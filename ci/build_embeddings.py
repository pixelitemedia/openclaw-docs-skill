#!/usr/bin/env python3
"""
Build embeddings for OpenClaw flattened docs and upsert to Supabase.

Phases (each runnable independently):
  chunk   : flattened doc → JSONL of unembedded chunks (no API calls)
  embed   : chunks JSONL  → JSONL with embedding vectors (calls OpenRouter)
  upsert  : embedded JSONL → Supabase docs_chunks + docs_fields tables
  all     : chunk + embed + upsert in one run

Usage:
  python3 scripts/build_embeddings.py chunk   --version 2026.5.8 --skill-dir . --out /tmp/chunks.jsonl
  python3 scripts/build_embeddings.py embed   --in /tmp/chunks.jsonl --out /tmp/embedded.jsonl
  python3 scripts/build_embeddings.py upsert  --in /tmp/embedded.jsonl
  python3 scripts/build_embeddings.py all     --version 2026.5.8 --skill-dir .

Environment variables:
  OPENROUTER_API_KEY            for `embed` (OpenRouter; OpenAI-compatible)
  EMBEDDING_MODEL               override; default openai/text-embedding-3-large
  EMBEDDING_DIMS                override; default 3072
  SUPABASE_URL                  for `upsert`; default https://gzfdvhuglftjnlhlcgjj.supabase.co
  SUPABASE_SERVICE_ROLE_KEY     for `upsert`; required to write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_MODEL = os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-large")
DEFAULT_DIMS = int(os.environ.get("EMBEDDING_DIMS", "3072"))
DEFAULT_SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://gzfdvhuglftjnlhlcgjj.supabase.co"
)
EMBEDDING_BATCH = 50  # rows per OpenRouter call
UPSERT_BATCH = 100  # rows per Supabase POST

# Sections that document configuration schema — `docs_fields` is built
# only from these so field_check has high precision. Everything still gets
# chunked + embedded for general search.
CANONICAL_SCHEMA_PATHS = (
    "gateway/configuration-reference.md",
    "gateway/secrets.md",
    "gateway/protocol.md",
    "plugins/manifest.md",
    "plugins/sdk-overview.md",
    "plugins/sdk-channel-plugins.md",
    "plugins/sdk-provider-plugins.md",
    "plugins/architecture.md",
    "channels/",  # all channel docs document per-channel config
    "reference/",
    "cli/",
)

VERSION_PREFIX = "openclaw-docs."

# --------------------------------------------------------------------------- #
# Phase 1: chunking
# --------------------------------------------------------------------------- #

# A chunk is one (heading-block) of a section: from one H2/H3 to the next.
# Sections without internal headings get one chunk for the whole section.
# Long heading-blocks (> MAX_CHARS) get split with overlap so embeddings
# don't degrade on very long inputs.
MAX_CHARS = 4000
OVERLAP_CHARS = 400

RE_SECTION = re.compile(r"^# Section: (.+)$")
RE_HEADING = re.compile(r"^(#{2,3})\s+(.+)$")
RE_FENCE = re.compile(r"^```")


@dataclass
class Chunk:
    version: str
    section_path: str
    heading: Optional[str]
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    content: str
    content_type: str
    metadata: dict


def _classify(text: str) -> str:
    """Cheap content-type label: prose / code / table / mixed."""
    lines = text.split("\n")
    fence_lines = sum(1 for l in lines if RE_FENCE.match(l))
    code_lines = 0
    in_fence = False
    for l in lines:
        if RE_FENCE.match(l):
            in_fence = not in_fence
            continue
        if in_fence:
            code_lines += 1
    table_lines = sum(1 for l in lines if l.startswith("|") and "|" in l[1:])
    n = max(len(lines), 1)
    code_frac = code_lines / n
    table_frac = table_lines / n
    if code_frac > 0.30:
        return "code"
    if table_frac > 0.20:
        return "table"
    if code_frac > 0.10 or table_frac > 0.10:
        return "mixed"
    return "prose"


def _split_long(text: str, line_offset: int, byte_offset_table: list) -> list:
    """Split a too-long block into overlapping pieces at paragraph boundaries.
    Returns list of (text, line_offset, byte_offset_start, byte_offset_end)."""
    if len(text) <= MAX_CHARS:
        return [(text, line_offset, byte_offset_table[line_offset], byte_offset_table[line_offset + len(text.split("\n"))])]

    out = []
    pieces = text.split("\n\n")
    cur = ""
    cur_lines = 0
    cur_start_line = line_offset
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > MAX_CHARS:
            # emit current with overlap with the next
            start_byte = byte_offset_table[cur_start_line]
            end_byte = byte_offset_table[cur_start_line + cur_lines]
            out.append((cur, cur_start_line, start_byte, end_byte))
            # start next with tail of previous as overlap
            tail_lines = cur.split("\n")
            overlap_tail = "\n".join(tail_lines[-max(1, len(tail_lines) // 4):])
            cur = overlap_tail + "\n\n" + p if overlap_tail else p
            cur_start_line = cur_start_line + cur_lines - len(overlap_tail.split("\n")) if overlap_tail else cur_start_line + cur_lines
            cur_lines = len(cur.split("\n"))
        else:
            if cur:
                cur += "\n\n" + p
            else:
                cur = p
            cur_lines = len(cur.split("\n"))
    if cur:
        start_byte = byte_offset_table[cur_start_line]
        end_byte = byte_offset_table[cur_start_line + cur_lines]
        out.append((cur, cur_start_line, start_byte, end_byte))
    return out


def chunk_doc(doc_path: Path, version: str) -> Iterable[Chunk]:
    """Walk the flattened doc and emit one Chunk per heading-block (or
    sub-block when too long). Heading-block = from one H2/H3 to the next."""
    text = doc_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # Build line→byte-offset table (1-indexed).
    byte_offsets = [0, 0]  # [0] unused, [1] start of line 1
    cum = 0
    for line in lines:
        cum += len(line.encode("utf-8")) + 1
        byte_offsets.append(cum)

    cur_section: Optional[str] = None
    cur_heading: Optional[str] = None
    block_start: Optional[int] = None
    block_buffer: list = []
    in_fence = False

    def emit(end_line_excl: int):
        if cur_section is None or block_start is None or not block_buffer:
            return
        end_line = end_line_excl - 1
        body = "\n".join(block_buffer).strip("\n")
        if not body.strip():
            return
        # If the block is too long, split with overlap.
        if len(body) <= MAX_CHARS:
            yield Chunk(
                version=version,
                section_path=cur_section,
                heading=cur_heading,
                start_line=block_start,
                end_line=end_line,
                start_byte=byte_offsets[block_start],
                end_byte=byte_offsets[end_line + 1],
                content=body,
                content_type=_classify(body),
                metadata={"split": False},
            )
        else:
            pieces = _split_long(body, block_start, byte_offsets)
            for i, (sub_text, sub_line, sub_byte_start, sub_byte_end) in enumerate(pieces):
                sub_end_line = sub_line + len(sub_text.split("\n")) - 1
                yield Chunk(
                    version=version,
                    section_path=cur_section,
                    heading=cur_heading,
                    start_line=sub_line,
                    end_line=sub_end_line,
                    start_byte=sub_byte_start,
                    end_byte=sub_byte_end,
                    content=sub_text,
                    content_type=_classify(sub_text),
                    metadata={"split": True, "piece": i, "of": len(pieces)},
                )

    for i, line in enumerate(lines, start=1):
        if RE_FENCE.match(line):
            in_fence = not in_fence
            block_buffer.append(line)
            continue

        m_sec = RE_SECTION.match(line) if not in_fence else None
        m_h = RE_HEADING.match(line) if not in_fence else None

        if m_sec:
            yield from emit(i)
            cur_section = m_sec.group(1).strip()
            cur_heading = None
            block_start = i + 1
            block_buffer = []
            continue

        if m_h and cur_section is not None:
            yield from emit(i)
            cur_heading = m_h.group(2).strip()
            block_start = i
            block_buffer = [line]
            continue

        if cur_section is not None:
            if block_start is None:
                block_start = i
            block_buffer.append(line)

    yield from emit(len(lines) + 1)


# --------------------------------------------------------------------------- #
# Field extraction (for docs_fields table → field_check tool)
# --------------------------------------------------------------------------- #

# Match `key:` in JSON5/JS-ish config blocks. Captures the field name.
RE_JSON_FIELD = re.compile(r'^\s*"?([a-zA-Z][a-zA-Z0-9_]*)"?\s*:', re.MULTILINE)
# Match standalone identifier mentions wrapped in backticks: `field`
RE_BACKTICK_FIELD = re.compile(r"`([a-zA-Z][a-zA-Z0-9_]{1,63})`")


def is_canonical_section(section_path: str) -> bool:
    return any(
        section_path == p or (p.endswith("/") and section_path.startswith(p))
        for p in CANONICAL_SCHEMA_PATHS
    )


def extract_fields(chunk: Chunk) -> Iterable[dict]:
    """Best-effort field extraction: pull identifiers from JSON code blocks
    and prominently-mentioned backtick-wrapped names in canonical schema
    sections. Heuristic, not perfect — it errs on inclusion to keep
    field_check from missing real fields."""
    if not is_canonical_section(chunk.section_path):
        return

    seen = set()
    # JSON5/JSON code blocks: extract `field:` keys.
    in_fence = False
    fence_lang = None
    code_block_lines: list = []

    def flush_code(lang: str | None, block: list[str]):
        if not block:
            return
        if lang in ("json", "json5", "jsonc", "ts", "typescript", "js", "javascript", None):
            for m in RE_JSON_FIELD.finditer("\n".join(block)):
                yield m.group(1)

    for line in chunk.content.split("\n"):
        m_fence = RE_FENCE.match(line)
        if m_fence:
            if in_fence:
                # closing
                for f in flush_code(fence_lang, code_block_lines):
                    yield f
                code_block_lines = []
                in_fence = False
                fence_lang = None
            else:
                in_fence = True
                fence_lang = line.strip("` ").lower() or None
            continue
        if in_fence:
            code_block_lines.append(line)

    return  # generator above; this method actually yields field names which the caller wraps


def extract_field_records(chunk: Chunk) -> list[dict]:
    """Full record version of extract_fields — yields dicts ready for upsert."""
    if not is_canonical_section(chunk.section_path):
        return []
    fields: dict = {}  # name → record (dedup within chunk)

    # Heuristic: derive context from heading + section
    context_path = chunk.section_path.removesuffix(".md").replace("/", ".")
    if chunk.heading:
        context_path = f"{context_path}::{chunk.heading}"

    # JSON-ish fields from code blocks
    in_fence = False
    fence_lang = None
    block: list = []
    for line in chunk.content.split("\n"):
        if RE_FENCE.match(line):
            if in_fence:
                if fence_lang in (None, "", "json", "json5", "jsonc", "ts", "typescript", "js", "javascript"):
                    for m in RE_JSON_FIELD.finditer("\n".join(block)):
                        name = m.group(1)
                        if 2 <= len(name) <= 64 and name not in fields:
                            fields[name] = {
                                "version": chunk.version,
                                "field_name": name,
                                "context_path": context_path,
                                "section_path": chunk.section_path,
                                "description": None,
                                "metadata": {"source": "json_code_block"},
                            }
                in_fence = False
                fence_lang = None
                block = []
            else:
                in_fence = True
                fence_lang = (line.strip("` ").lower() or None)
            continue
        if in_fence:
            block.append(line)

    return list(fields.values())


# --------------------------------------------------------------------------- #
# Phase 2: embedding (OpenRouter, OpenAI-compatible)
# --------------------------------------------------------------------------- #


def _http_post_json(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def embed_batch(texts: list[str], api_key: str, model: str, dims: int) -> list[list[float]]:
    """Call OpenRouter embeddings; return one vector per text in the same order."""
    body = {"model": model, "input": texts}
    if dims and dims < 3072:
        body["dimensions"] = dims
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pixelitemedia/openclaw-docs-skill",
        "X-Title": "openclaw-docs-skill",
    }
    for attempt in range(4):
        try:
            r = _http_post_json(
                "https://openrouter.ai/api/v1/embeddings", headers, body, timeout=120
            )
            return [item["embedding"] for item in r["data"]]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                wait = 2 ** attempt
                print(f"  HTTP {e.code}, retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise


# --------------------------------------------------------------------------- #
# Phase 3: upsert to Supabase
# --------------------------------------------------------------------------- #


def upsert_chunks(rows: list[dict], supabase_url: str, service_key: str):
    """Upsert via PostgREST. on_conflict matches the unique constraint."""
    url = (
        f"{supabase_url}/rest/v1/docs_chunks"
        f"?on_conflict=version,section_path,start_line"
    )
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for i in range(0, len(rows), UPSERT_BATCH):
        batch = rows[i : i + UPSERT_BATCH]
        data = json.dumps(batch).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
        print(f"  Upserted {min(i + UPSERT_BATCH, len(rows))}/{len(rows)} chunks")


def upsert_fields(rows: list[dict], supabase_url: str, service_key: str):
    if not rows:
        return
    url = (
        f"{supabase_url}/rest/v1/docs_fields"
        f"?on_conflict=version,field_name,context_path"
    )
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for i in range(0, len(rows), UPSERT_BATCH):
        batch = rows[i : i + UPSERT_BATCH]
        data = json.dumps(batch).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
        print(f"  Upserted {min(i + UPSERT_BATCH, len(rows))}/{len(rows)} fields")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def cmd_chunk(args):
    skill_root = Path(args.skill_dir).resolve()
    doc_path = skill_root / "versions" / f"{VERSION_PREFIX}{args.version}.md"
    if not doc_path.exists() and args.version == "latest":
        doc_path = skill_root / "versions" / "openclaw-docs.latest.md"
    if not doc_path.exists():
        sys.exit(f"Doc not found: {doc_path}")

    # Resolve "latest" to concrete version from the toc index
    if args.version == "latest":
        toc = skill_root / "versions" / "openclaw-docs.latest.toc.jsonl"
        if toc.exists():
            with open(toc) as f:
                first = json.loads(f.readline())
                args.version = first["version"]
                print(f"latest → {args.version}", file=sys.stderr)

    out = open(args.out, "w") if args.out else sys.stdout
    n = 0
    for chunk in chunk_doc(doc_path, args.version):
        out.write(json.dumps(asdict(chunk)) + "\n")
        n += 1
    if args.out:
        out.close()
    print(f"Chunked {n} chunks → {args.out or '-'}", file=sys.stderr)


def cmd_embed(args):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("Set OPENROUTER_API_KEY")
    model = args.model or DEFAULT_MODEL
    dims = args.dims or DEFAULT_DIMS

    # Resume support: if --resume and the output file exists, skip chunks already
    # in there (keyed by section_path + start_line). Embeds only the rest and
    # appends. Saves cost + time on partial-failure retries.
    done_keys: set = set()
    out_mode = "w"
    if args.resume and args.out and Path(args.out).exists():
        with open(args.out) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    done_keys.add((r["section_path"], r["start_line"]))
                except Exception:
                    pass
        out_mode = "a"
        print(f"Resume: {len(done_keys)} chunks already embedded, skipping those.", file=sys.stderr)

    # Stream input, skip done, embed batched, write incrementally — no big in-memory list.
    out = open(args.out, out_mode) if args.out else sys.stdout
    pending: list = []
    total = 0
    embedded = 0

    def flush(batch: list):
        nonlocal embedded
        if not batch:
            return
        texts = [c["content"] for c in batch]
        vecs = embed_batch(texts, api_key, model, dims)
        for c, v in zip(batch, vecs):
            c["embedding"] = v
            out.write(json.dumps(c) + "\n")
        out.flush()
        embedded += len(batch)
        print(f"  embedded {embedded} (running)", file=sys.stderr)

    print(f"Embedding via {model} ({dims} dims)...", file=sys.stderr)
    with open(args.in_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            total += 1
            if (c["section_path"], c["start_line"]) in done_keys:
                continue
            pending.append(c)
            if len(pending) >= EMBEDDING_BATCH:
                flush(pending)
                pending = []
    flush(pending)

    if args.out:
        out.close()
    print(f"done — {embedded} embedded this run, {len(done_keys)} skipped (resumed), {total} total chunks", file=sys.stderr)


def _to_db_row(c: dict) -> dict:
    """Convert chunk dict to docs_chunks row, including halfvec literal."""
    emb = c.get("embedding")
    return {
        "version": c["version"],
        "section_path": c["section_path"],
        "heading": c.get("heading"),
        "start_line": c["start_line"],
        "end_line": c["end_line"],
        "start_byte": c.get("start_byte"),
        "end_byte": c.get("end_byte"),
        "content": c["content"],
        "content_type": c["content_type"],
        # PostgREST accepts pgvector as JSON array string formatted "[v1,v2,...]"
        "embedding": "[" + ",".join(f"{x:.6f}" for x in emb) + "]" if emb else None,
        "metadata": c.get("metadata", {}),
    }


def cmd_upsert(args):
    service_key = (
        os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not service_key:
        sys.exit("Set SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY)")
    url = args.supabase_url or DEFAULT_SUPABASE_URL

    rows = []
    field_rows: list = []
    with open(args.in_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            rows.append(_to_db_row(c))
            chunk_obj = Chunk(
                version=c["version"],
                section_path=c["section_path"],
                heading=c.get("heading"),
                start_line=c["start_line"],
                end_line=c["end_line"],
                start_byte=c.get("start_byte", 0),
                end_byte=c.get("end_byte", 0),
                content=c["content"],
                content_type=c["content_type"],
                metadata=c.get("metadata", {}),
            )
            field_rows.extend(extract_field_records(chunk_obj))

    print(f"Upserting {len(rows)} chunks + {len(field_rows)} fields to {url}", file=sys.stderr)
    upsert_chunks(rows, url, service_key)
    upsert_fields(field_rows, url, service_key)
    print("done", file=sys.stderr)


def cmd_all(args):
    """chunk + embed + upsert in one pass via tmp files."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".chunks.jsonl", delete=False) as tf_chunks:
        chunks_path = tf_chunks.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".embedded.jsonl", delete=False) as tf_emb:
        embedded_path = tf_emb.name

    try:
        # chunk
        args.out = chunks_path
        cmd_chunk(args)
        # embed
        args.in_path = chunks_path
        args.out = embedded_path
        cmd_embed(args)
        # upsert
        args.in_path = embedded_path
        cmd_upsert(args)
    finally:
        Path(chunks_path).unlink(missing_ok=True)
        Path(embedded_path).unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_chunk = sub.add_parser("chunk")
    p_chunk.add_argument("--version", default="latest")
    p_chunk.add_argument("--skill-dir", default=os.path.expanduser("~/openclaw-docs-skill"))
    p_chunk.add_argument("--out")
    p_chunk.set_defaults(func=cmd_chunk)

    p_embed = sub.add_parser("embed")
    p_embed.add_argument("--in", dest="in_path", required=True)
    p_embed.add_argument("--out")
    p_embed.add_argument("--model", default=DEFAULT_MODEL)
    p_embed.add_argument("--dims", type=int, default=DEFAULT_DIMS)
    p_embed.add_argument("--resume", action="store_true",
                         help="If --out exists, skip chunks already in it and append new ones.")
    p_embed.set_defaults(func=cmd_embed)

    p_upsert = sub.add_parser("upsert")
    p_upsert.add_argument("--in", dest="in_path", required=True)
    p_upsert.add_argument("--supabase-url", default=DEFAULT_SUPABASE_URL)
    p_upsert.set_defaults(func=cmd_upsert)

    p_all = sub.add_parser("all")
    p_all.add_argument("--version", default="latest")
    p_all.add_argument("--skill-dir", default=os.path.expanduser("~/openclaw-docs-skill"))
    p_all.add_argument("--model", default=DEFAULT_MODEL)
    p_all.add_argument("--dims", type=int, default=DEFAULT_DIMS)
    p_all.add_argument("--supabase-url", default=DEFAULT_SUPABASE_URL)
    p_all.set_defaults(func=cmd_all)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

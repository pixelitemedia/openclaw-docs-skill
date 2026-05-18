#!/usr/bin/env python3
"""CI step: chunk + embed the latest flattened doc and POST to the Supabase
ingest Edge Function. Idempotent — skips embedding if the version is already
fully present in docs_chunks.

Required env vars:
  OPENROUTER_API_KEY        for embedding (OpenAI-compatible /v1/embeddings)
  SUPABASE_URL              e.g. https://gzfdvhuglftjnlhlcgjj.supabase.co
  INGEST_TOKEN              shared secret matching the ingest Edge Function
  SUPABASE_QUERY_KEY        optional: anon/publishable key for the read-only
                            check that confirms whether a version is already
                            ingested. If unset, we skip the check and always
                            re-embed (idempotent on the DB side anyway).

Optional:
  EMBEDDING_MODEL           default openai/text-embedding-3-large
  EMBEDDING_DIMS            default 3072
  SKILL_DIR                 default .
  FORCE_REINGEST            if "1", skip the already-ingested check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Import the chunker + field-extraction logic from build_embeddings.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_embeddings import (  # type: ignore
    chunk_doc,
    extract_field_records,
    embed_batch,
    Chunk,
    EMBEDDING_BATCH,
    VERSION_PREFIX,
)

UPSERT_BATCH = 50  # ~1.3 MB per Edge Function POST (kept under typical limits)


def already_ingested(supabase_url: str, query_key: str | None, version: str) -> bool:
    """Returns True if the version already has chunks in Supabase. Skips the
    check if no query_key is available (re-embedding is idempotent via
    on-conflict-do-update, so the worst case is unnecessary work)."""
    if not query_key:
        return False
    url = f"{supabase_url}/rest/v1/docs_chunks?select=id&version=eq.{version}&limit=1"
    req = urllib.request.Request(url)
    req.add_header("apikey", query_key)
    req.add_header("Authorization", f"Bearer {query_key}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read())
            return len(rows) > 0
    except urllib.error.HTTPError as e:
        # Read access not authorized; assume not ingested and let writes happen
        print(f"  (couldn't check existing rows: HTTP {e.code}); proceeding to re-embed", file=sys.stderr)
        return False


def to_row(c: dict) -> dict:
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
        "embedding": "[" + ",".join(f"{x:.6f}" for x in emb) + "]" if emb else None,
        "metadata": c.get("metadata", {}),
    }


def post_to_ingest(url: str, token: str, table: str, rows: list) -> int:
    body = json.dumps({"table": table, "rows": rows}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Ingest-Token", token)
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.loads(r.read())
        return j.get("inserted", 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="Override version to ingest (defaults to latest in versions/)")
    ap.add_argument("--skill-dir", default=os.environ.get("SKILL_DIR", "."))
    args = ap.parse_args()

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    ingest_token = os.environ.get("INGEST_TOKEN")
    if not (openrouter_key and supabase_url and ingest_token):
        sys.exit("Missing required env vars: OPENROUTER_API_KEY, SUPABASE_URL, INGEST_TOKEN")

    skill_dir = Path(args.skill_dir).resolve()

    # Resolve version from latest toc index (or override)
    if args.version:
        version = args.version
    else:
        latest_toc = skill_dir / "versions" / "openclaw-docs.latest.toc.jsonl"
        if not latest_toc.exists():
            sys.exit(f"latest toc not found at {latest_toc}; run flatten first")
        with open(latest_toc) as f:
            version = json.loads(f.readline())["version"]
    print(f"Target version: {version}", file=sys.stderr)

    # Already ingested?
    query_key = os.environ.get("SUPABASE_QUERY_KEY")
    if os.environ.get("FORCE_REINGEST") != "1" and already_ingested(supabase_url, query_key, version):
        print(f"Version {version} already in Supabase docs_chunks; skipping (set FORCE_REINGEST=1 to override)", file=sys.stderr)
        return

    # Find the flattened doc for this version. In CI the version-specific .md
    # is briefly on disk before being uploaded to a release and removed; we run
    # before that cleanup. As a fallback, also try latest.md.
    doc_path = skill_dir / "versions" / f"{VERSION_PREFIX}{version}.md"
    if not doc_path.exists():
        # Fallback: latest.md should have the same content as the just-flattened version
        fallback = skill_dir / "versions" / "openclaw-docs.latest.md"
        if fallback.exists():
            doc_path = fallback
            print(f"Using {fallback} as source (version-specific .md not found)", file=sys.stderr)
        else:
            sys.exit(f"No flattened doc found at {doc_path} or {fallback}")

    # Chunk
    chunks = list(chunk_doc(doc_path, version))
    print(f"Chunked {len(chunks)} chunks", file=sys.stderr)

    # Dedupe by (version, section_path, start_line) — keep longest content
    seen: dict = {}
    field_rows = []
    for c in chunks:
        key = (c.version, c.section_path, c.start_line)
        if key not in seen or len(c.content) > len(seen[key].content):
            seen[key] = c
        field_rows.extend(extract_field_records(c))
    deduped = list(seen.values())
    print(f"After dedupe: {len(deduped)} unique chunks, {len(field_rows)} raw field records", file=sys.stderr)

    # Embed in batches, streaming results to the ingest endpoint
    ingest_url = f"{supabase_url}/functions/v1/ingest"
    print(f"Embedding via openai/text-embedding-3-large and posting to {ingest_url}", file=sys.stderr)
    total_inserted = 0
    for i in range(0, len(deduped), EMBEDDING_BATCH):
        batch = deduped[i : i + EMBEDDING_BATCH]
        texts = [c.content for c in batch]
        vecs = embed_batch(
            texts,
            openrouter_key,
            os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-large"),
            int(os.environ.get("EMBEDDING_DIMS", "3072")),
        )
        rows = []
        for c, v in zip(batch, vecs):
            d = c.__dict__.copy()
            d["embedding"] = v
            rows.append(to_row(d))
        # Push to ingest in batches of UPSERT_BATCH
        for j in range(0, len(rows), UPSERT_BATCH):
            sub = rows[j : j + UPSERT_BATCH]
            n = post_to_ingest(ingest_url, ingest_token, "docs_chunks", sub)
            total_inserted += n
        print(f"  ingested {total_inserted}/{len(deduped)}", file=sys.stderr)

    # Dedupe + ingest fields
    field_seen = set()
    field_unique = []
    for f in field_rows:
        k = (f["version"], f["field_name"], f["context_path"])
        if k in field_seen:
            continue
        field_seen.add(k)
        field_unique.append(f)
    print(f"Posting {len(field_unique)} unique fields", file=sys.stderr)
    field_total = 0
    for i in range(0, len(field_unique), UPSERT_BATCH):
        batch = field_unique[i : i + UPSERT_BATCH]
        n = post_to_ingest(ingest_url, ingest_token, "docs_fields", batch)
        field_total += n
    print(f"DONE — {total_inserted} chunks + {field_total} fields", file=sys.stderr)


if __name__ == "__main__":
    main()

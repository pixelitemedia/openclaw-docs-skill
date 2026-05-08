#!/usr/bin/env python3
"""Read `gh release list --json tagName,publishedAt` JSON from stdin, emit
versions/releases.json shape on stdout.

Filters to tags of the form `v<version>`, drops everything else. Sort is by
the version string's tuple (numerically) so `2026.5.10` doesn't end up below
`2026.5.6`. Used by the CI workflow.
"""
import json
import re
import sys


def version_key(v: str):
    parts = v.split(".")
    return tuple(int(x) if x.isdigit() else x for x in parts)


def main() -> None:
    rels = json.load(sys.stdin)
    out = []
    for r in rels:
        tag = r["tagName"]
        m = re.match(r"^v(.+)$", tag)
        if not m:
            continue
        out.append(
            {
                "version": m.group(1),
                "tag": tag,
                "published_at": r["publishedAt"],
            }
        )
    out.sort(key=lambda r: version_key(r["version"]), reverse=True)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

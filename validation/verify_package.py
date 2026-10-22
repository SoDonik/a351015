#!/usr/bin/env python3
"""Check the SHA-256 manifest for the supplied release files; read-only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest = json.loads((ROOT / "PACKAGE_MANIFEST.json").read_text())
    failures = []
    for relative, expected in manifest["files"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            failures.append(f"Missing or invalid file: {relative}")
            continue
        data = path.read_bytes()
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            failures.append(f"Changed file: {relative}")
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        return 1
    print(f"PASS: {len(manifest['files'])} packaged files match their SHA-256 manifest.")
    print("This confirms file identity, not the mathematical conclusions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Multi-architecture manifest validation gate."""

import argparse, json, sys

REQUIRED_STATUS = {"validated", "passed", "scanned"}

def validate(data, strict=False):
    passed, failed = [], []
    manifests = data.get("manifests", [data])
    for m in manifests:
        arch = m.get("platform", {}).get("architecture", "unknown")
        digest = m.get("digest", "")
        size = m.get("size", 0)
        if not digest:
            failed.append(f"architecture {arch}: missing digest")
            continue
        status = m.get("annotations", {}).get("com.example.validation.status", "")
        if strict and status.lower() not in REQUIRED_STATUS:
            failed.append(f"architecture {arch}: status '{status}' not in {REQUIRED_STATUS}")
        else:
            passed.append(f"{arch} {digest[:12]} ({size} bytes) {status}")
    return passed, failed

def main():
    ap = argparse.ArgumentParser(description="Validate multi-arch Docker manifest")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("input", nargs="?", default=None)
    args = ap.parse_args()
    data = json.load(open(args.input)) if args.input else json.load(sys.stdin)
    passed, failed = validate(data, strict=args.strict)
    for p in passed: print(f"OK {p}")
    for f in failed: print(f"FAIL {f}")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()

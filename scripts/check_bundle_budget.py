"""Check a Vercel Python dependency install or an actual .func artifact."""

import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
parser.add_argument("--max-mb", type=int, default=225)
args = parser.parse_args()
if not args.path.is_dir():
    parser.error("the measured directory does not exist")

total = sum(file.stat().st_size for file in args.path.rglob("*") if file.is_file())
size = total / 1_000_000
print(f"Uncompressed files in {args.path}: {size:.1f} MB (budget {args.max_mb} MB)")
if total > args.max_mb * 1_000_000:
    raise SystemExit(1)

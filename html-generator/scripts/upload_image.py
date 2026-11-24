#!/usr/bin/env python3
"""Upload a local image to Feishu and print its image_key.

Used by the agent to embed screenshots / chart images inline in markdown:

    .venv/bin/python .claude/skills/html-generator/scripts/upload_image.py \\
        --path /tmp/foo.png [--keep]

Output (stdout):
    image_key: img_v3_xxxxxxxx_yyyyyyy

Then the agent inlines the key with `![alt](image_key)` in the answer body.

Default behaviour: after a successful upload the local file is **deleted** to
avoid polluting the repo / disk with stale screenshots. Pass --keep to retain
it (useful when you want to attach the same image to multiple recipients or
debug the upload). On upload failure the file is always preserved so you can
re-try / inspect it.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure the project root is importable when this script is invoked directly.
# Path layout: <repo>/.claude/skills/html-generator/scripts/upload_image.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from feishu.image import upload_image  # noqa: E402


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Upload an image to Feishu")
    parser.add_argument("--path", required=True, help="Absolute path to the image file")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the local file after a successful upload (default: delete)",
    )
    args = parser.parse_args()

    try:
        image_key = await upload_image(args.path)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"local file preserved at: {args.path}", file=sys.stderr)
        return 1

    print(f"image_key: {image_key}")

    if not args.keep:
        try:
            os.remove(args.path)
            print(f"deleted local file: {args.path}", file=sys.stderr)
        except OSError as exc:
            # Non-fatal: caller already has the image_key, the leftover file is
            # only a hygiene issue.
            print(
                f"WARN: failed to delete {args.path}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))


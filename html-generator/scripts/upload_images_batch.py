#!/usr/bin/env python3
"""Upload multiple local images to Feishu **concurrently** and print
`path<TAB>image_key` lines on stdout.

Usage:
    .venv/bin/python .claude/skills/html-generator/scripts/upload_images_batch.py \\
        --paths /tmp/playwright/a.png /tmp/playwright/b.png /tmp/playwright/c.png \\
        [--concurrency 6] [--keep]

Why this exists:
    The single-file `upload_image.py` is fine for one screenshot, but doing 10
    images in a loop pays the "import + token fetch" cost N times AND the
    harness tends to serialise sibling Bash calls. This script does the work in
    a single Python process with `asyncio.gather` so 10 images upload in ~3s
    instead of ~30s.

Behaviour:
    - On success: stdout gets one `path\\timage_key` line per image, in INPUT
      order. exit 0.
    - On any image's failure: that line is written to stderr in the form
      `FAIL\\tpath\\treason`, the rest still complete. exit 1 if any failed.
    - Local files are deleted after a successful upload (default). Failed
      images are kept so you can re-try / inspect.
    - Each upload uses the lower-level `feishu.image.upload_image` which
      already retries transient API failures (rate limit, network blip, 5xx)
      with exponential backoff + jitter — caller doesn't need to retry again.
    - Concurrency is capped (default 6) to avoid stampeding the Feishu API.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Path layout: <repo>/.claude/skills/html-generator/scripts/upload_images_batch.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from feishu.image import upload_image  # noqa: E402


async def _upload_one(
    sem: asyncio.Semaphore,
    path: str,
    keep: bool,
) -> tuple[str, str | None, str | None]:
    """Returns (path, image_key, error). image_key is None on failure, error
    is None on success."""
    async with sem:
        try:
            image_key = await upload_image(path)
        except Exception as exc:
            return path, None, f"{type(exc).__name__}: {exc}"
    if not keep:
        try:
            os.remove(path)
        except OSError as exc:
            # non-fatal — caller has the image_key already
            print(f"WARN: failed to delete {path}: {exc}", file=sys.stderr)
    return path, image_key, None


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Concurrently upload multiple images to Feishu",
    )
    parser.add_argument("--paths", nargs="+", required=True,
                        help="Absolute paths to image files")
    parser.add_argument("--concurrency", type=int, default=6,
                        help="Max concurrent uploads (default: 6)")
    parser.add_argument("--keep", action="store_true",
                        help="Keep local files after upload (default: delete)")
    args = parser.parse_args()

    if args.concurrency < 1:
        print("ERROR: --concurrency must be >= 1", file=sys.stderr)
        return 2

    sem = asyncio.Semaphore(args.concurrency)
    tasks = [
        asyncio.create_task(_upload_one(sem, p, args.keep))
        for p in args.paths
    ]
    results = await asyncio.gather(*tasks)

    any_fail = False
    # Preserve input order on stdout so the agent can correlate keys with
    # original paths positionally.
    for path, image_key, err in results:
        if err is None:
            print(f"{path}\t{image_key}")
        else:
            any_fail = True
            print(f"FAIL\t{path}\t{err}", file=sys.stderr)

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))

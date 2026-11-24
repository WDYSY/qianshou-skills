#!/usr/bin/env python3
"""html-generator 入口门禁：仅文本模型先向用户投票切模型。

退出码：
  0  VISION_OK / SKIP_SCREENSHOT_QA — 可以继续生成
  2  VOTE_SENT — 已发卡，本轮必须立刻结束
  3  发卡失败
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FEISHU_MSG_SCRIPTS = PROJECT_ROOT / ".claude" / "skills" / "feishu-msg" / "scripts"
if str(FEISHU_MSG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(FEISHU_MSG_SCRIPTS))

from agent.model_catalog import model_supports_image, normalize_short_model  # noqa: E402
from feishu.card import build_api_error_recovery_card  # noqa: E402
from services.api_error_recovery import (  # noqa: E402
    HTML_SKIP_SCREENSHOT_QA_NOTE,
    NEED_VISION_VOTE,
    SKIP_SCREENSHOT_QA,
    VISION_OK,
    has_html_skip_screenshot_qa,
    html_vision_gate_status,
    html_vision_gate_vote_spec,
)


def resolve_current_model() -> str:
    env_model = normalize_short_model(os.getenv("BAIGE_CURRENT_MODEL") or "")
    if env_model:
        return env_model
    thread_id = (os.getenv("BAIGE_FEISHU_THREAD_ID") or "").strip()
    if not thread_id:
        return ""
    try:
        from feishu_msg import _resolve_db_path
        db_path = _resolve_db_path()
        if not db_path.exists():
            return ""
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            row = conn.execute(
                "SELECT model FROM thread_mapping WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        finally:
            conn.close()
        return normalize_short_model((row[0] if row else "") or "")
    except Exception:
        return ""


def send_vision_gate_vote(current_model: str, thread_id: str) -> str:
    from feishu_msg import _persist_vote_cache, _send_card, _update_vote_card_msgid

    spec = html_vision_gate_vote_spec(current_model=current_model)
    vote_id = secrets.token_hex(6)
    _persist_vote_cache(
        vote_id=vote_id,
        question=spec["question"],
        options=spec["options"],
        multi=False,
        allow_text=False,
        thread_id=thread_id,
    )
    body = (
        f"当前模型 `{current_model or '未知'}` 仅支持文本，"
        "没法对生成的页面做截图自检。建议先切到支持识图的模型。"
    )
    card_json = build_api_error_recovery_card(
        vote_id=vote_id,
        thread_id=thread_id,
        question=spec["question"],
        options=spec["options"],
        body=body,
    )
    sent_msg_id = _send_card(
        card_json,
        label=f"html-vision-gate (vote_id={vote_id})",
    )
    if sent_msg_id:
        _update_vote_card_msgid(vote_id, sent_msg_id)
    return vote_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="html-generator vision gate")
    parser.add_argument("--dry-run", action="store_true", help="print decision, do not send vote")
    parser.add_argument("--model", default="", help="override BAIGE_CURRENT_MODEL")
    args = parser.parse_args(argv)

    model = normalize_short_model(args.model) or resolve_current_model()
    thread_id = (os.getenv("BAIGE_FEISHU_THREAD_ID") or "").strip()
    skip = has_html_skip_screenshot_qa(thread_id)
    status = html_vision_gate_status(model, skip_screenshot_qa=skip)

    if status == VISION_OK:
        print("VISION_OK")
        if model_supports_image(model) and skip:
            from services.api_error_recovery import clear_html_skip_screenshot_qa
            clear_html_skip_screenshot_qa(thread_id)
        return 0

    if status == SKIP_SCREENSHOT_QA:
        print("SKIP_SCREENSHOT_QA")
        print(HTML_SKIP_SCREENSHOT_QA_NOTE)
        return 0

    spec = html_vision_gate_vote_spec(current_model=model)
    if args.dry_run:
        print("NEED_VOTE")
        print(json.dumps(spec, ensure_ascii=False))
        return 2

    try:
        vote_id = send_vision_gate_vote(model, thread_id)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 3
        print("VOTE_FAILED", file=sys.stderr)
        return code if code else 3
    except Exception as exc:
        print(f"VOTE_FAILED: {exc}", file=sys.stderr)
        return 3

    print("VOTE_SENT")
    print(f"vote_id={vote_id}")
    print("已向用户发出切换模型投票。本轮立刻结束，不要生成页面、不要调子 Agent。")
    return 2


if __name__ == "__main__":
    sys.exit(main())

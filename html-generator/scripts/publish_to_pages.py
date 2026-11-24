#!/usr/bin/env python3
"""把刚生成的 HTML 复制到当前仓库 public/ 目录并 push（走 GitLab Pages）。

用法:
    .venv/bin/python .claude/skills/html-generator/scripts/publish_to_pages.py \\
        --src-html /home/powerop/work/baige-ai-assistant/ui/generated/202605/foo_20260519_120000.html \\
        --topic foo \\
        [--user-id hua.chen]

脚本会：
1. 解析 source 路径，按文件名末尾的 _YYYYMMDD[_HHmmss] 提取日期；缺失则用今天
2. 计算目标目录: /home/powerop/work/baige-ai-assistant/public/<user>/<YYYYMMDD>-<topic-slug>/index.html
3. 重写 vendor URL（景玩超级助手内网 → ../../static/vendor/），重写其他 generated/ 跨页链接
4. 自动重新生成用户主页 index.html（按日期倒序列出该用户所有页面）
5. git pull --rebase / add / commit / push
6. 输出最终公网 URL 到 stdout 一行（agent 直接拿来回复用户）

异常时返回非 0，stderr 输出原因，agent 回退给用户内网链接即可。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PAGES_REPO = Path("/home/powerop/work/repos/ttd-super-assistant")
PAGES_PUBLIC = PAGES_REPO / "public"
PAGES_BASE_URL = "http://pages.release.ctripcorp.com/super/ttd-super-assistant"
PAGES_BRANCH = "main"

# 容器名会因为重新部署而变化（port8038.<container>.gps.cloud.ctripcorp.com），
# 所以 <container> 段用通配，新旧 pod 都能命中。
INTERNAL_HOST_RE = r"https?://port8038\.[a-z0-9\-]+\.gps\.cloud\.ctripcorp\.com"

VENDOR_REWRITE = [
    (
        re.compile(INTERNAL_HOST_RE + r"/static/vendor/"),
        "../../static/vendor/",
    ),
    (
        re.compile(r"\{SYS_BASE_URL\}/static/vendor/"),
        "../../static/vendor/",
    ),
    # 生成时直接写 pages 公网 vendor URL（推荐写法，本地预览/playwright 截图都能跑通），
    # 发布到 pages 时改成相对路径，避免重复走外网。兼容新旧两个 pages 域名。
    (
        re.compile(r"https?://pages\.release\.ctripcorp\.com/(?:super/ttd-super-assistant|qiuyuli/ttd-super-assisstant)/static/vendor/"),
        "../../static/vendor/",
    ),
    # favicon：本地预览用 SYS_BASE_URL 直连 ui/static/logov4.jpg（也兼容旧的 favicon.ico/png），
    # 发布到 pages 时统一改成相对路径指向 public/logov4.jpg
    (
        re.compile(INTERNAL_HOST_RE + r"/static/logov4\.jpg"),
        "../../logov4.jpg",
    ),
    (
        re.compile(r"\{SYS_BASE_URL\}/static/logov4\.jpg"),
        "../../logov4.jpg",
    ),
    (
        re.compile(INTERNAL_HOST_RE + r"/static/favicon\.(?:ico|png)"),
        "../../logov4.jpg",
    ),
    (
        re.compile(r"\{SYS_BASE_URL\}/static/favicon\.(?:ico|png)"),
        "../../logov4.jpg",
    ),
    # 兼容历史：旧 portal 域名引用统一替换为 logo
    (
        re.compile(r"https?://ai\.portal\.hotel\.ctripcorp\.com/baige\.ico"),
        "../../logov4.jpg",
    ),
]
# 跨页面链接：景玩超级助手内网 generated 域名 → pages 公网根（找不到对应页面就退到 pages 首页）
GENERATED_LINK = re.compile(
    INTERNAL_HOST_RE + r"/generated/(?:\d{6}/)?[^\s\"'<>]*"
)

DATE_FROM_NAME = re.compile(r"_(\d{8})(?:_\d{6})?$")

# 用于检测/补齐 favicon link
FAVICON_DETECT = re.compile(r'<link[^>]+rel\s*=\s*["\'][^"\']*icon[^"\']*["\']', re.IGNORECASE)
HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
FALLBACK_FAVICON_TAG = '\n    <link rel="icon" type="image/jpeg" href="../../logov4.jpg">'


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "untitled"


def parse_date_from_filename(stem: str) -> str:
    m = DATE_FROM_NAME.search(stem)
    if m:
        return m.group(1)
    return datetime.now().strftime("%Y%m%d")


def transform_html(content: str) -> str:
    for pat, repl in VENDOR_REWRITE:
        content = pat.sub(repl, content)
    # 跨页面引用一律退到 pages 根（避免 404 的 fragile 行为，无法精确映射时给个安全值）
    content = GENERATED_LINK.sub(PAGES_BASE_URL + "/", content)
    # 兜底：如果 head 里完全没有 favicon link，自动补一个相对路径版本
    if not FAVICON_DETECT.search(content):
        m = HEAD_OPEN.search(content)
        if m:
            insert_at = m.end()
            content = content[:insert_at] + FALLBACK_FAVICON_TAG + content[insert_at:]
    return content


def regenerate_user_home(user_id: str) -> None:
    """扫描 public/<user>/ 下所有 <YYYYMMDD>-* 目录，按日期倒序生成 index.html。"""
    user_dir = PAGES_PUBLIC / user_id
    page_dirs = []
    for d in user_dir.iterdir():
        if not d.is_dir():
            continue
        m = re.match(r"(\d{8})-(.+)", d.name)
        if not m:
            continue
        page_dirs.append((m.group(1), m.group(2), d.name))

    page_dirs.sort(key=lambda x: (x[0], x[1]), reverse=True)

    cards_html = []
    last_date = None
    for date_str, slug, dirname in page_dirs:
        try:
            display_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            display_date = date_str
        if date_str != last_date:
            cards_html.append(f'<div class="date-group">{display_date}</div>')
            last_date = date_str
        title = slug.replace("-", " ")
        cards_html.append(
            f'<a class="page-card" href="./{dirname}/">'
            f'<div class="page-title">{title}</div>'
            f'<div class="page-meta">{dirname}</div>'
            f'</a>'
        )
    cards_block = "\n            ".join(cards_html)

    # user-id → 显示信息（默认就用 user-id）
    user_display = {
        "hua.chen": ("陈华", "携程酒店排序推荐团队 · 排序工程"),
        "wy.teng": ("滕雯阳", "携程酒店排序推荐团队 · 数据分析"),
        "qiuyu.li": ("李秋玉", "携程旅游景玩研发部 · 订单团队"),
    }
    name_zh, role = user_display.get(user_id, (user_id, "景玩超级助手 Pages"))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{user_id} — 景玩超级助手 Pages</title>
    <link rel="icon" type="image/jpeg" href="../logov4.jpg">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
            min-height: 100vh;
            background: linear-gradient(180deg, #f8fafc 0%, #e0f2fe 100%); color: #1e293b;
            padding: 3rem 2rem;
        }}
        .container {{ max-width: 880px; margin: 0 auto; }}
        .header {{ margin-bottom: 2.5rem; }}
        .header a.back {{ color: #64748b; font-size: 0.85rem; text-decoration: none; }}
        .header a.back:hover {{ color: #2563eb; }}
        .header h1 {{ font-size: 2.2rem; font-weight: 700; color: #0f172a; margin-top: 0.4rem; }}
        .header p {{ color: #64748b; font-size: 0.9rem; margin-top: 0.3rem; }}
        .stats {{ font-size: 0.8rem; color: #94a3b8; margin-top: 0.5rem; }}
        .date-group {{
            font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.18em;
            color: #94a3b8; margin: 1.6rem 0 0.6rem; padding-bottom: 0.4rem;
            border-bottom: 1px dashed #e2e8f0;
        }}
        .page-card {{
            display: block; background: #fff; border: 1px solid #e2e8f0;
            border-radius: 10px; padding: 0.9rem 1.1rem; margin-bottom: 0.6rem;
            text-decoration: none; color: inherit;
            transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s;
        }}
        .page-card:hover {{
            border-color: #2563eb; box-shadow: 0 2px 12px rgba(37,99,235,0.1);
            transform: translateX(2px);
        }}
        .page-title {{ font-weight: 500; font-size: 0.95rem; color: #0f172a; }}
        .page-meta {{ font-size: 0.75rem; color: #94a3b8; margin-top: 0.2rem; font-family: ui-monospace, "SF Mono", Menlo, monospace; }}
        .footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 0.75rem; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a class="back" href="../">← 景玩超级助手 Pages</a>
            <h1>{user_id}</h1>
            <p>{name_zh} · {role}</p>
            <div class="stats">共 {len(page_dirs)} 个页面</div>
        </div>
        <div class="page-list">
            {cards_block}
        </div>
        <div class="footer">Powered by GitLab Pages · 景玩超级助手 AI 助手</div>
    </div>
</body>
</html>
"""
    (user_dir / "index.html").write_text(html, encoding="utf-8")


def run_git(args: list[str]) -> tuple[int, str]:
    """在 PAGES_REPO 下运行 git，返回 (returncode, combined_output)。"""
    proc = subprocess.run(
        ["git", "-C", str(PAGES_REPO)] + args,
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish HTML to current repo public/ (GitLab Pages)")
    parser.add_argument("--src-html", required=True, help="本地副本 HTML 绝对路径")
    parser.add_argument("--topic", required=True, help="页面主题，用于生成目录名")
    parser.add_argument("--user-id", default="hua.chen")
    parser.add_argument("--skip-push", action="store_true", help="只复制不 push（调试用）")
    args = parser.parse_args()

    src = Path(args.src_html)
    if not src.exists():
        print(f"src html not found: {src}", file=sys.stderr)
        return 1

    if not PAGES_REPO.exists():
        print(f"pages repo not found: {PAGES_REPO}", file=sys.stderr)
        return 1

    date_str = parse_date_from_filename(src.stem)
    slug = slugify(args.topic)
    dirname = f"{date_str}-{slug}"

    # 同 dirname 已存在时加序号
    user_dir = PAGES_PUBLIC / args.user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    final_dirname = dirname
    i = 2
    while (user_dir / final_dirname).exists():
        final_dirname = f"{dirname}-{i}"
        i += 1

    dst_dir = user_dir / final_dirname
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "index.html"

    try:
        content = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 二进制兜底
        import shutil
        shutil.copy2(src, dst)
    else:
        dst.write_text(transform_html(content), encoding="utf-8")

    regenerate_user_home(args.user_id)

    public_url = f"{PAGES_BASE_URL}/{args.user_id}/{final_dirname}/"

    if args.skip_push:
        print(public_url)
        return 0

    # 先 pull --rebase（这一步在写入文件之前没意义，所以先 stash 当前改动再 pull）
    # 简化方案：先 add 把所有改动入暂存区，再 pull --rebase --autostash
    rc, out = run_git(["add", "public/"])
    if rc != 0:
        print(f"git add failed: {out}", file=sys.stderr)
        return 2

    rc, out = run_git(["pull", "--rebase", "--autostash", "origin", PAGES_BRANCH])
    if rc != 0:
        print(f"git pull failed: {out}", file=sys.stderr)
        return 2

    # rebase 之后改动可能已经 commit/丢弃，重新 add 一次保证状态干净
    rc, out = run_git(["add", "public/"])
    if rc != 0:
        print(f"git add failed: {out}", file=sys.stderr)
        return 2

    commit_msg = f"feat: add {final_dirname} for {args.user_id}"
    rc, out = run_git(["commit", "-m", commit_msg])
    if rc != 0:
        # 没有改动也算成功（可能用户故意重发同内容）
        if "nothing to commit" in out:
            print(public_url)
            return 0
        print(f"git commit failed: {out}", file=sys.stderr)
        return 2

    rc, out = run_git(["push", "origin", PAGES_BRANCH])
    if rc != 0:
        print(f"git push failed: {out}", file=sys.stderr)
        return 2

    print(public_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Refresh merged-PR wall in README.md and merged-prs.svg.

Pulls all merged PRs authored by TINGyu123644, excludes the library-homework PR,
fetches each upstream repo's stargazer count, sorts by stars DESC, and rewrites
the README section delimited by <!--START_SECTION:prs--> / <!--END_SECTION:prs-->.
Also updates the top badge row (merged PR count, net churn, stars reached)
and regenerates the merged-prs.svg contribution wall.
"""
import os
import re
import json
import urllib.request
import urllib.parse
import sys
from datetime import datetime, timezone

TOKEN = os.environ["GITHUB_TOKEN"]
USER = "TINGyu123644"

EXCLUDE = {("mulianyun", "library_management_new", 5)}

PR_META = {
    "langflow-ai/langflow#15411": {
        "emoji": "🏆", "label": "核心功能修复",
        "merger": "@erichare",
        "bullets": [
            "JSON Schema 属性名允许以 `_` 开头，但 Pydantic 把前导下划线字段当私有属性，`create_model()` 直接抛 `NameError`；`update_tools()` 又把异常吞掉——用户看到的是 \"Successfully loaded 0 tools\"。",
            "修复：剥离前导下划线构造安全字段名 → 确定性去重 → 原 wire 名通过 `AliasChoices` 保留；嵌套循环与顶层循环都覆盖。",
            "本地复现：旧 HEAD 必抛 `NameError`，修复后模型构建、校验、`model_dump()` 往返全部通过。",
        ],
    },
    "bytedance/deer-flow#6361": {
        "emoji": "🪟", "label": "跨平台兼容",
        "merger": "@WillemJiang",
        "bullets": [
            "`backend/tests/blocking_io/` 下 12 个锚点在 Windows 上确定性地挂在 `OSError: [Errno 206] Filename too long`，突破了 260 字符 MAX_PATH。",
            "给三个受影响文件加模块级 `pytest.mark.skipif(os.name == \"nt\")`，对齐项目已合并的 `#6257` / `#5931` 约定；POSIX 上照常跑。",
        ],
    },
    "volcengine/OpenViking#6387": {
        "emoji": "🐛", "label": "真实 Bug",
        "merger": "@fujiajie666",
        "bullets": [
            "Docker 部署里 `storage.workspace` 配成相对路径时，每个 `ov compile` 任务在 `stage=sandbox` 直接报 `mkdir: cannot create directory`。",
            "根因：`CompileSandboxManager` 把相对工作区根传进沙箱后端，凭证路径被相对解析了**两次**。",
            "修复：在唯一入口把根目录 `resolve()` 成绝对路径，并加回归测试。",
        ],
    },
    "langgenius/dify#45255": {
        "emoji": "🧪", "label": "测试基建",
        "merger": "@wylswz",
        "bullets": [
            "`api/core/tools/utils/uuid_utils.py` 的 `is_valid_uuid` 此前**零测试覆盖**。",
            "新增 11 个参数化用例：规范连字符、大写、无连字符、带花括号、`urn:uuid:` 前缀 → 全部接受；`None`、空串、普通词、非十六进制字符 → 全部拒绝。",
            "纯增量、不改生产代码；review 轮按 pyrefly `strict` preset 补了 `-> None` 返回类型标注。",
        ],
    },
    "langgenius/dify#45254": {
        "emoji": "🧪", "label": "测试基建",
        "merger": "@asukaminato0721",
        "bullets": [
            "`remove_leading_symbols` 工具函数此前无单元测试覆盖。",
            "新增参数化用例覆盖：前导符号剥离、纯符号输入、混合符号+文字、边界空串等场景。",
            "纯增量测试，不改生产代码。",
        ],
    },
    "langgenius/dify#45225": {
        "emoji": "🐛", "label": "真实 Bug",
        "merger": "@Stream29",
        "bullets": [
            "`parse_and_check_json_markdown` 在模型返回非 dict 结构时，下游代码直接当 dict 取 key 会 `AttributeError`。",
            "修复：解析后显式校验 `isinstance(result, dict)`，不满足直接抛异常，避免脏数据流入工具链。",
            "新增对应回归测试用例。",
        ],
    },
    "langgenius/dify#45261": {
        "emoji": "🧪", "label": "测试基建",
        "merger": "@asukaminato0721",
        "bullets": [
            "RAG document models 的数据模型层此前测试覆盖薄弱。",
            "新增 226 行单元测试，覆盖文档创建、分段、状态流转等核心模型方法。",
            "纯增量测试，不改生产代码。",
        ],
    },
}


def api_get(url):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "tingyu-profile-bot")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fmt_stars(n):
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def build_svg(prs, total_prs, total_stars_str, total_add, total_del):
    """Build the merged-prs.svg contribution wall."""
    # Aggregate by repo
    repo_map = {}
    for p in prs:
        key = f"{p['owner']}/{p['repo']}"
        if key not in repo_map:
            repo_map[key] = {"stars": p["stars"], "count": 0}
        repo_map[key]["count"] += 1

    repo_rows = sorted(repo_map.items(), key=lambda x: x[1]["stars"], reverse=True)
    n_projects = len(repo_rows)

    W = 880
    row_h = 46
    header_h = 44
    top_h = 86
    bottom_pad = 30
    H = top_h + header_h + len(repo_rows) * row_h + bottom_pad

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">')
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

    # Top stat cards: 3 cards
    card_w = 260
    card_gap = 16
    x0 = 24
    cards = [
        ("MERGED PRS", str(total_prs), "#8250df"),
        ("PROJECTS", str(n_projects), "#0969da"),
        ("UPSTREAM ★", total_stars_str, "#bc4c00"),
    ]
    for i, (label, value, color) in enumerate(cards):
        cx = x0 + i * (card_w + card_gap)
        parts.append(f'<rect x="{cx}" y="16" width="{card_w}" height="56" rx="6" fill="#2d333b"/>')
        parts.append(f'<text x="{cx+14}" y="49" fill="#ffffff" font-size="13" font-weight="700" letter-spacing="0.5">{label}</text>')
        parts.append(f'<rect x="{cx+card_w-70}" y="16" width="70" height="56" rx="6" fill="{color}"/>')
        parts.append(f'<text x="{cx+card_w-35}" y="51" fill="#ffffff" font-size="19" font-weight="800" text-anchor="middle">{value}</text>')

    # Table header
    ty = top_h
    parts.append(f'<rect x="24" y="{ty}" width="832" height="{header_h}" fill="#ffffff" stroke="#d0d7de"/>')
    parts.append(f'<text x="48" y="{ty+28}" fill="#24292f" font-size="16" font-weight="700">Project</text>')
    parts.append(f'<text x="573" y="{ty+28}" fill="#24292f" font-size="16" font-weight="700" text-anchor="middle">★ Stars</text>')
    parts.append(f'<text x="756" y="{ty+28}" fill="#24292f" font-size="16" font-weight="700" text-anchor="middle">Merged</text>')

    # Rows
    for i, (repo_name, info) in enumerate(repo_rows):
        ry = ty + header_h + i * row_h
        bg = "#f6f8fa" if i % 2 == 1 else "#ffffff"
        parts.append(f'<rect x="24" y="{ry}" width="832" height="{row_h}" fill="{bg}" stroke="#d0d7de"/>')
        parts.append(f'<text x="48" y="{ry+29}" fill="#0969da" font-size="15" font-weight="500">{repo_name}</text>')
        parts.append(f'<text x="573" y="{ry+29}" fill="#24292f" font-size="15" text-anchor="middle">{fmt_stars(info["stars"])}</text>')
        parts.append(f'<text x="756" y="{ry+29}" fill="#24292f" font-size="15" text-anchor="middle">{info["count"]}</text>')

    # Footer
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fy = ty + header_h + len(repo_rows) * row_h + 12
    parts.append(f'<text x="24" y="{fy}" fill="#57606a" font-size="11">Updated {today} · via GitHub Actions · @TINGyu123644</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def main():
    q = f"author:{USER} is:pr is:merged"
    url = f"https://api.github.com/search/issues?{urllib.parse.urlencode({'q': q, 'per_page': 50})}"
    data = api_get(url)

    prs = []
    for item in data.get("items", []):
        m = re.match(r"https://github\.com/([^/]+)/([^/]+)/(?:pull|issues)/(\d+)", item["html_url"])
        if not m:
            continue
        owner, repo, num = m.group(1), m.group(2), int(m.group(3))
        if (owner, repo, num) in EXCLUDE:
            continue
        prs.append({
            "owner": owner, "repo": repo, "number": num,
            "title": item["title"], "url": item["html_url"],
        })

    for pr in prs:
        rd = api_get(f"https://api.github.com/repos/{pr['owner']}/{pr['repo']}")
        pr["stars"] = rd.get("stargazers_count", 0)
        pd = api_get(f"https://api.github.com/repos/{pr['owner']}/{pr['repo']}/pulls/{pr['number']}")
        pr["additions"] = pd.get("additions", 0)
        pr["deletions"] = pd.get("deletions", 0)
        pr["changed_files"] = pd.get("changed_files", 0)
        pr["merged_at"] = (pd.get("merged_at") or "")[:10]
        pr["merged_by"] = (pd.get("merged_by") or {}).get("login", "maintainer")

    prs.sort(key=lambda x: x["stars"], reverse=True)

    total_prs = len(prs)
    total_add = sum(p["additions"] for p in prs)
    total_del = sum(p["deletions"] for p in prs)
    repo_stars = {}
    for p in prs:
        key = f"{p['owner']}/{p['repo']}"
        repo_stars[key] = p["stars"]
    total_stars = sum(repo_stars.values())
    total_stars_str = fmt_stars(total_stars)

    # --- Build README PR section ---
    out = []
    out.append("## 🏆 已合并上游 PR（按仓库 star 数降序）\n")
    out.append("| # | 仓库 | PR | ⭐ Stars | 增 / 删 | 文件 | 含金量 |")
    out.append("|---|---|---|---|---|---|---|")
    for i, pr in enumerate(prs, 1):
        key = f"{pr['owner']}/{pr['repo']}#{pr['number']}"
        meta = PR_META.get(key, {"emoji": "📌", "label": "merged", "merger": "maintainer", "bullets": []})
        s = fmt_stars(pr["stars"])
        t = pr["title"]
        if len(t) > 60:
            t = t[:57] + "..."
        out.append(
            f"| {i} | [**{pr['owner']}/{pr['repo']}**](https://github.com/{pr['owner']}/{pr['repo']}) "
            f"| [#{pr['number']}]({pr['url']}) — {t} "
            f"| ![{s}](https://img.shields.io/badge/⭐-{s}-181717) "
            f"| ![+{pr['additions']}](https://img.shields.io/badge/+{pr['additions']}-brightgreen) / ![-{pr['deletions']}](https://img.shields.io/badge/-{pr['deletions']}-lightgrey) "
            f"| {pr['changed_files']} | {meta['emoji']} {meta['label']} |"
        )

    out.append("\n### 📖 每条 PR 在修什么\n")
    for pr in prs:
        key = f"{pr['owner']}/{pr['repo']}#{pr['number']}"
        meta = PR_META.get(key, {"emoji": "📌", "label": "merged", "merger": "maintainer", "bullets": []})
        merger_label = meta.get("merger") or f"@{pr['merged_by']}"
        out.append(
            f"#### {meta['emoji']} [#{pr['number']}]({pr['url']}) · "
            f"[{pr['owner']}/{pr['repo']}](https://github.com/{pr['owner']}/{pr['repo']}) — {pr['title'][:50]}"
        )
        out.append(
            f"**合并者 {merger_label} · {pr['merged_at']} · "
            f"+{pr['additions']} / −{pr['deletions']} · {pr['changed_files']} files**\n"
        )
        for b in meta["bullets"]:
            out.append(f"- {b}")
        out.append("\n---\n")

    new_section = "\n".join(out)

    with open("README.md", "r", encoding="utf-8") as f:
        readme = f.read()

    pat = re.compile(r"(<!--START_SECTION:prs-->).*?(<!--END_SECTION:prs-->)", re.DOTALL)
    def repl(m):
        return m.group(1) + "\n" + new_section + "\n" + m.group(2)
    new_readme = pat.sub(repl, readme)

    # --- Update top badges ---
    new_readme = re.sub(
        r"!\[Merged PRs\]\(https://img\.shields\.io/badge/Merged_PRs-[^)]*\)",
        f"![Merged PRs](https://img.shields.io/badge/Merged_PRs-{total_prs}-2ea44f?style=for-the-badge)",
        new_readme,
    )
    new_readme = re.sub(
        r"!\[Stars Reached\]\(https://img\.shields\.io/badge/Upstream_Stars_Reached-[^)]*\)",
        f"![Stars Reached](https://img.shields.io/badge/Upstream_Stars_Reached-{total_stars_str}-181717?style=for-the-badge)",
        new_readme,
    )
    new_readme = re.sub(
        r"!\[Lines\]\(https://img\.shields\.io/badge/Net_CHURN-[^)]*\)",
        f"![Lines](https://img.shields.io/badge/Net_CHURN-+{total_add}__-{total_del}-008080?style=for-the-badge)",
        new_readme,
    )

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(new_readme)

    # --- Generate merged-prs.svg ---
    svg = build_svg(prs, total_prs, total_stars_str, total_add, total_del)
    with open("merged-prs.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Done: {total_prs} PRs across {len(repo_stars)} repos, +{total_add}/-{total_del}, {total_stars_str} stars.")


if __name__ == "__main__":
    main()

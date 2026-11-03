#!/usr/bin/env python3
"""Refresh merged-PR wall in README.md.

Pulls all merged PRs authored by TINGyu123644, excludes the library-homework PR,
fetches each upstream repo's stargazer count, sorts by stars DESC, and rewrites
the README section delimited by <!--START_SECTION:prs--> / <!--END_SECTION:prs-->.

Human-curated 'gold-content' blurbs live in PR_META below; newly merged PRs without
an entry fall back to a generic emoji/label and can be enriched later.
"""
import os
import re
import json
import urllib.request
import urllib.parse
import sys

TOKEN = os.environ["GITHUB_TOKEN"]
USER = "TINGyu123644"

# (owner, repo, number) tuples to exclude from the wall.
EXCLUDE = {("mulianyun", "library_management_new", 5)}

# Hand-curated metadata keyed by f"{owner}/{repo}#{number}".
PR_META = {
    "langflow-ai/langflow#15411": {
        "emoji": "🏆", "label": "核心功能修复",
        "merger": "@erichare",
        "bullets": [
            "JSON Schema 属性名允许以 `_` 开头（Glean 的 `chat`/`search` 工具就这么声明 `_user_goal`），但 Pydantic 把前导下划线字段当私有属性，`create_model()` 直接抛 `NameError`；`update_tools()` 又把这个异常吞掉继续——**用户看到的是 \"Successfully loaded 0 tools\"，全程无报错**。",
            "修复：剥离前导下划线构造 Pydantic 安全字段名 → 确定性去重（不用 `hash()`，避免 `PYTHONHASHSEED` 随机化）→ 原 wire 名通过 `AliasChoices(safe, wire, camelCase)` 保留；嵌套循环与顶层循环都覆盖。",
            "本地复现：Glean 式 schema 在旧 HEAD 必抛 `NameError`，修复后模型构建、按 `_user_goal` 校验、`model_dump()` 往返全部通过。",
        ],
    },
    "bytedance/deer-flow#6361": {
        "emoji": "🪟", "label": "跨平台兼容",
        "merger": "@WillemJiang",
        "bullets": [
            "`backend/tests/blocking_io/` 下 12 个锚点在 Windows 上确定性地挂在 `OSError: [Errno 206] Filename or extension too long`，根本走不到被测逻辑——真实磁盘布局嵌套 + `tmp_path` 前缀突破了 260 字符 MAX_PATH。",
            "给三个受影响文件加模块级 `pytest.mark.skipif(os.name == \"nt\")`，对齐项目已合并的 `#6257` / `#5931` 约定；POSIX 上照常跑，Windows CI 转绿。",
        ],
    },
    "volcengine/OpenViking#6387": {
        "emoji": "🐛", "label": "真实 Bug",
        "merger": "@fujiajie666",
        "bullets": [
            "Docker 部署里 `storage.workspace` 配成相对路径时，每个 `ov compile` 任务在 `stage=sandbox` 直接报 `mkdir: cannot create directory ... No such file or directory`。",
            "根因：`CompileSandboxManager` 把相对工作区根传进沙箱后端，凭证路径被相对解析了**两次**。",
            "修复：在唯一入口 `CompileSandboxManager.__init__` 里把根目录 `resolve()` 成绝对路径，并加回归测试（相对 workspace 下断言凭证路径为绝对路径）。",
        ],
    },
    "langgenius/dify#45255": {
        "emoji": "🧪", "label": "测试基建",
        "merger": "@wylswz",
        "bullets": [
            "`api/core/tools/utils/uuid_utils.py` 的 `is_valid_uuid` 此前**零测试覆盖**（旧测试覆盖的是另一个 `libs/uuid_utils.py`）。",
            "新增 11 个参数化用例：规范连字符、大写、无连字符、带花括号、`urn:uuid:` 前缀 → 全部接受；`None`、空串、普通词、长短一位、非十六进制字符 → 全部拒绝。",
            "纯增量、不改生产代码；review 轮按 pyrefly `strict` preset 补了 `-> None` 返回类型标注。",
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

    prs.sort(key=lambda x: x["stars"], reverse=True)

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
        out.append(
            f"#### {meta['emoji']} [#{pr['number']}]({pr['url']}) · "
            f"[{pr['owner']}/{pr['repo']}](https://github.com/{pr['owner']}/{pr['repo']}) — {pr['title'][:50]}"
        )
        out.append(
            f"**合并者 {meta['merger']} · {pr['merged_at']} · "
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
    if new_readme == readme:
        print("No section marker found; README not modified.")
        sys.exit(1)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(new_readme)

    print(f"README refreshed: {len(prs)} merged PRs, sorted by stars DESC.")


if __name__ == "__main__":
    main()

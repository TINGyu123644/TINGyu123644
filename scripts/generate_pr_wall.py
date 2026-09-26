#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a "Merged PR Wall" SVG for a GitHub profile README.

Usage:
  # Real mode (in GitHub Actions):
  python generate_pr_wall.py --username YOUR_NAME --token $GITHUB_TOKEN --out pr-wall.svg

  # Demo mode (preview with sample data):
  python generate_pr_wall.py --demo --out pr-wall.svg
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone


# ---------- styling ----------
WIDTH = 880
PAD_X = 24

# top stat pills
PILL_H = 56
PILL_GAP = 12
PILL_Y = 16

# colors
DARK_BG = "#2d333b"
TEXT_LIGHT = "#ffffff"
PURPLE = "#8250df"
BLUE = "#0969da"
ORANGE = "#bc4c00"
TABLE_BG = "#ffffff"
HEADER_COLOR = "#24292f"
LINK_COLOR = "#0969da"
BORDER = "#d0d7de"
ROW_ALT = "#f6f8fa"
MUTED = "#57606a"

ROW_H = 46
HEADER_H = 44
TABLE_Y = PILL_Y + PILL_H + 22


def fmt_stars(n: int) -> str:
    if n >= 1000:
        v = n / 1000
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{s}k"
    return str(n)


def github_api(url: str, token) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "pr-wall-generator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_merged_prs(username: str, token) -> list:
    out = []
    page = 1
    while True:
        q = f"author:{username} type:pr is:merged"
        url = (
            "https://api.github.com/search/issues"
            f"?q={urllib.parse.quote(q)}&per_page=100&page={page}"
        )
        data = github_api(url, token)
        items = data.get("items", [])
        out.extend(items)
        if len(items) < 100 or len(out) >= data.get("total_count", 0):
            break
        page += 1
        if page > 10:
            break
    return out


def build_rows(prs: list, token) -> list:
    by_repo = {}
    for pr in prs:
        repo_url = pr.get("repository_url", "")
        full = repo_url.replace("https://api.github.com/repos/", "")
        if not full:
            continue
        by_repo[full] = by_repo.get(full, 0) + 1

    rows = []
    for full, merged in by_repo.items():
        try:
            info = github_api(f"https://api.github.com/repos/{full}", token)
            stars = info.get("stargazers_count", 0)
        except Exception:
            stars = 0
        rows.append({"repo": full, "merged": merged, "stars": stars})

    rows.sort(key=lambda r: (-r["stars"], -r["merged"], r["repo"]))
    return rows


def render_svg(rows: list, username: str, out_path: str) -> None:
    total_prs = sum(r["merged"] for r in rows)
    total_projects = len(rows)
    total_stars = sum(r["stars"] for r in rows)

    table_h = HEADER_H + ROW_H * len(rows)
    height = TABLE_Y + table_h + 24

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" font-family="-apple-system,BlinkMacSystemFont,'
        f'Segoe UI,Helvetica,Arial,sans-serif">'
    )
    parts.append(f'<rect width="{WIDTH}" height="{height}" fill="#ffffff"/>')

    pill_w = (WIDTH - 2 * PAD_X - 2 * PILL_GAP) / 3
    pills = [
        ("MERGED PRS", str(total_prs), PURPLE),
        ("PROJECTS", str(total_projects), BLUE),
        ("UPSTREAM ★", fmt_stars(total_stars), ORANGE),
    ]
    for i, (label, value, vcolor) in enumerate(pills):
        x = PAD_X + i * (pill_w + PILL_GAP)
        label_w = pill_w * 0.72
        value_w = pill_w - label_w
        parts.append(
            f'<rect x="{x:.1f}" y="{PILL_Y}" width="{label_w:.1f}" height="{PILL_H}" '
            f'rx="6" fill="{DARK_BG}"/>'
        )
        parts.append(
            f'<text x="{x + 14:.1f}" y="{PILL_Y + PILL_H/2 + 5:.1f}" '
            f'fill="{TEXT_LIGHT}" font-size="13" font-weight="700" '
            f'letter-spacing="0.5">{label}</text>'
        )
        vx = x + label_w
        parts.append(
            f'<rect x="{vx:.1f}" y="{PILL_Y}" width="{value_w:.1f}" height="{PILL_H}" '
            f'rx="6" fill="{vcolor}"/>'
        )
        parts.append(
            f'<text x="{vx + value_w/2:.1f}" y="{PILL_Y + PILL_H/2 + 7:.1f}" '
            f'fill="{TEXT_LIGHT}" font-size="19" font-weight="800" '
            f'text-anchor="middle">{value}</text>'
        )

    tx = PAD_X
    tw = WIDTH - 2 * PAD_X
    col_repo = tx + 24
    col_star = tx + tw * 0.66
    col_merged = tx + tw * 0.88

    parts.append(
        f'<rect x="{tx}" y="{TABLE_Y}" width="{tw}" height="{HEADER_H}" '
        f'fill="{TABLE_BG}" stroke="{BORDER}"/>'
    )
    parts.append(
        f'<text x="{col_repo}" y="{TABLE_Y + HEADER_H/2 + 6:.1f}" '
        f'fill="{HEADER_COLOR}" font-size="16" font-weight="700">Project</text>'
    )
    parts.append(
        f'<text x="{col_star}" y="{TABLE_Y + HEADER_H/2 + 6:.1f}" '
        f'fill="{HEADER_COLOR}" font-size="16" font-weight="700" text-anchor="middle">★ Stars</text>'
    )
    parts.append(
        f'<text x="{col_merged}" y="{TABLE_Y + HEADER_H/2 + 6:.1f}" '
        f'fill="{HEADER_COLOR}" font-size="16" font-weight="700" text-anchor="middle">Merged</text>'
    )

    for i, row in enumerate(rows):
        ry = TABLE_Y + HEADER_H + i * ROW_H
        bg = ROW_ALT if i % 2 == 1 else TABLE_BG
        parts.append(
            f'<rect x="{tx}" y="{ry}" width="{tw}" height="{ROW_H}" '
            f'fill="{bg}" stroke="{BORDER}"/>'
        )
        parts.append(
            f'<text x="{col_repo}" y="{ry + ROW_H/2 + 6:.1f}" '
            f'fill="{LINK_COLOR}" font-size="15" font-weight="500">{row["repo"]}</text>'
        )
        parts.append(
            f'<text x="{col_star}" y="{ry + ROW_H/2 + 6:.1f}" '
            f'fill="{HEADER_COLOR}" font-size="15" text-anchor="middle">{fmt_stars(row["stars"])}</text>'
        )
        parts.append(
            f'<text x="{col_merged}" y="{ry + ROW_H/2 + 6:.1f}" '
            f'fill="{HEADER_COLOR}" font-size="15" text-anchor="middle">{row["merged"]}</text>'
        )

    parts.append(
        f'<text x="{tx}" y="{height - 8}" fill="{MUTED}" font-size="11">'
        f'Updated {datetime.now(timezone.utc).strftime("%Y-%m-%d")} · '
        f'via GitHub Actions · @{username}</text>'
    )

    parts.append("</svg>")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"[ok] wrote {out_path} ({total_prs} PRs, {total_projects} projects, {total_stars} stars)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=False, default="TINGyu123644")
    ap.add_argument("--token", default=None)
    ap.add_argument("--out", default="merged-prs.svg")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.demo:
        rows = [
            {"repo": "bytedance/deer-flow",        "stars": 82900, "merged": 2},
            {"repo": "MemPalace/mempalace",         "stars": 59200, "merged": 1},
            {"repo": "agentscope-ai/agentscope",    "stars": 32200, "merged": 1},
        ]
        render_svg(rows, args.username, args.out)
        return

    prs = fetch_merged_prs(args.username, args.token)
    rows = build_rows(prs, args.token)
    render_svg(rows, args.username, args.out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""由各 design.md 的 frontmatter 生成 INDEX.md（INDEX.md 的唯一写入者）。

用法：
    python .agents/skills/jw-design/scripts/generate_index.py            # 重新生成 INDEX.md
    python .agents/skills/jw-design/scripts/generate_index.py --check    # 仅检查是否过期（不写文件）

退出码：
    生成模式：0 成功 / 2 内部失败。
    --check ：0 已是最新 / 1 过期需重新生成 / 2 内部失败。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

import lib_frontmatter as lib

_GENERATED_AT_RE = re.compile(r"^<!-- generated-at:.*-->\s*$", re.MULTILINE)

# 索引内分组：标题 + 该组包含的 (stage, status) 过滤条件
STAGE_GROUPS = (
    ("开发前 (proposals)", "proposals", ("draft", "in-review", "changes-requested", "approved")),
    ("开发中 (active)", "active", ("in-development", "on-hold")),
    ("转测中 (testing)", "testing", ("draft", "in-review", "in-testing", "completed", "failed")),
    ("开发后 (archive)", "archive", ("shipped", "superseded", "abandoned")),
    ("已否决 (rejected)", "proposals", ("rejected",)),
    ("转测否决 (testing-rejected)", "testing", ("rejected",)),
)

_COLUMNS = ("ID", "标题", "状态", "负责人", "领域", "版本", "更新日期", "实现状态")


def _cell(value) -> str:
    """单元格文本：None/空 → '—'，并转义竖线。"""
    if value in (None, "", []):
        return "—"
    return lib.coerce_str(value).replace("|", "\\|")


def _impl_status(rec: lib.DocRecord) -> str:
    impl = rec.fm.get("implementation")
    if isinstance(impl, dict) and impl.get("status"):
        return _cell(impl["status"])
    return "—"


def _row(rec: lib.DocRecord) -> str:
    fm = rec.fm
    doc_id = lib.coerce_str(fm.get("id") or rec.folder_id or "?")
    id_link = f"[{doc_id}]({rec.rel_path})"
    cells = (
        id_link,
        _cell(fm.get("title")),
        _cell(fm.get("status")),
        _cell(fm.get("owner")),
        _cell(fm.get("domain")),
        _cell(fm.get("version")),
        _cell(fm.get("updated")),
        _impl_status(rec),
    )
    return "| " + " | ".join(cells) + " |"


def _status_sort_key(rec: lib.DocRecord, status_order: tuple[str, ...]):
    status = lib.coerce_str(rec.fm.get("status", ""))
    rank = status_order.index(status) if status in status_order else len(status_order)
    return (rank, rec.folder)


def build_index(records: list[lib.DocRecord], timestamp: str) -> str:
    valid = [r for r in records if not r.parse_error]
    skipped = [r for r in records if r.parse_error]

    # 计数（按四个展示分组）
    counts = []
    grouped: dict[str, list[lib.DocRecord]] = {}
    for title, stage_dir, statuses in STAGE_GROUPS:
        rows = [
            r
            for r in valid
            if r.stage_dir == stage_dir and lib.coerce_str(r.fm.get("status", "")) in statuses
        ]
        rows.sort(key=lambda r: _status_sort_key(r, statuses))
        grouped[title] = rows
        counts.append(f"{title.split(' ')[0]} {len(rows)}")

    out: list[str] = []
    out.append("<!-- 本文件由 .agents/skills/jw-design/scripts/generate_index.py 自动生成，请勿手改。重新生成：python .agents/skills/jw-design/scripts/generate_index.py -->")
    out.append(f"<!-- generated-at: {timestamp} -->")
    out.append("")
    out.append("# 设计文档索引 (INDEX)")
    out.append("")
    out.append("> " + " · ".join(counts))
    out.append("")

    header = "| " + " | ".join(_COLUMNS) + " |"
    sep = "|" + "|".join(["---"] * len(_COLUMNS)) + "|"

    for title, _stage_dir, _statuses in STAGE_GROUPS:
        rows = grouped[title]
        out.append(f"## {title}")
        out.append("")
        if rows:
            out.append(header)
            out.append(sep)
            out.extend(_row(r) for r in rows)
        else:
            out.append("（暂无）")
        out.append("")

    if skipped:
        out.append("## ⚠ 无法解析（已跳过，请运行 validate 修复）")
        out.append("")
        for r in skipped:
            out.append(f"- `{r.rel_path}` — {r.parse_error}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def _normalize(text: str) -> str:
    """剔除易变的 generated-at 行，用于 --check 比对。"""
    return _GENERATED_AT_RE.sub("", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="由 frontmatter 生成 INDEX.md")
    parser.add_argument("--root", type=Path, default=None, help="设计资产根目录（默认 .agents/agent-docs/designs）")
    parser.add_argument("--check", action="store_true", help="仅检查是否过期，不写文件")
    args = parser.parse_args(argv)

    try:
        root = args.root or lib.repo_root()
        records = lib.iter_docs(root, None)
        timestamp = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8))).isoformat(timespec="minutes")
        content = build_index(records, timestamp)
        index_path = root / lib.INDEX_FILE

        if args.check:
            if not index_path.is_file():
                print("INDEX.md 不存在，需要生成。", file=sys.stderr)
                return 1
            current = index_path.read_text(encoding="utf-8")
            if _normalize(current) == _normalize(content):
                print("✓ INDEX.md 已是最新。")
                return 0
            print("✗ INDEX.md 已过期，请运行：python .agents/skills/jw-design/scripts/generate_index.py", file=sys.stderr)
            return 1

        index_path.write_text(content, encoding="utf-8")
        print(f"✓ 已生成 {lib.INDEX_FILE}（{len([r for r in records if not r.parse_error])} 篇文档）。")
        return 0
    except Exception as exc:  # noqa: BLE001 - 顶层兜底
        print(f"内部错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""域对照表：「行域 × 列域」的期望伤害矩阵。

口径（用户确认）：
* **每一行 = 一个文件**（该文件里只有一个域，且那个域内有「★结果」卡片）；
* **每一列 = 一个文件**（同样只含一个域，作为拐力来源）；
* **左上角 = 固定拐力**：再选一个域，它给的 ``out::`` 对**所有**组合都加一次；
* 单元格 = 「行角色」在「该列域的 out:: ＋ 固定域的 out::」作用下的 **期望伤害**。

实现：行文件本身是一个完整工程（有自己的 ★结果 / 链条），把它读进来求值，
再通过 ``Graph.extra_buffs`` 把列 + 固定域的 ``out::`` 注入到行角色上。
拐力只作用于直接目标（不传递），所以这道注入不会顺着行文件内部的箭头继续传。
"""

from __future__ import annotations

import json
import os

from . import external as _external

__all__ = ["build", "parse_spec"]

DASH = "—"


def parse_spec(text: str) -> list:
    """一行一个来源，格式同「外部域」：``文件`` 或 ``文件::域``。"""
    return _external.parse_sources(text)


def _source_label(path: str, role: str) -> str:
    return _external.source_label(path, role)


def _load(path: str, role: str, base_dir, extra_bases) -> tuple:
    """读一个来源：``(.resolve 后的绝对路径, 域名字, {out::名字: 值})``；读不到返回空串。"""
    full = _external.resolve(path, base_dir, extra_bases)
    if not full:
        return ("", "", {})
    names, per_role = _external.load(path, base_dir, extra_bases)
    actual = role or (names[0] if len(names) == 1 else "")
    if not actual:
        return (full, "", {})
    return (full, actual, dict(per_role.get(actual) or {}))


def _expected(full: str, role: str, grants: dict) -> float | None:
    """把 ``grants`` 注入到 ``full`` 这个工程里的 ``role`` 上，返回其 ★结果 的期望值。"""
    from .graph import Graph

    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    try:
        graph = Graph.from_dict(data)
        graph.base_dir = os.path.dirname(full)
        graph.extra_bases = []
        graph.extra_buffs = {role: dict(grants)} if role else {}
        out = graph.evaluate()
    except Exception:                                    # 行文件坏了就当一个空格子
        return None
    result = out.get("result") or {}
    values = result.get("values")
    if not values:
        return None                                      # 没有 ★结果（或没接到链上）
    try:
        return float(values["expected"])
    except (KeyError, TypeError, ValueError):
        return None


def build(rows_text: str, cols_text: str, fixed_text: str,
          base_dir=None, extra_bases=()) -> list:
    """生成矩阵（第一行是表头，可直接给前端的表格卡片）。"""
    rows = parse_spec(rows_text)
    cols = parse_spec(cols_text)
    fixed = parse_spec(fixed_text)
    fixed_grants: dict = {}
    fixed_labels: list = []
    # 固定拐力可以多选（用户要求）：多来源同名**相加**，角标把名字列出来
    for path, role in fixed:
        full, actual, grants = _load(path, role, base_dir, extra_bases)
        if not (full and actual):
            fixed_labels.append(_source_label(path, role))
            continue
        fixed_labels.append(_source_label(path, actual))
        for name, val in grants.items():
            fixed_grants[name] = fixed_grants.get(name, 0.0) + float(val)
    fixed_label = " + ".join(fixed_labels)

    header = [fixed_label or "行 \\ 列"]
    col_loaded = []
    for path, role in cols:
        full, actual, grants = _load(path, role, base_dir, extra_bases)
        col_loaded.append((full, actual, grants))
        header.append(_source_label(path, actual) if full and actual else DASH)

    table = [header]
    for path, role in rows:
        full, row_role, _own = _load(path, role, base_dir, extra_bases)
        row_label = _source_label(path, row_role) if full and row_role else DASH
        line = [row_label if row_label != DASH else _source_label(path, role)]
        for _cfull, _crole, grants in col_loaded:
            if not full or not row_role or not _crole:
                line.append(DASH)
                continue
            merged = dict(fixed_grants)
            for name, val in grants.items():
                merged[name] = merged.get(name, 0.0) + float(val)
            got = _expected(full, row_role, merged)
            line.append(_fmt(got))
        table.append(line)
    return table


def _fmt(value) -> str:
    """单元格文字：数字用与界面一致的格式，读不到就给个短横。"""
    if value is None:
        return DASH
    from .expr import fmt_num

    return fmt_num(value)

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
    # **要取指定域的那张 ★结果**：一个文件里可能有多个域（各有自己的结果卡），
    # out["result"] 只代表"第一张连上的结果卡"，拿它会把别的域的伤害算进来
    # （用户报的 `data/米c0::factor7` 算出 factor9 的数就是这么来的）。
    nodes_out = out.get("nodes") or {}
    picked = None
    if role:
        for nid, info in nodes_out.items():
            if info.get("type") != "result":
                continue
            node = graph.nodes.get(nid)
            if node is not None and node.role == role:
                picked = info
                break
    if picked is None:
        picked = out.get("result") or {}
    values = picked.get("values")
    if not values:
        return None                                      # 没有 ★结果（或没接到链上）
    try:
        return float(values["expected"])
    except (KeyError, TypeError, ValueError):
        return None


def build(rows_text: str, cols_text: str, fixed_text: str,
          base_dir=None, extra_bases=(), arrow_grants=None,
          with_values: bool = False):
    """生成矩阵（第一行是表头，可直接给前端的表格卡片）。

    ``with_values=True`` 时返回 ``(table, values)``：``values`` 是同样形状的
    **原始数值**（``None`` = 读不到）。表格里是格式化过的字符串，算百分比要用原值。
    """
    rows = parse_spec(rows_text)
    cols = parse_spec(cols_text)
    fixed = parse_spec(fixed_text)
    fixed_grants: dict = {}
    fixed_labels: list = []
    # 指到卡片接入点的箭头（来自外部域 / 角色 / 武器域）也当固定拐力：
    #   all = 左上角（全局）、rows[i] = 第 i 行、cols[j] = 第 j 列；同一格三者相加
    arrow = arrow_grants or {}
    all_grants = dict((arrow.get("all") or {}) if isinstance(arrow, dict) else {})
    row_grants = (arrow.get("rows") or {}) if isinstance(arrow, dict) else {}
    col_grants = (arrow.get("cols") or {}) if isinstance(arrow, dict) else {}
    for name, val in all_grants.items():
        fixed_grants[name] = fixed_grants.get(name, 0.0) + float(val)
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
    values: list = []                       # 与 table 同形（首行是表头，用不上）
    for row_index, (path, role) in enumerate(rows):
        full, row_role, _own = _load(path, role, base_dir, extra_bases)
        row_label = _source_label(path, row_role) if full and row_role else DASH
        line = [row_label if row_label != DASH else _source_label(path, role)]
        value_line: list = [row_label]
        for col_index, (_cfull, _crole, grants) in enumerate(col_loaded):
            if not full or not row_role or not _crole:
                line.append(DASH)
                continue
            merged = dict(fixed_grants)
            # 行接入点 / 列接入点带来的拐力：只作用于这一行 / 这一列
            for extra in (row_grants.get(row_index) or {},
                          col_grants.get(col_index) or {},
                          grants):
                for name, val in extra.items():
                    merged[name] = merged.get(name, 0.0) + float(val)
            got = _expected(full, row_role, merged)
            line.append(_fmt(got))
            value_line.append(got)
        table.append(line)
        values.append(value_line)
    if with_values:
        return table, values
    return table


def _fmt(value) -> str:
    """单元格文字：数字用与界面一致的格式，读不到就给个短横。"""
    if value is None:
        return DASH
    from .expr import fmt_num

    return fmt_num(value)


def ratio_table(values: list, base_cell: str) -> list:
    """每格相对**基准单元格**的百分比（``rows[i][j]`` 与表格同形，0 或 None = 没有）。

    ``base_cell`` 形如 ``"1,2"``（第 1 行第 2 列，行列都从 0 开始，**不含表头**）。
    基准格自己是 100%；读不到的格子给 None。基准没设 / 设的值是 0 → 全部 None。
    """
    try:
        row, col = [int(part) for part in str(base_cell or "").split(",")]
    except (TypeError, ValueError):
        return []
    if row < 0 or col < 0 or row >= len(values) or col >= len(values[row]) - 1:
        return []
    base = values[row][col + 1] if values[row] else None
    if not base:
        return []
    out = []
    for line in values:
        out.append([
            (float(v) / float(base) * 100.0) if v else None
            for v in line[1:]
        ])
    return out


# 手动计算的结果缓存：{(输入, 拐力签名, run_id): (table, values)}
# 用户点一次「计算」换一个 run_id → 重算一次；之后同一 run_id 的求值直接复用
# （拖卡片、改别的字段都会触发整图求值，没必要每次都把矩阵重读一遍文件）。
_RESULT_CACHE: dict = {}


def _grants_key(grants) -> tuple:
    """拐力结构 → 可哈希的签名（用于缓存键）。"""
    data = grants or {}
    if not isinstance(data, dict):
        return ()
    return (
        tuple(sorted((str(k), float(v)) for k, v in (data.get("all") or {}).items())),
        tuple(sorted(
            (int(i), tuple(sorted((str(k), float(v)) for k, v in (g or {}).items())))
            for i, g in (data.get("rows") or {}).items()
        )),
        tuple(sorted(
            (int(i), tuple(sorted((str(k), float(v)) for k, v in (g or {}).items())))
            for i, g in (data.get("cols") or {}).items()
        )),
    )


def build_cached(rows_text: str, cols_text: str, fixed_text: str, run_id: str,
                 base_dir=None, extra_bases=(), arrow_grants=None):
    """按 ``run_id`` 缓存结果的手动计算：同一个 run_id 只算一次。"""
    key = (
        str(rows_text or ""), str(cols_text or ""), str(fixed_text or ""),
        str(base_dir or ""), tuple(str(b) for b in (extra_bases or ())),
        _grants_key(arrow_grants), str(run_id or ""),
    )
    hit = _RESULT_CACHE.get(key)
    if hit is not None:
        return hit
    table, values = build(rows_text, cols_text, fixed_text, base_dir, extra_bases,
                          arrow_grants=arrow_grants, with_values=True)
    if len(_RESULT_CACHE) > 32:            # 只留最近的一批
        _RESULT_CACHE.clear()
    _RESULT_CACHE[key] = (table, values)
    return table, values


def clear_cache() -> None:
    """清空结果缓存（测试用）。"""
    _RESULT_CACHE.clear()

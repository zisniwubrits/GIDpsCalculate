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


def _row_graph(full: str, role: str, grants: dict):
    """把 ``grants`` 注入到 ``full`` 这个工程里的 ``role`` 上求值，返回 ``(graph, out)``。

    读不到 / 求值炸了 → ``(None, None)``（调用方按"这格空着"处理）。
    """
    from .graph import Graph

    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None, None
    try:
        graph = Graph.from_dict(data)
        graph.base_dir = os.path.dirname(full)
        graph.extra_bases = []
        graph.extra_buffs = {role: dict(grants)} if role else {}
        out = graph.evaluate()
    except Exception:
        return None, None
    return graph, out


def _expected(full: str, role: str, grants: dict) -> float | None:
    """把 ``grants`` 注入到 ``full`` 这个工程里的 ``role`` 上，返回其 ★结果 的期望值。"""
    graph, out = _row_graph(full, role, grants)
    if graph is None or out is None:
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


def _merged_cell_grants(fixed_grants, arrow_grants, row_grants, col_grants, col_own):
    """一个单元格吃到的全部拐力：固定 + 全局箭头 + 该行 + 该列 + 列文件自己的 out::。"""
    merged = dict(fixed_grants)
    for extra in (row_grants or {}, col_grants or {}, col_own or {}):
        for name, val in extra.items():
            merged[name] = merged.get(name, 0.0) + float(val)
    return merged


def _own_terms(rfull: str, role: str, graph) -> dict:
    """``{宏: [(算式项文本, 数值)]}``：把该域 `own::名字 = a+b+c` 的算式拆成词条项。

    面板里的"值"常常是 `own::atk_pct = 24 + 27.6 + 34.8*2 + 46.6` 这种把圣遗物词条
    逐项相加的写法；这里按 **加号** 拆开，逐项在求值环境里算一遍（算不出来的项只留文本）。
    """
    import re as _re

    from . import nodes as _nodes

    try:
        with open(rfull, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    texts = []
    for node in data.get("nodes") or []:
        fields = node.get("fields") or {}
        if node.get("type") == "var":
            texts.append(str(fields.get("defs") or ""))
        elif node.get("type") in ("role", "weapon"):
            texts.append(str(fields.get("panel") or ""))
    out: dict = {}
    pattern = _re.compile(
        r"^[ \t]*own[ \t]*::[ \t]*([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)[ \t]*=[ \t]*(.+)$")
    for text in texts:
        for line in text.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            name, expr = match.group(1), match.group(2).strip()
            terms = [part.strip() for part in expr.split("+") if part.strip()]
            token = _nodes.use_env(dict(getattr(graph, "variables", {}) or {}))
            values = []
            try:
                for part in terms:
                    try:
                        values.append((part, float(_nodes.eval_field(part))))
                    except ValueError:
                        values.append((part, None))
            finally:
                _nodes.reset_env(token)
            out[name] = values
    return out


def cell_panel(rows_text: str, cols_text: str, fixed_text: str,
               row_index: int, col_index: int, base_dir=None, extra_bases=(),
               arrow_grants=None) -> dict:
    """某个单元格的「角色面板」：**汇总了该行 / 该列 / 全局拐力之后**的宏表。

    右键单元格用（用户要求）。返回::

        {"title": "米c0.factor7 ｜ 奥c0.odette",
         "rows": [{"key","label","value","incoming"}…],   # incoming = 收到的拐
         "out":  [{"macro","label","value"}…]}            # 它给出去的拐（非 0 的）
    """
    from .nodes import PANEL_MACROS, PANEL_MACRO_KEYS
    from .expr import fmt_num

    rows = parse_spec(rows_text)
    cols = parse_spec(cols_text)
    if row_index < 0 or col_index < 0 or row_index >= len(rows) or col_index >= len(cols):
        return {}
    fixed_grants: dict = {}
    contrib: dict = {}                    # {宏: [(来源标签, 值)]}：词条来源统计用

    def note(name: str, val, label: str) -> None:
        if not val:
            return
        contrib.setdefault(name, []).append((label, float(val)))

    fixed = parse_spec(fixed_text)
    for path, role in fixed:
        _full, actual, grants = _load(path, role, base_dir, extra_bases)
        if actual:
            label = _source_label(path, actual)
            for name, val in grants.items():
                fixed_grants[name] = fixed_grants.get(name, 0.0) + float(val)
                note(name, val, label)
    arrow = arrow_grants or {}
    for name, val in (arrow.get("all") or {}).items():
        fixed_grants[name] = fixed_grants.get(name, 0.0) + float(val)
        note(name, val, "箭头")

    rfull, rrole, _rgrants = _load(*rows[row_index], base_dir, extra_bases)
    _cfull, crole, cgrants = _load(*cols[col_index], base_dir, extra_bases)
    if not (rfull and rrole):
        return {}
    row_extra = (arrow.get("rows") or {}).get(row_index)
    col_extra = (arrow.get("cols") or {}).get(col_index)
    for extra, label in ((row_extra, "箭头（行）"), (col_extra, "箭头（列）"),
                         (cgrants, _source_label(cols[col_index][0], crole) if crole else DASH)):
        for name, val in (extra or {}).items():
            note(name, val, label)
    merged = _merged_cell_grants(
        fixed_grants, arrow, row_extra, col_extra, cgrants,
    )
    graph, _out = _row_graph(rfull, rrole, merged)
    if graph is None:
        return {}
    values = graph.variables
    own_terms = _own_terms(rfull, rrole, graph)
    rows_out = []
    sources_out = []                      # 词条来源：一行一个（属性 / 数值 / 来源）
    for key in PANEL_MACRO_KEYS:
        # 变量表里的键是 `角色__宏`（内部用 __ 拼），不是展示用的 `角色::宏`
        raw = values.get("%s__%s" % (rrole, key))
        incoming = float(merged.get(key) or 0.0)
        empty = raw is None or abs(float(raw)) < 1e-9
        if empty and not incoming:
            continue                     # 这一项既没有值也没收到拐：不占一行
        label = next((lb for k, lb, _f in PANEL_MACROS if k == key), key)
        rows_out.append(dict(
            key=key, label=label,
            value="" if raw is None else fmt_num(float(raw)),
            incoming=incoming,
            self_terms=[dict(text=text, value=value) for text, value in own_terms.get(key, [])],
            grants=[dict(source=label2, value=value) for label2, value in contrib.get(key, [])],
        ))
        # 词条来源拍平：自身那部分单独一行，每条拐力各一行（与角色面板的拐力列表同形）
        own_part = (float(raw) - incoming) if raw is not None else 0.0
        if abs(own_part) > 1e-9:
            sources_out.append(dict(macro=key, label=label, value=own_part, source="自身"))
        for label2, value in contrib.get(key, []):
            sources_out.append(dict(macro=key, label=label, value=float(value), source=label2))
    outgoing = []
    for name in _out_names(graph, rrole):
        val = float(graph.role_out_value(values, rrole, name) or 0.0)
        if not val:
            continue
        label = next((lb for k, lb, _f in PANEL_MACROS if k == name), name)
        outgoing.append(dict(macro=name, label=label, value=val))
    return dict(
        title="%s ｜ %s" % (_source_label(rows[row_index][0], rrole),
                            _source_label(cols[col_index][0], crole) if crole else DASH),
        rows=rows_out,
        sources=sources_out,
        out=[item for item in outgoing if item["value"]],
    )


def _out_names(graph, role: str) -> list:
    """该域声明过的 out:: 名字（读变量表里的 ``角色__out__*`` 键）。"""
    prefix = role + "::"
    names = set()
    for key in graph.variables:
        shown = key.replace("__", "::")
        if shown.startswith(prefix + "out::"):
            names.add(shown[len(prefix) + 5:])
    return sorted(names)

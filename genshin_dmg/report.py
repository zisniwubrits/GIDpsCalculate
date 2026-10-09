# -*- coding: utf-8 -*-
"""可读文本报告（「导出结果」按钮）。

把整张画布的卡片参数、连线、结果与节点求值过程拼成一份纯文本，
便于贴给别人或存档。纯逻辑，不依赖 UI。
"""

from __future__ import annotations

import datetime

from genshin_dmg.expr import fmt_num
from genshin_dmg.graph import Graph
from genshin_dmg.nodes import NODE_TYPES, field_specs

__all__ = ["snapshot", "describe", "result_lines", "build_report",
           "default_filename", "variables_text", "APP_TITLE"]

APP_TITLE = "原神 · 直伤伤害计算"
_LINE = "=" * 48


def snapshot(graph: Graph):
    """采集画布快照 → ``[(分组, [(标签, 值)])]``。"""
    rows = []
    for nid, node in graph.nodes.items():
        spec = NODE_TYPES[node.type]
        vals = []
        for f in field_specs(node.type):
            vals.append("%s=%s" % (f["label"], node.fields.get(f["key"], "")))
        rows.append((nid, "[%s] @(%d,%d) %s" % (
            spec["title"], node.pos[0], node.pos[1], " ".join(vals))))
    links = ["%s -> %s.in%d" % (l.src, l.dst, l.port) for l in graph.links]
    return [
        ("节点卡片", rows),
        ("连线", [("link%d" % i, s) for i, s in enumerate(links)]),
    ]


def describe(graph: Graph, out: dict) -> list:
    """从结果卡片反向溯源的节点求值顺序（缩进表示上游）。"""
    res = graph.result_node()
    if res is None:
        return ["（无结果卡片）"]
    lines, seen = [], set()

    def walk(nid, depth):
        if nid in seen:
            return
        seen.add(nid)
        for p in range(graph.input_count(nid)):
            s = graph.link_src(nid, p)
            if s:
                walk(s, depth + 1)
        info = (out.get("nodes") or {}).get(nid) or {}
        if info.get("values"):
            v = info["values"]
            txt = "未暴击 %s / 暴击 %s / 期望 %s" % (
                fmt_num(v["noncrit"]), fmt_num(v["crit"]), fmt_num(v["expected"]))
            if info.get("factor"):
                txt = "%s ｜ %s" % (info["factor"], txt)
        elif info.get("error"):
            txt = "(错误: %s)" % info["error"]
        else:
            txt = info.get("display") or "（无输出）"
        lines.append("%s%s  →  %s" % ("    " * depth, graph.nodes[nid].title, txt))

    walk(res, 0)
    return lines


def result_lines(graph: Graph, out: dict) -> list:
    """结果区块（与界面上显示的一致）。"""
    if out.get("ok") and out.get("result"):
        v = out["result"]["values"]
        lines = [
            "【结果】",
            "未暴击伤害 : %s" % fmt_num(v["noncrit"]),
            "暴击伤害   : %s" % fmt_num(v["crit"]),
            "期望伤害   : %s   (有效暴击封顶100%%)" % fmt_num(v["expected"]),
        ]
        names = out["result"].get("boundNames") or []
        if names:
            lines.append("绑定变量   : %s" % " / ".join(names))
        for w in out.get("warnings") or []:
            lines.append("提示：%s" % w)
        return lines
    if out.get("error") and "结果" in str(out["error"]):
        return [
            "【提示】画布中还没有「★结果」卡片：",
            "各卡片仍会显示自身系数与输出；把链尾连到 ★结果 即可汇总伤害。",
        ]
    return ["【无法计算】%s" % (out.get("error") or "未知错误")]


def build_report(graph: Graph, title: str = APP_TITLE, timestamp=None,
                 out: dict | None = None) -> str:
    """把输入快照与结果拼成可读的报告文本。"""
    out = graph.evaluate() if out is None else out
    now = timestamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [_LINE, "  " + title, "  保存时间：" + now, _LINE]
    for gname, items in snapshot(graph):
        rows.append("【%s】" % gname)
        for label, value in items:
            rows.append("  %-16s : %s" % (label, value))
        rows.append("")
    rows.append(_LINE)
    rows.append("【计算结果与完整过程】")
    rows.extend(result_lines(graph, out))
    rows.append("-" * 22)
    rows.append("【节点求值过程（从结果反向溯源）】")
    rows.extend(describe(graph, out))
    rows.append(_LINE)
    return "\n".join(rows)


def default_filename(prefix: str = "直伤伤害", now=None) -> str:
    """默认文件名（带时间戳，避免覆盖）。"""
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M%S")
    return "%s_%s.txt" % (prefix, stamp)


def variables_text(graph: Graph, out: dict | None = None) -> str:
    """变量表的纯文本形式（复制用）。"""
    out = graph.evaluate() if out is None else out
    if not out["variables"]:
        return "变量\t值\n（暂无变量）\t"
    return "变量\t值\n" + "\n".join(
        "%s\t%s" % (v["name"], v["text"]) for v in out["variables"])

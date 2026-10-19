# -*- coding: utf-8 -*-
"""圣遗物 ↔ 主程序 的**适配层**（唯一允许 import ``graph.py`` 的地方）。

职责只有两件事，都是"把工程变成数字/程序"：

* :class:`GraphDamageFn` / :func:`damage_fn_from_project` —— **解释层**伤害函数：
  9 个属性 → 跑一遍现有工程链 → 期望伤害。这就是将来 DLL 的基准实现。
* :func:`compile_project` —— 工程 → **程序**（阶段列表 + RPN），交给
  :func:`relic_program.run_expected` 或通用 DLL 执行。

边界（见 ``AGENTS.md`` §10）：跨边界的只有 ``list[float]`` / ``dict`` / ``float``；
不往上层传 Graph、传卡片。``relic.py`` 与 ``relic_program.py`` **不得** import 本模块。
"""

from __future__ import annotations

import json

from . import relic_math as _math
from .relic import STATS_ORDER
from .relic_program import (
    NotCompilable,
    OP_ADD,
    OP_BASE,
    OP_CRIT,
    OP_DEF,
    OP_MUL,
    OP_RES,
    OP_RESULT,
    _CORE,
    _emit,
)

__all__ = ["GraphDamageFn", "damage_fn_from_project", "compile_project"]


# ---- 解释层：9 个属性 → 期望伤害 -----------------------------------------
class GraphDamageFn:
    """**解释层**实现：``stats(9 个 float) → 期望伤害``，内部跑现有工程链。

    这是 DLL 的基准实现（慢但绝对可信）：属性以 ``Graph.extra_own`` 注入该角色
    （算作"自身"，进 ``own::``），再取该角色 ★结果卡的 ``expected``。

    * ``calc(xs)``：单次，返回 ``float``；
    * ``calc_batch(rows)``：批量，``rows`` 是 ``len(xs)//9`` 组扁平输入（行优先），返回 ``list[float]``；
    * 长度不对 / 非有限数 → ``ValueError``（不静默返回 0）。
    """

    def __init__(self, graph, role: str):
        from genshin_dmg.graph import Graph

        self.graph = graph if isinstance(graph, Graph) else Graph.from_dict(graph or {})
        self.role = role
        self.stats_order = STATS_ORDER
        node_id = ""
        for node in self.graph.nodes.values():
            if node.type != "result":
                continue
            if role and getattr(node, "role", "") == role:
                node_id = node.id
                break
            if not role and node_id == "":
                node_id = node.id          # role="" → 用第一张 ★结果 卡
        if not node_id:
            raise ValueError("工程里没有 %s 的 ★结果 卡"
                             % ("属于 %s" % role if role else "任何"))
        self.node_id = node_id

    # -- 内部 --------------------------------------------------------------
    @staticmethod
    def _check(xs) -> list:
        values = [float(value) for value in xs]
        if len(values) != len(STATS_ORDER):
            raise ValueError("输入必须是 %d 个属性（收到 %d 个）"
                             % (len(STATS_ORDER), len(values)))
        for value in values:
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("属性不能是 NaN / inf：%r" % (values,))
        return values

    def _calc_values(self, values: list) -> float:
        self.graph.extra_own = {self.role: dict(zip(STATS_ORDER, values))}
        out = self.graph.evaluate()
        node = (out.get("nodes") or {}).get(self.node_id) or {}
        result = (node.get("values") or {}).get("expected")
        if result is None:
            raise ValueError("★结果卡没有算出 expected")
        return float(result)

    # -- 接口 --------------------------------------------------------------
    def calc(self, xs) -> float:
        """单次：9 个属性 → 期望伤害。"""
        return self._calc_values(self._check(xs))

    def calc_batch(self, rows) -> list:
        """批量：``rows`` 是行优先的扁平序列（长度 = 组合数 × 9）→ 每组的伤害。"""
        flat = [float(value) for value in rows]
        width = len(STATS_ORDER)
        if len(flat) % width:
            raise ValueError("批量输入长度必须是 %d 的整数倍（收到 %d）"
                             % (width, len(flat)))
        out = []
        for start in range(0, len(flat), width):
            out.append(self._calc_values(self._check(flat[start:start + width])))
        return out


def damage_fn_from_project(project, role: str) -> GraphDamageFn:
    """从工程（dict 或文件路径）造一个伤害函数（解释层）。"""
    if isinstance(project, str):
        with open(project, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = project
    return GraphDamageFn(data, role)


# ---- 编译层：工程 → 程序 --------------------------------------------------
def _role_result(graph, role: str):
    first = None
    for node in graph.nodes.values():
        if node.type != "result":
            continue
        if role and getattr(node, "role", "") == role:
            return node
        if first is None:
            first = node
    if first is None:
        raise NotCompilable("工程里没有 ★结果 卡")
    if role:
        raise NotCompilable("工程里没有属于 %s 的 ★结果 卡" % role)
    return first


def _compile_node(graph, nid: str, resolve, seen=()) -> list:
    """递归编译某个节点的整条子链，返回阶段列表。

    「加法合并」有多个输入：每个输入各自编译成子程序，运行时分量相加。
    """
    if nid in seen:
        raise NotCompilable("链里有环")
    node = graph.nodes.get(nid)
    if node is None:
        raise NotCompilable("链上缺少节点: %s" % nid)
    if node.type not in _CORE:
        raise NotCompilable("暂不支持编译卡片类型: %s" % node.type)

    def field(key, default="0"):
        raw = node.getter()(key)
        return default if raw is None or (isinstance(raw, str) and not raw.strip()) else raw

    if node.type == "add":
        count = graph.input_count(nid)
        branches = []
        for port in range(count):
            src = graph.link_src(nid, port)
            if src:
                branches.append(_compile_node(graph, src, resolve, seen + (nid,)))
        if not branches:
            raise NotCompilable("「加法合并」没有输入")
        return [dict(op=OP_ADD, branches=branches)]

    upstream = graph.link_src(nid, 0)
    stages = _compile_node(graph, upstream, resolve, seen + (nid,)) if upstream else []

    if node.type == "base":
        expr = _emit(field("stat_base"), resolve)
        expr += _emit(field("stat_big"), resolve) + [("const", 100.0), ("div",),
                                                    ("const", 1.0), ("add",), ("mul",)]
        expr += _emit(field("stat_flat"), resolve) + [("add",)]
        expr += _emit(field("multiplier", "200"), resolve) + [("const", 100.0), ("div",), ("mul",)]
        stages.append(dict(op=OP_BASE, expr=expr))
    elif node.type == "dmg":
        expr = _emit(field("dmg_net"), resolve) + [("const", 100.0), ("div",),
                                                   ("const", 1.0), ("add",)]
        stages.append(dict(op=OP_MUL, expr=expr))
    elif node.type == "res":
        stages.append(dict(op=OP_RES, expr=_emit(field("resistance", "10"), resolve)))
    elif node.type == "def":
        stages.append(dict(op=OP_DEF, exprs=[
            _emit(field("char_level", "90"), resolve),
            _emit(field("enemy_level", "90"), resolve),
            _emit(field("def_reduction", "0"), resolve),
            _emit(field("ignore_def", "0"), resolve),
        ]))
    elif node.type == "crit":
        stages.append(dict(op=OP_CRIT,
                           rate=_emit(field("crit_rate", "50"), resolve),
                           cd=_emit(field("crit_damage", "100"), resolve)))
    elif node.type == "result":
        stages.append(dict(op=OP_RESULT))
    return stages


def compile_project(project, role: str) -> dict:
    """工程（dict / Graph）→ 函数表示（可直接交给通用 DLL）。"""
    from genshin_dmg.graph import Graph

    graph = project if isinstance(project, Graph) else Graph.from_dict(project or {})
    result = _role_result(graph, role)

    # 先把「不注入圣遗物」的变量表算出来：面板宏的常数部分就在这里
    graph.extra_own = {}
    out = graph.evaluate()
    base_env = {}
    for row in out.get("variables") or []:
        base_env[_math.mangle(row["name"])] = float(row["value"])

    def resolve(name: str) -> list:
        key = _math.mangle(name)
        if name in STATS_ORDER:
            panel = float(base_env.get(_math.mangle("%s::%s" % (role, name)),
                                       base_env.get(key, 0.0)))
            return [("const", panel), ("stat", STATS_ORDER.index(name)), ("add",)]
        if key in base_env:
            return [("const", base_env[key])]
        scoped = _math.mangle("%s::%s" % (role, name))
        if scoped in base_env:
            return [("const", base_env[scoped])]
        raise NotCompilable("解析不到变量: %s" % name)

    return dict(role=role, stats_order=list(STATS_ORDER),
                stages=_compile_node(graph, result.id, resolve))

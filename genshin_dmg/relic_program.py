# -*- coding: utf-8 -*-
"""把工程里的伤害链抽象成"可传给通用 DLL 的函数表示"。

用户口径：**一个通用 DLL**，接收"函数表示"后自己求值；不是每个工程编译一个 DLL。

函数表示 = 一串 **阶段（stage）**，每个阶段带小的 RPN 表达式（只含常量与 9 个属性）：

| op | 含义 |
|---|---|
| ``base`` | ``(stat_base*(1+stat_big/100)+stat_flat) * multiplier/100`` |
| ``mul`` | 乘一个纯系数（增伤区 / 反应系数 …） |
| ``res`` | 乘抗性系数（表达式给"敌人抗性%"，减抗已合并） |
| ``def`` | 乘防御系数（角色等级 / 敌人等级 / 减防% / 无视防御%） |
| ``crit`` | 记录暴击率、暴伤（两条分支最后按它们混合） |
| ``result`` | ``expected = (1-r)*noncrit + r*crit`` |

RPN 项：``("const", 值)`` / ``("stat", 下标)`` / ``("add",)`` / ``("sub",)`` / ``("mul",)`` /
``("div",)`` / ``("neg",)`` / ``("min",)`` / ``("max",)`` / ``("pow",)``。
"""

from __future__ import annotations

from . import damage as _damage
from . import nodes as _nodes
from .expr import _OPS, _FULLWIDTH, mangle
from .relic import STATS_ORDER

__all__ = ["NotCompilable", "compile_project", "run", "run_expected"]

OP_BASE = "base"
OP_MUL = "mul"
OP_RES = "res"
OP_DEF = "def"
OP_CRIT = "crit"
OP_RESULT = "result"

_CORE = ("base", "dmg", "res", "def", "crit", "add", "result")
_UNARY = {_OPS[type(op)]: name for op, name in
          ((None, None),)} if False else None   # 占位，实际映射见下方

_OP_NAMES = {
    "add": "add", "sub": "sub", "mul": "mul", "truediv": "div",
    "floordiv": "div", "mod": None, "pow": "pow",
}


class NotCompilable(Exception):
    """链里有暂时无法编译的卡片（调用方回退到解释层）。"""


# ---- 表达式（RPN）--------------------------------------------------------
def _emit(text, resolve) -> list:
    """字段表达式 → RPN。名字解析交给 ``resolve``，解析不了就 NotCompilable。"""
    import ast

    t = (text or "").strip()
    for k, v in _FULLWIDTH.items():
        t = t.replace(k, v)
    t = "".join(t.split())
    if not t:
        raise NotCompilable("空表达式")
    try:
        tree = ast.parse(mangle(t), mode="eval")
    except SyntaxError:
        raise NotCompilable("语法错误: %r" % text)

    out: list = []

    def walk(node) -> None:
        if isinstance(node, ast.Expression):
            walk(node.body)
            return
        if isinstance(node, ast.Constant):
            out.append(("const", float(node.value)))
            return
        if isinstance(node, ast.Name):
            out.extend(resolve(node.id))
            return
        if isinstance(node, ast.BinOp):
            name = type(node.op).__name__
            op = {"Add": "add", "Sub": "sub", "Mult": "mul", "Div": "div",
                  "Pow": "pow"}.get(name)
            if op is None:
                raise NotCompilable("不支持的运算: %s" % name)
            walk(node.left)
            walk(node.right)
            out.append((op,))
            return
        if isinstance(node, ast.UnaryOp):
            if type(node.op).__name__ != "USub":
                raise NotCompilable("不支持的一元运算")
            walk(node.operand)
            out.append(("neg",))
            return
        raise NotCompilable("不支持的语法: %r" % type(node).__name__)

    walk(tree)
    return out


def _run_expr(expr, stats) -> float:
    stack: list = []
    for item in expr:
        op = item[0]
        if op == "const":
            stack.append(float(item[1]))
        elif op == "stat":
            stack.append(float(stats[int(item[1])]))
        elif op == "add":
            b = stack.pop()
            stack.append(stack.pop() + b)
        elif op == "sub":
            b = stack.pop()
            stack.append(stack.pop() - b)
        elif op == "mul":
            b = stack.pop()
            stack.append(stack.pop() * b)
        elif op == "div":
            b = stack.pop()
            stack.append(stack.pop() / b)
        elif op == "neg":
            stack.append(-stack.pop())
        elif op == "min":
            b = stack.pop()
            stack.append(min(stack.pop(), b))
        elif op == "max":
            b = stack.pop()
            stack.append(max(stack.pop(), b))
        elif op == "pow":
            b = stack.pop()
            stack.append(stack.pop() ** b)
        else:
            raise NotCompilable("未知表达式操作: %r" % (op,))
    if len(stack) != 1:
        raise NotCompilable("表达式栈不平衡")
    return stack[0]


# ---- 编译工程 ------------------------------------------------------------
def _role_result(graph, role: str):
    for node in graph.nodes.values():
        if node.type == "result" and getattr(node, "role", "") == role:
            return node
    raise NotCompilable("工程里没有属于 %s 的 ★结果 卡" % role)


def _chain(graph, result_id: str) -> list:
    """从 ★结果 往上游走，返回 [base, …, result]；遇到未知类型就 NotCompilable。"""
    order: list = []
    seen: set = set()
    nid = result_id
    while nid:
        if nid in seen:
            raise NotCompilable("链里有环")
        seen.add(nid)
        node = graph.nodes.get(nid)
        if node is None:
            raise NotCompilable("链上缺少节点: %s" % nid)
        if node.type not in _CORE:
            raise NotCompilable("暂不支持编译卡片类型: %s" % node.type)
        order.append(node.id)
        nid = graph.link_src(nid, 0)
    order.reverse()
    return order


def compile_project(project, role: str) -> dict:
    """工程（dict / Graph）→ 函数表示（可直接交给通用 DLL）。"""
    from .graph import Graph

    graph = project if isinstance(project, Graph) else Graph.from_dict(project or {})
    result = _role_result(graph, role)
    chain = _chain(graph, result.id)

    # 先把「不注入圣遗物」的变量表算出来：面板宏的常数部分就在这里
    graph.extra_own = {}
    out = graph.evaluate()
    base_env = {}
    for row in out.get("variables") or []:
        base_env[mangle(row["name"])] = float(row["value"])

    def resolve(name: str) -> list:
        key = mangle(name)
        if name in STATS_ORDER:
            panel = float(base_env.get(mangle("%s::%s" % (role, name)),
                                       base_env.get(key, 0.0)))
            return [("const", panel), ("stat", STATS_ORDER.index(name)), ("add",)]
        if key in base_env:
            return [("const", base_env[key])]
        scoped = mangle("%s::%s" % (role, name))
        if scoped in base_env:
            return [("const", base_env[scoped])]
        raise NotCompilable("解析不到变量: %s" % name)

    stages: list = []
    for nid in chain:
        node = graph.nodes[nid]
        get = node.getter()

        def field(key, default="0"):
            raw = get(key)
            return default if raw is None or (isinstance(raw, str) and not raw.strip()) else raw

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
        elif node.type == "add":
            if graph.input_count(nid) != 1:
                raise NotCompilable("「加法合并」多输入暂不支持")
        elif node.type == "result":
            stages.append(dict(op=OP_RESULT))
    return dict(role=role, stats_order=list(STATS_ORDER), stages=stages)


# ---- 解释执行（与 DLL 对拍的基准）----------------------------------------
def run(program: dict, stats) -> dict:
    """执行程序，返回 ``{"noncrit", "crit", "rate", "expected"}``。"""
    values = [float(v) for v in stats]
    if len(values) != len(STATS_ORDER):
        raise ValueError("需要 %d 个属性" % len(STATS_ORDER))
    noncrit = 1.0
    crit = 1.0
    critted = False
    rate = 0.0
    cd = 0.0
    for stage in program.get("stages") or []:
        op = stage["op"]
        if op == OP_BASE:
            value = _run_expr(stage["expr"], values)
            noncrit *= value
            crit *= value
        elif op == OP_MUL:
            coeff = _run_expr(stage["expr"], values)
            noncrit *= coeff
            crit *= coeff
        elif op == OP_RES:
            coeff = _damage.resistance_coefficient(
                _run_expr(stage["expr"], values) / 100.0)
            noncrit *= coeff
            crit *= coeff
        elif op == OP_DEF:
            exprs = stage["exprs"]
            coeff = _damage.defense_coefficient(
                _run_expr(exprs[0], values), _run_expr(exprs[1], values),
                def_reduction=_run_expr(exprs[2], values) / 100.0,
                ignore_def=_run_expr(exprs[3], values) / 100.0,
            )
            noncrit *= coeff
            crit *= coeff
        elif op == OP_CRIT:
            if critted:
                raise NotCompilable("链里有多个暴击区")
            rate = _run_expr(stage["rate"], values) / 100.0
            cd = _run_expr(stage["cd"], values) / 100.0
            crit *= 1.0 + cd
            critted = True
        elif op == OP_RESULT:
            continue
        else:
            raise NotCompilable("未知阶段: %r" % (op,))
    rate = min(1.0, max(0.0, rate))
    expected = (1.0 - rate) * noncrit + rate * crit
    return dict(noncrit=noncrit, crit=crit, rate=rate, expected=expected)


def run_expected(program: dict, stats) -> float:
    return run(program, stats)["expected"]

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

from . import relic_math as _math
from .relic import STATS_ORDER

__all__ = ["NotCompilable", "_emit", "run", "run_expected"]

OP_BASE = "base"
OP_MUL = "mul"
OP_RES = "res"
OP_DEF = "def"
OP_CRIT = "crit"
OP_ADD = "add"
OP_RESULT = "result"

_CORE = ("base", "dmg", "res", "def", "crit", "add", "result")

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
    for k, v in _math.FULLWIDTH.items():
        t = t.replace(k, v)
    t = "".join(t.split())
    if not t:
        raise NotCompilable("空表达式")
    try:
        tree = ast.parse(_math.mangle(t), mode="eval")
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


# ---- 解释执行（与 DLL 对拍的基准）----------------------------------------
def _run_stages(stages, values) -> tuple:
    """执行一串阶段，返回 (未暴击, 暴击, 期望) 三分量。"""
    nc = c = e = 1.0
    for stage in stages:
        op = stage["op"]
        if op == OP_BASE:
            value = _run_expr(stage["expr"], values)
            nc *= value
            c *= value
            e *= value
        elif op == OP_MUL:
            coeff = _run_expr(stage["expr"], values)
            nc *= coeff
            c *= coeff
            e *= coeff
        elif op == OP_RES:
            coeff = _math.resistance_coefficient(
                _run_expr(stage["expr"], values) / 100.0)
            nc *= coeff
            c *= coeff
            e *= coeff
        elif op == OP_DEF:
            exprs = stage["exprs"]
            coeff = _math.defense_coefficient(
                _run_expr(exprs[0], values), _run_expr(exprs[1], values),
                def_reduction=_run_expr(exprs[2], values) / 100.0,
                ignore_def=_run_expr(exprs[3], values) / 100.0)
            nc *= coeff
            c *= coeff
            e *= coeff
        elif op == OP_CRIT:
            rate = min(1.0, max(0.0, _run_expr(stage["rate"], values) / 100.0))
            cd = _run_expr(stage["cd"], values) / 100.0
            base = nc
            nc = base
            c = base * (1.0 + cd)
            e = base * (1.0 + rate * cd)
        elif op == OP_ADD:
            total = [0.0, 0.0, 0.0]
            for branch in stage["branches"]:
                part = _run_stages(branch, values)
                total[0] += part[0]
                total[1] += part[1]
                total[2] += part[2]
            # 「加法合并」= 各分支分量相加（与 _t_add 一致，不乘上游）
            nc, c, e = total[0], total[1], total[2]
        elif op == OP_RESULT:
            continue
        else:
            raise NotCompilable("未知阶段: %r" % (op,))
    return nc, c, e


def run(program: dict, stats) -> dict:
    """执行程序，返回 ``{"noncrit", "crit", "expected"}``。"""
    values = [float(v) for v in stats]
    if len(values) != len(STATS_ORDER):
        raise ValueError("需要 %d 个属性" % len(STATS_ORDER))
    nc, c, e = _run_stages(program.get("stages") or [], values)
    return dict(noncrit=nc, crit=c, expected=e)


def run_expected(program: dict, stats) -> float:
    return run(program, stats)["expected"]

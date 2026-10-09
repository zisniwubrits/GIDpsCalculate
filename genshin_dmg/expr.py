# -*- coding: utf-8 -*-
"""输入框的解析与数值格式化（纯函数，不依赖任何 UI）。

所有数值输入框都走 :func:`parse_num` / :func:`parse_pct`，因此天然支持：
  * 算式：``70+30``、``200*3``、``(80+20)*1.5``
  * 变量名：``攻击力*2``（变量来自「变量」卡片与「★结果」卡片的三元组）
  * 全角符号：``× ÷ ＋ － （）`` 与千分位逗号

:func:`eval_expr` 使用 :mod:`ast` 白名单求值，**不使用 eval**。

格式化统一走 :func:`fmt_num` / :func:`plain_num`，**不出现科学计数法**。
"""

from __future__ import annotations

import ast
import keyword
import operator

__all__ = [
    "eval_expr",
    "parse_num",
    "parse_pct",
    "fmt_num",
    "plain_num",
    "valid_var_name",
    "to_bool",
]

# 全角 → 半角
_FULLWIDTH = {"，": ",", "×": "*", "÷": "/", "＋": "+", "－": "-", "（）": "()"}

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_TRUE_WORDS = ("1", "true", "yes", "是", "on")


def eval_expr(text: str, env: dict | None = None) -> float:
    """安全求值算术表达式（支持 ``+ - * / // % **``、括号、变量名）。

    失败时抛 :class:`ValueError`（空表达式、语法错误、未定义变量、除以零…）。
    """
    env = env or {}
    t = (text or "").strip()
    for k, v in _FULLWIDTH.items():
        t = t.replace(k, v)
    t = t.replace("（", "(").replace("）", ")")
    t = t.replace(",", "").replace("，", "")
    t = "".join(t.split())          # 去掉空格与换行，便于多行编辑
    if not t:
        raise ValueError("表达式为空")
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        raise ValueError("表达式语法错误")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):          # 变量引用
            if node.id in env:
                return float(env[node.id])
            raise ValueError("未定义变量: %s" % node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("不支持的运算")

    try:
        return float(ev(tree))
    except (ZeroDivisionError, OverflowError, TypeError) as e:
        raise ValueError(str(e))


def parse_num(s, d: float = 0.0, env: dict | None = None) -> float:
    """解析数值；支持算式与变量名，非法则返回默认值 ``d``。"""
    if isinstance(s, bool):
        return 1.0 if s else 0.0
    if isinstance(s, (int, float)):
        return float(s)
    t = (s or "").strip()
    if not t:
        return d
    try:
        return float(t)
    except ValueError:
        pass
    try:
        return eval_expr(t, env)
    except ValueError:
        return d


def parse_pct(s, d: float = 0.0, env: dict | None = None) -> float:
    """解析百分比（``50`` → ``0.5``）。"""
    return parse_num(s, d, env) / 100.0


def fmt_num(x: float) -> str:
    """固定小数位格式化，避免出现科学计数法（如 ``1.2e+05``）。"""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "0.0000"
    if x != x or x in (float("inf"), float("-inf")):     # NaN / inf
        return str(x)
    if abs(x) >= 10000:
        return "{:,.1f}".format(x)
    if abs(x) >= 100:
        return "{:.2f}".format(x)
    if abs(x) >= 1:
        return "{:.3f}".format(x)
    return "{:.4f}".format(x)


def plain_num(x: float) -> str:
    """纯数字字符串（无千分位、无科学计数法），便于复制后直接粘贴。"""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "0"
    if x != x or x in (float("inf"), float("-inf")):
        return str(x)
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    s = "{:.6f}".format(x).rstrip("0").rstrip(".")
    return s if s else "0"


def valid_var_name(s) -> str:
    """校验用户填写的变量名；空 / 非法标识符 / 关键字时返回空串（表示不定义）。"""
    t = (s or "").strip()
    if not t or keyword.iskeyword(t) or not t.isidentifier():
        return ""
    return t


def to_bool(value) -> bool:
    """把各种来源的布尔值统一成 bool（前端 JSON 的 true/false、字符串 "是" 等）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return (value or "").strip().lower() in _TRUE_WORDS

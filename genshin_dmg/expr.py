# -*- coding: utf-8 -*-
"""输入框的解析与数值格式化（纯函数，不依赖任何 UI）。

所有数值输入框都走 :func:`parse_num` / :func:`parse_pct`，因此天然支持：
  * 算式：``70+30``、``200*3``、``(80+20)*1.5``
  * 变量名：``攻击力*2``（变量来自「变量」卡片与「★结果」卡片的三元组）
  * 命名空间变量：``雷神::攻击力*2``（角色容器卡的命名空间，见下）
  * 全角符号：``× ÷ ＋ － （）`` 与千分位逗号

:func:`eval_expr` 使用 :mod:`ast` 白名单求值，**不使用 eval**。

命名空间（``角色::变量``）怎么实现：Python 的标识符里不能有 ``::``，
所以求值前先把 ``A::B`` 拼成合法标识符 ``A__B``（:func:`mangle`），
变量表内部就用这个键；对外（界面、错误信息、变量表）一律用 :func:`demangle`
还原成 ``A::B`` 展示。映射要**单射**，因此角色名与变量名里禁止出现连续两个
下划线（``__`` 保留给内部拼接）—— :func:`valid_var_name` 会拦下这种名字。

格式化统一走 :func:`fmt_num` / :func:`plain_num`，**不出现科学计数法**。
"""

from __future__ import annotations

import ast
import keyword
import operator
import re

__all__ = [
    "eval_expr",
    "parse_num",
    "parse_pct",
    "fmt_num",
    "plain_num",
    "valid_var_name",
    "to_bool",
    "mangle",
    "demangle",
    "env_key",
    "qualify",
    "NS_SEP",
    "NS_JOIN",
]

# 全角 → 半角（全角冒号也认：中文输入法下很容易打出 ：： ）
_FULLWIDTH = {"，": ",", "×": "*", "÷": "/", "＋": "+", "－": "-",
              "（）": "()", "：": ":"}

# 命名空间分隔符（用户书写）与内部拼接符（拼成合法标识符）
NS_SEP = "::"
NS_JOIN = "__"

# 形如 名字::名字 的片段（名字=标识符形态：字母/下划线开头，后跟字母数字下划线）
_NS_RE = re.compile(r"([^\W\d]\w*)\s*::\s*([^\W\d]\w*)")

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


# ---------------------------------------------------------------- 命名空间
def mangle(text: str) -> str:
    """把表达式里的 ``角色::变量`` 拼成合法标识符 ``角色__变量``（供 ast 解析）。"""
    return _NS_RE.sub(lambda m: m.group(1) + NS_JOIN + m.group(2), text or "")


def demangle(name: str) -> str:
    """内部标识符 → 展示名：``角色__变量`` → ``角色::变量``（没有前缀则原样返回）。

    用户名字里禁止 ``__``，所以内部键里的每个拼接符都是命名空间分隔。
    """
    return (name or "").replace(NS_JOIN, NS_SEP)


def qualify(name: str, role: str = "") -> str:
    """给变量名加上角色前缀（已经有前缀 / 没有角色则原样返回）。"""
    t = (name or "").strip()
    if not t or not role or NS_SEP in t:
        return t
    return "%s%s%s" % (role, NS_SEP, t)


def env_key(name: str) -> str:
    """展示名 → 变量表内部键（``角色::变量`` → ``角色__变量``；普通名原样）。"""
    return mangle((name or "").strip())


def _plain_ok(t: str) -> bool:
    """单个名字（不含命名空间）是否合法：标识符、非关键字、不含内部拼接符。"""
    return bool(t) and t.isidentifier() and not keyword.iskeyword(t) and NS_JOIN not in t


def valid_var_name(s) -> str:
    """校验用户填写的变量名，返回**规范化的展示名**；非法时返回空串（表示不定义）。

    支持 ``角色::变量`` 形式；角色名与变量名都不能含 ``__``（保留给内部拼接）。
    """
    t = (s or "").strip()
    if not t:
        return ""
    if NS_SEP in t:
        ns, _, var = t.partition(NS_SEP)
        ns, var = ns.strip(), var.strip()
        if not _plain_ok(ns) or not _plain_ok(var):
            return ""
        return "%s%s%s" % (ns, NS_SEP, var)
    return t if _plain_ok(t) else ""


def eval_expr(text: str, env: dict | None = None) -> float:
    """安全求值算术表达式（支持 ``+ - * / // % **``、括号、变量名、``角色::变量``）。

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
    t = mangle(t)                   # 角色::变量 → 角色__变量（合法标识符）
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
                val = env[node.id]
                # 值可以是数字，也可以是**惰性取值函数**（命名的卡片输出要等求值才知道，
                # 见 graph.py 的 _card_vars），这里统一兑现成数字。
                return float(val() if callable(val) else val)
            # 报错用展示名，别把内部的 角色__变量 露给用户
            raise ValueError("未定义变量: %s" % demangle(node.id))
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


def to_bool(value) -> bool:
    """把各种来源的布尔值统一成 bool（前端 JSON 的 true/false、字符串 "是" 等）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return (value or "").strip().lower() in _TRUE_WORDS

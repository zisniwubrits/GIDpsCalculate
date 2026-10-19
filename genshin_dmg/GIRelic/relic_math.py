# -*- coding: utf-8 -*-
"""圣遗物层需要的那几个通用工具（**独立副本**，不 import 主程序任何模块）。

搬了两处：

* 命名空间改名 :func:`mangle` 与全角替换表 :data:`_FULLWIDTH`（原 ``genshin_dmg/expr.py``）——
  用来把工程里的 ``角色::宏`` 拼成变量表键，只做字符串处理；
* 抗性区 / 防御区系数（原 ``genshin_dmg/damage.py``）—— :func:`resistance_coefficient` /
  :func:`defense_coefficient` 及其用到的 :func:`clamp`。

**公式口径以主程序为准**：``damage.py`` 改了这里必须同步，
由 ``tests/test_relic_independence.py`` 对拍（同输入 → 同输出，1e-12）守住。
"""

from __future__ import annotations

import re

__all__ = [
    "FULLWIDTH",
    "NS_SEP",
    "NS_JOIN",
    "mangle",
    "clamp",
    "resistance_coefficient",
    "defense_coefficient",
]

# ---------------------------------------------------------------- 表达式文本
# 全角 → 半角（全角冒号也认：中文输入法下很容易打出 ：： ）
FULLWIDTH = {"，": ",", "×": "*", "÷": "/", "＋": "+", "－": "-",
             "（）": "()", "：": ":"}

# 兼容主程序的私有名（那边叫 _FULLWIDTH），调用方两种名字都能用
_FULLWIDTH = FULLWIDTH

# 命名空间分隔符（用户书写）与内部拼接符（拼成合法标识符）
NS_SEP = "::"
NS_JOIN = "__"

# 命名空间链条：`A` / `A::B` / `A::B::C`…（每段都是标识符形态）
_CHAIN = r"[^\W\d]\w*(?:\s*::\s*[^\W\d]\w*)*"
# 允许**前导** `::`（用户会写 `::out::atk` 表示"本角色的 out"）
_NS_RE = re.compile(r"::\s*(?P<bare>" + _CHAIN + r")|(?P<full>" + _CHAIN + r")")


def mangle(text: str) -> str:
    """把表达式里的命名空间链条拼成合法标识符（``角色::out::atk`` → ``角色__out__atk``）。

    支持多段与前导 ``::``（``::out::atk`` → ``out__atk``，即"本角色的 out"）。
    """
    def repl(m):
        chain = m.group("bare") or m.group("full") or ""
        parts = [p.strip() for p in chain.split(NS_SEP) if p.strip()]
        return NS_JOIN.join(parts)

    return _NS_RE.sub(repl, text or "")


# ---------------------------------------------------------------- 伤害系数
def clamp(value: float, lo: float, hi: float) -> float:
    """把数值限制在 [lo, hi] 区间内。"""
    return max(lo, min(hi, value))


def resistance_coefficient(res: float) -> float:
    """
    抗性系数。

    res <= 0        : 1 - res/2
    0 <= res <= 75% : 1 - res
    75% <= res      : 1 / (4*res + 1)
    """
    if res <= 0:
        return 1 - res / 2
    if res <= 0.75:
        return 1 - res
    return 1 / (4 * res + 1)


def defense_coefficient(
    char_level: float,
    enemy_level: float,
    def_reduction: float = 0.0,
    ignore_def: float = 0.0,
) -> float:
    """
    角色攻击敌人时的防御系数（真实减防机制）。

        角色等级+100
        --------------------------------------------------
        (角色等级+100) + (敌人等级+100)×(1 - 减防)×(1 - 无视防御)

    减防 / 无视防御作用在"敌人防御项（分母）"，因此减防会提升伤害。
    来自角色的减防上限 90%，无视防御上限 100%。
    """
    dr = clamp(def_reduction, 0.0, 0.90)
    ide = clamp(ignore_def, 0.0, 1.00)
    a = char_level + 100
    b = enemy_level + 100
    return a / (a + b * (1 - dr) * (1 - ide))

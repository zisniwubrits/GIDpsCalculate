# -*- coding: utf-8 -*-
"""
原神伤害计算核心模块。

公式来源:
  https://ellen.rth1.xyz/原神产球及附着/index.html
  https://yuhuazhe.cn/zlk/gongshi.html （羽化哲：月/星反应等进阶公式）

本模块只做纯计算（不依赖 tkinter / 任何 UI），便于单元测试与复用。
所有百分比参数一律使用小数（例如 10% 传入 0.10）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 等级 → 反应基础值 表（用于剧变反应 / 激化反应 / 反应月/直伤月等）
# ---------------------------------------------------------------------------
REACTION_BASE_BY_LEVEL = {
    90: 1202.81,
    95: 1411.74,
    100: 1674.81,
    105: 1884.98,
    110: 1963.85,
}
REACTION_BASE_DEFAULT = 1446.85  # 未列出的等级使用的基准

# 剧变反应倍率
TRANSFORM_RATE = {
    "燃烧": 0.25,
    "扩散": 0.6,
    "超导": 1.5,
    "感电": 2.0,
    "超载": 2.75,
    "碎冰": 3.0,
    "绽放": 2.0,
    "超绽放": 3.0,
    "烈绽放": 3.0,
}

# 增幅反应基础系数（蒸发 / 融化）
AMPLIFY_BASE_FACTOR = {
    "蒸发·水→火": 2.0,
    "融化·火→冰": 2.0,
    "蒸发·火→水": 1.5,
    "融化·冰→火": 1.5,
}


def clamp(value: float, lo: float, hi: float) -> float:
    """把数值限制在 [lo, hi] 区间内。"""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# 抗性区
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 防御区（角色攻击敌人）
# ---------------------------------------------------------------------------
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

    减防 / 无视防御作用在“敌人防御项（分母）”，因此减防会提升伤害。
    来自角色的减防上限 90%，无视防御上限 100%。
    """
    dr = clamp(def_reduction, 0.0, 0.90)
    ide = clamp(ignore_def, 0.0, 1.00)
    a = char_level + 100
    b = enemy_level + 100
    return a / (a + b * (1 - dr) * (1 - ide))


# ---------------------------------------------------------------------------
# 增幅反应（蒸发 / 融化）系数
# ---------------------------------------------------------------------------
def amplify_coefficient(
    base_factor: float,
    elemental_mastery: float,
    reaction_bonus: float = 0.0,
) -> float:
    """
    蒸发融化系数 = 基础系数 × (1 + 2.78*元素精通/(元素精通+1400) + 反应增伤%)

    基础系数：
      蒸发 水→火 : 2.0
      融化 火→冰 : 2.0
      蒸发 火→水 : 1.5
      融化 冰→火 : 1.5
    """
    em = max(elemental_mastery, 0.0)
    return base_factor * (1 + 2.78 * em / (em + 1400) + reaction_bonus)


# ---------------------------------------------------------------------------
# 激化反应（超激化 / 蔓激化）附加到常规伤害的“激化值”
# ---------------------------------------------------------------------------
def aggravate_value(
    kind: str,
    elemental_mastery: float,
    enhance_bonus: float = 0.0,
    level: int = 90,
) -> float:
    """
    激化值 = 等级基础值 × 系数 × (1 + 5*元素精通/(元素精通+1200) + 激化提高%)

    系数：超激化 1.15，蔓激化 1.25。
    """
    kind = kind.strip()
    factor = 1.15 if kind == "超激化" else 1.25
    base = REACTION_BASE_BY_LEVEL.get(level, REACTION_BASE_DEFAULT)
    em = max(elemental_mastery, 0.0)
    return base * factor * (1 + 5 * em / (em + 1200) + enhance_bonus)


# ---------------------------------------------------------------------------
# 剧变反应伤害
# ---------------------------------------------------------------------------
def transformative_damage(
    reaction: str,
    elemental_mastery: float,
    level: int = 90,
    reaction_bonus: float = 0.0,
    extra_increase: float = 0.0,
    resistance: float = 0.0,
) -> float:
    """
    剧变伤害 = (剧变基础 + 额外提升) × 抗性系数

    剧变基础 = 等级基础值 × 反应倍率 × (1 + 16*元素精通/(元素精通+2000) + 反应增伤%)

    剧变反应不受益于常模倍增/易伤/减伤，且无视防御力，不能暴击。
    """
    if reaction not in TRANSFORM_RATE:
        raise ValueError(f"未知剧变反应: {reaction!r}")
    base = REACTION_BASE_BY_LEVEL.get(level, REACTION_BASE_DEFAULT)
    em = max(elemental_mastery, 0.0)
    base_value = base * TRANSFORM_RATE[reaction] * (
        1 + 16 * em / (em + 2000) + reaction_bonus
    )
    return (base_value + extra_increase) * resistance_coefficient(resistance)


# ---------------------------------------------------------------------------
# 常规（直伤）伤害 —— 核心公式
# ---------------------------------------------------------------------------
def normal_damage(
    base_value: float,
    *,
    base_bonus: float = 0.0,
    aggravate: float = 0.0,
    inc_bonus: float = 0.0,
    vulnerable_bonus: float = 0.0,
    damage_reduction: float = 0.0,
    resistance: float = 0.10,
    char_level: float = 90,
    enemy_level: float = 90,
    def_reduction: float = 0.0,
    ignore_def: float = 0.0,
    crit: bool = True,
    crit_rate: float = 0.50,
    crit_damage: float = 1.00,
    amplify_base: Optional[float] = None,
    elemental_mastery: float = 0.0,
    amplify_bonus: float = 0.0,
    has_initials: bool = True,
) -> dict:
    """
    常规伤害：

    最终伤害 = (基础值 + 激化值 + 基础值加成)
               × (1 + 增伤% + 易伤% - 减伤%)
               × 抗性系数
               × 防御系数
               × 暴击区
               × 蒸发融化系数

    base_value : 基础值 = 属性值 × 倍率（攻击力/生命值/元素精通/防御力均可）
    base_bonus : 基础值加成（描述中“造成的伤害提高 X%”）
    aggravate  : 激化值（超激化/蔓激化的附加值，见 aggravate_value）
    inc_bonus  : 增伤（我方造成的伤害提升 X%）
    vulnerable_bonus : 易伤（目标受到的伤害提升 X%）
    damage_reduction : 减伤（目标受到的伤害降低 X%）
    resistance : 敌人抗性（小数）
    has_initials : 是否出现伤害数字；为 False（如命中护盾）不计算蒸发融化系数

    返回包含各阶段系数的字典，便于展示明细。
    """
    if amplify_base is not None and not has_initials:
        amplify_base = None

    raw = base_value + aggravate + base_bonus

    dmg_bonus = 1 + inc_bonus + vulnerable_bonus - damage_reduction
    res_coeff = resistance_coefficient(resistance)
    def_coeff = defense_coefficient(
        char_level, enemy_level, def_reduction=def_reduction, ignore_def=ignore_def
    )

    if crit:
        crit_coeff = 1 + crit_damage
    else:
        crit_coeff = 1.0

    if amplify_base is not None:
        amp_coeff = amplify_coefficient(
            amplify_base, elemental_mastery, amplify_bonus
        )
    else:
        amp_coeff = 1.0

    damage = raw * dmg_bonus * res_coeff * def_coeff * crit_coeff * amp_coeff

    # 逐乘区中间值（用于展示计算过程）
    after_dmg = raw * dmg_bonus
    after_res = after_dmg * res_coeff
    after_def = after_res * def_coeff

    # 有效暴击率最多计入 100%，溢出部分截断
    cr_cap = clamp(crit_rate, 0.0, 1.0)

    # 期望伤害（按暴击率加权，有效暴击率封顶100%）
    expected = raw * dmg_bonus * res_coeff * def_coeff * amp_coeff * (
        1 + cr_cap * crit_damage
    )

    return {
        "raw": raw,
        "dmg_bonus": dmg_bonus,
        "res_coeff": res_coeff,
        "def_coeff": def_coeff,
        "crit_coeff": crit_coeff,
        "amp_coeff": amp_coeff,
        "after_dmg": after_dmg,
        "after_res": after_res,
        "after_def": after_def,
        "crit_rate_cap": cr_cap,
        "damage": damage,
        "expected": expected,
    }


# ---------------------------------------------------------------------------
# 结晶反应（护盾量，额外便利功能）
# ---------------------------------------------------------------------------
def crystallize_shield(
    elemental_mastery: float, shield_bonus: float = 0.0, shield_strength: float = 0.0
) -> float:
    """
    结晶盾量 = 1851.06 × (1 + 4.44*元素精通/(元素精通+1400)) × (1 + 护盾强效%)

    注：公式中的护盾强效会受持有护盾角色的护盾强效影响。
    """
    em = max(elemental_mastery, 0.0)
    base = 1851.06 * (1 + 4.44 * em / (em + 1400))
    return base * (1 + shield_bonus) * (1 + shield_strength)


# ---------------------------------------------------------------------------
# 属性前置乘区（攻/生/防的“大增益 + 小增益”）
# ---------------------------------------------------------------------------
def effective_stat(
    base_value: float, big_bonus: float = 0.0, flat_bonus: float = 0.0
) -> float:
    """
    攻/生/防等属性的最终数值（作为直伤公式中的“属性值”）。

        最终属性 = 白值 × (1 + 大增益%) + 小增益

    base_value : 白值（如基础攻击力）
    big_bonus  : 大增益%（如大攻击%），小数
    flat_bonus : 小增益（如小攻击固定数值），直接相加
    """
    return base_value * (1 + big_bonus) + flat_bonus


# ---------------------------------------------------------------------------
# 便捷封装：根据“反应类型+精通”直接计算蒸发/融化系数
# ---------------------------------------------------------------------------
def amplify_for_reaction(
    reaction_name: Optional[str],
    elemental_mastery: float,
    reaction_bonus: float = 0.0,
) -> float:
    """reaction_name 为 蒸发·水→火 / 融化·火→冰 等；None 或空串返回 1.0。"""
    if not reaction_name:
        return 1.0
    if reaction_name not in AMPLIFY_BASE_FACTOR:
        raise ValueError(f"未知增幅反应: {reaction_name!r}")
    return amplify_coefficient(
        AMPLIFY_BASE_FACTOR[reaction_name], elemental_mastery, reaction_bonus
    )


# ---------------------------------------------------------------------------
# 月 / 星 反应（进阶）
# 公式来源：https://yuhuazhe.cn/zlk/gongshi.html （羽化哲）
#
# 通用结构：
#   直伤基础 = 直伤系数 × 属性 × 倍率 × (1+基础提升%) × (1+em_skill+反应增伤%)
#   最终直伤 = (直伤基础 + 额外提升) × 抗性系数 × 暴击区 × 擢升
#
#   反应值   = 等级基础 × 反应倍率 × (1+基础提升%) × (1+em_skill+反应增伤%)
#   月/星反应无视防御，不受益于常规增伤/易伤/减伤，但受益于元素精通与暴击。
#   元素精通系数项：6×EM / (EM+2000)。
# ---------------------------------------------------------------------------
# 等级修正：角色 95 级把基准 1446.85 换为 1561.46，100 级换为 1674.81。
REACT_BASE_CORRECTION = {95: 1561.46, 100: 1674.81}

# 直伤月反应的直伤系数
MONTH_DIRECT_COEFF = {"月感电": 3.0, "月结晶": 1.6, "月绽放": 1.0}
# 反应月反应的倍率（月绽放没有“反应月”，只有直伤）
MONTH_REACT_COEFF = {"月感电": 1.8, "月结晶": 0.96}

# 星超导：直伤基础倍率随 hit 数（附着次数 0~12）变化
# hit 1 起等步长：每层 +0.05，1.45 → 2.00。
STAR_SUPERCOND_RATE = {
    0: 1.0, 1: 1.45, 2: 1.5, 3: 1.55, 4: 1.60, 5: 1.65, 6: 1.70,
    7: 1.75, 8: 1.80, 9: 1.85, 10: 1.90, 11: 1.95, 12: 2.0,
}

# 星扩散：反应基础倍率（风固定 0.75；冰随风涡系数 1~6）
STAR_SWIRL_WIND_BASE = 0.75
STAR_SWIRL_ICE_RATE = {1: 2.0, 2: 2.0, 3: 3.0, 4: 3.0, 5: 3.0, 6: 3.0}

# 月反应（感电/结晶）最终多角色分摊权重：
# 最高×1 + 第二高×1/2 + 第三高×1/12 + 第四高×1/12
MONTH_FINAL_WEIGHTS = [1.0, 1 / 2, 1 / 12, 1 / 12]


def react_base(level: int = 90) -> float:
    """取月/星反应所用的等级基准（95/100 级有修正，其余用 1446.85）。"""
    return REACT_BASE_CORRECTION.get(level, 1446.85)


def em_skill(elemental_mastery: float) -> float:
    """星/月通用元素精通系数项：6×EM/(EM+2000)。"""
    em = max(elemental_mastery, 0.0)
    return 6 * em / (em + 2000)


def _finish_star(
    value: float,
    extra_increase: float,
    resistance: float,
    crit: bool,
    crit_damage: float,
    boost_multi: float,
) -> float:
    crit_coeff = (1 + crit_damage) if crit else 1.0
    return (
        (value + extra_increase)
        * resistance_coefficient(resistance)
        * crit_coeff
        * boost_multi
    )


def month_direct(
    kind: str,
    attr_value: float,
    multiplier: float,
    *,
    elemental_mastery: float = 0.0,
    base_boost: float = 0.0,
    reaction_bonus: float = 0.0,
    extra_increase: float = 0.0,
    resistance: float = 0.10,
    crit: bool = True,
    crit_damage: float = 1.0,
    boost_multi: float = 1.0,
) -> float:
    """
    直伤月（月感电/月结晶/月绽放）。

    直伤基础 = 系数(3/1.6/1) × 属性 × 倍率 × (1+基础提升%) × (1+em_skill+增伤%)
    最终直伤 = (直伤基础 + 额外提升) × 抗性系数 × 暴击区 × 擢升
    """
    if kind not in MONTH_DIRECT_COEFF:
        raise ValueError(f"未知直伤月反应: {kind!r}")
    coeff = MONTH_DIRECT_COEFF[kind]
    raw = (
        coeff
        * attr_value
        * multiplier
        * (1 + base_boost)
        * (1 + em_skill(elemental_mastery) + reaction_bonus)
    )
    return _finish_star(raw, extra_increase, resistance, crit, crit_damage, boost_multi)


def month_reaction(
    kind: str,
    *,
    elemental_mastery: float = 0.0,
    base_boost: float = 0.0,
    reaction_bonus: float = 0.0,
    resistance: float = 0.10,
    crit: bool = True,
    crit_damage: float = 1.0,
    boost_multi: float = 1.0,
    level: int = 90,
) -> float:
    """
    反应月（月感电 ×1.8 / 月结晶 ×0.96）——单角色参与值。

    反应值 = 等级基础 × 倍率 × (1+基础提升%) × (1+em_skill+增伤%)×抗性×暴击×擢升
    注：最终伤害还需对多名参与角色按 MONTH_FINAL_WEIGHTS 分摊，见 distribute_damages。
    """
    if kind not in MONTH_REACT_COEFF:
        raise ValueError(f"未知反应月反应: {kind!r}（{list(MONTH_REACT_COEFF)}）")
    rate = MONTH_REACT_COEFF[kind]
    value = (
        react_base(level)
        * rate
        * (1 + base_boost)
        * (1 + em_skill(elemental_mastery) + reaction_bonus)
    )
    return _finish_star(value, 0.0, resistance, crit, crit_damage, boost_multi)


def distribute_damages(damages, weights=None) -> float:
    """
    多角色伤害分摊：把各角色伤害从大到小排序后按权重加权。

    weights 缺省为月反应权重 [1, 1/2, 1/12, 1/12]（最高×1+第二高×1/2+…）。
    """
    w = list(weights) if weights is not None else MONTH_FINAL_WEIGHTS
    s = sorted(damages, reverse=True)
    total = 0.0
    for i, wt in enumerate(w):
        total += wt * (s[i] if i < len(s) else 0.0)
    return total


def star_superconduct_direct(
    hits: int,
    attr_value: float,
    multiplier: float,
    *,
    elemental_mastery: float = 0.0,
    base_boost: float = 0.0,
    reaction_bonus: float = 0.0,
    extra_increase: float = 0.0,
    resistance: float = 0.10,
    crit: bool = True,
    crit_damage: float = 1.0,
    boost_multi: float = 1.0,
) -> float:
    """
    星超导（直伤）。

    直伤基础 = 星超导基础倍率(hit) × (攻击力或精通) × 倍率
               × (1+基础提升%) × (1+em_skill+星超导增伤%)
    最终直伤 = (直伤基础+额外提升) × 抗性系数 × 暴击区 × 擢升
    hits：冰/雷附着次数（0~12），决定基础倍率。
    """
    hits = int(clamp(int(hits), 0, 12))
    rate = STAR_SUPERCOND_RATE[hits]
    raw = (
        rate
        * attr_value
        * multiplier
        * (1 + base_boost)
        * (1 + em_skill(elemental_mastery) + reaction_bonus)
    )
    return _finish_star(raw, extra_increase, resistance, crit, crit_damage, boost_multi)


def star_swirl_reaction(
    subtype: str,
    *,
    vortex_count: int = 1,
    elemental_mastery: float = 0.0,
    base_boost: float = 0.0,
    reaction_bonus: float = 0.0,
    resistance: float = 0.10,
    crit: bool = True,
    crit_damage: float = 1.0,
    boost_multi: float = 1.0,
    level: int = 90,
) -> float:
    """
    反应星扩散（风 / 冰）。

    反应星扩散(风) = 等级基础 × 0.75 × …
    反应星扩散(冰) = 等级基础 × 基础倍率(风涡1~2→2；3~6→3) × …
    subtype：'风' 或 '冰'。vortex_count 仅对冰子反应生效。
    """
    subtype = subtype.strip()
    if subtype == "风":
        rate = STAR_SWIRL_WIND_BASE
    elif subtype == "冰":
        vc = int(clamp(int(vortex_count), 1, 6))
        rate = STAR_SWIRL_ICE_RATE[vc]
    else:
        raise ValueError(f"subtype 必须是 '风' 或 '冰'，得到 {subtype!r}")
    value = (
        react_base(level)
        * rate
        * (1 + base_boost)
        * (1 + em_skill(elemental_mastery) + reaction_bonus)
    )
    return _finish_star(value, 0.0, resistance, crit, crit_damage, boost_multi)


def star_swirl_direct(
    attr_value: float,
    multiplier: float,
    *,
    elemental_mastery: float = 0.0,
    base_boost: float = 0.0,
    reaction_bonus: float = 0.0,
    extra_increase: float = 0.0,
    resistance: float = 0.10,
    crit: bool = True,
    crit_damage: float = 1.0,
    boost_multi: float = 1.0,
) -> float:
    """
    星扩散直伤。

    直伤基础 = 1 × 属性 × 倍率 × (1+基础提升%) × (1+em_skill+星扩散增伤%)
    最终直伤 = (直伤基础+额外提升) × 抗性系数 × 暴击区 × 擢升
    """
    raw = (
        1.0
        * attr_value
        * multiplier
        * (1 + base_boost)
        * (1 + em_skill(elemental_mastery) + reaction_bonus)
    )
    return _finish_star(raw, extra_increase, resistance, crit, crit_damage, boost_multi)

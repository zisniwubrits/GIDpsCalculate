# -*- coding: utf-8 -*-
"""圣遗物：**刷取换算层**（常量 + 期望算术）。

这一步只管"数据与算术"，不算伤害、不碰 `graph.py`、不碰前端，也没有 HTTP。

口径（用户确认）：

* 只考虑**圣遗物副本**：20 原粹树脂/次；
* 每次必掉 1 件五星，另有 **6.5%** 概率再多掉 1 件 → **1.065 件/次**；
* 副本掉落属于**两套之一，各 50%**；要做 4 件套就得是目标套，
  另外**允许 1 个散件槽**（任意套）→ 目标套件数期望 = `1.065 × 0.5`；
* 主词条由副本**随机**给出（概率见 :data:`MAIN_STAT_PROB`；花/羽固定；
  空之杯「每类属性伤害各 5%」，**物理伤害也算一类**（7 元素 + 物理 = 8 类，合计 100%））；
* 副词条按**权重**抽取（见 :data:`SUBSTAT_WEIGHT`，总权重 1100）；
* 初始副词条 3 或 4 条：副本 **20%** 是 4 条 → 每件期望词条点 = `8 + 0.2 = 8.2`；
* 词条数值取 :data:`nodes.RELIC_ROWS` 的**平均值**（不另抄一份数字）；
* 4 件套的**效果数值不建模**（用户在圣遗物域里自己固定）。

由上面的规则推出的两个关键量：

* 一件"目标套 + 指定主词条"的期望树脂 ``20 / (1.065 × 0.5 × p)``；
* 一件"散件槽 + 指定主词条"的期望树脂 ``20 / (1.065 × p)``。
"""

from __future__ import annotations

from . import nodes as _nodes

__all__ = [
    "RESIN_PER_RUN",
    "EXTRA_DROP_RATE",
    "SET_SHARE",
    "FOUR_SUB_RATE",
    "SUBSTAT_LABELS",
    "SUBSTAT_WEIGHT",
    "SUBSTAT_AVG",
    "MAIN_STAT_PROB",
    "MAIN_STAT_VALUE",
    "DAMAGE_MAINS",
    "SLOTS",
    "SLOT_LABELS",
    "SLOT_FLOWER",
    "SLOT_PLUME",
    "SLOT_SANDS",
    "SLOT_GOBLET",
    "SLOT_CIRCLET",
    "pieces_for_resin",
    "effective_points",
    "resin_cost",
    "substat_pool",
    "expected_substat_rolls",
    "expected_substats",
    "combo_cost",
    "main_combos",
    "feasible_combos",
]

# ---- 刷取侧常量 ----------------------------------------------------------
RESIN_PER_RUN = 20              # 一次副本 20 树脂
EXTRA_DROP_RATE = 0.065         # 额外掉一件的概率 → 1.065 件/次
SET_SHARE = 0.5                 # 副本两套各 50%
FOUR_SUB_RATE = 0.2             # 副本掉落初始 4 词条的概率（BOSS/周本/三合一是 34%）
UPGRADE_ROLLS = 5               # +4/+8/+12/+16/+20
# 槽位用 ASCII 标识（代码里不要用中文当键）；中文只在界面上显示
SLOT_FLOWER = "flower"      # 生之花
SLOT_PLUME = "plume"        # 死之羽
SLOT_SANDS = "sands"        # 时之沙
SLOT_GOBLET = "goblet"      # 空之杯
SLOT_CIRCLET = "circlet"    # 理之冠
SLOTS = (SLOT_FLOWER, SLOT_PLUME, SLOT_SANDS, SLOT_GOBLET, SLOT_CIRCLET)
# 显示用中文名（只在需要给人看的时候用）
SLOT_LABELS = {
    SLOT_FLOWER: "生之花",
    SLOT_PLUME: "死之羽",
    SLOT_SANDS: "时之沙",
    SLOT_GOBLET: "空之杯",
    SLOT_CIRCLET: "理之冠",
}


# ---- 副词条：权重 + 平均值（平均值取自 nodes.RELIC_ROWS）-------------------
# 键一律用 ASCII（与面板宏同名，方便直接注入）；中文只作"显示 / 查参考表"的标签
SUBSTAT_LABELS = {
    "crit_rate": "暴击率（%）",
    "crit_dmg": "暴击伤害（%）",
    "atk_flat": "固定攻击力",
    "atk_pct": "百分比攻击力（%）",
    "hp_flat": "固定生命值",
    "hp_pct": "百分比生命值（%）",
    "def_flat": "固定防御力",
    "def_pct": "百分比防御力（%）",
    "em": "元素精通",
    "er": "元素充能效率（%）",
}

# {key: 权重}（生命/攻击/防御 150、双爆 75、其余 100，合计 1100）
SUBSTAT_WEIGHT = {
    "crit_rate": 75,
    "crit_dmg": 75,
    "atk_flat": 150,
    "atk_pct": 100,
    "hp_flat": 150,
    "hp_pct": 100,
    "def_flat": 150,
    "def_pct": 100,
    "em": 100,
    "er": 100,
}


def _relic_average(name: str) -> float:
    """从参考表里取某个属性的"平均值"（第 4 列）。找不到就报错（数据源只有这一份）。"""
    for row in _nodes.RELIC_ROWS:
        if row[0] == name:
            return float(row[3])
    raise KeyError("参考表里没有这个词条：%s" % name)


# {key: 平均词条值}（按显示名去参考表里取，参考表是唯一数据源）
SUBSTAT_AVG = {key: _relic_average(label) for key, label in SUBSTAT_LABELS.items()}


# ---- 主词条：概率 + 满级值 ------------------------------------------------
# 空之杯的"属性伤害加成"：7 种元素 + 物理，每类各 5%（合计 100% 的一部分）
_ELEMENT_DMG = ("pyro", "hydro", "electro", "cryo", "anemo", "geo", "dendro")
DAMAGE_MAINS = tuple("dmg_%s" % name for name in _ELEMENT_DMG) + ("dmg_physical",)

MAIN_STAT_PROB: dict = {
    SLOT_FLOWER: {"hp_flat": 1.0},
    SLOT_PLUME: {"atk_flat": 1.0},
    SLOT_SANDS: {
        "hp_pct": 0.2668,
        "atk_pct": 0.2666,
        "def_pct": 0.2666,
        "er": 0.10,
        "em": 0.10,
    },
    SLOT_GOBLET: {
        "hp_pct": 0.1925,
        "atk_pct": 0.1925,
        "def_pct": 0.19,
        "em": 0.025,
        **{key: 0.05 for key in DAMAGE_MAINS},
    },
    SLOT_CIRCLET: {
        "hp_pct": 0.22,
        "atk_pct": 0.22,
        "def_pct": 0.22,
        "em": 0.04,
        "crit_rate": 0.10,
        "crit_dmg": 0.10,
        "heal": 0.10,
    },
}

MAIN_STAT_VALUE: dict = {
    SLOT_FLOWER: {"hp_flat": 4780.0},
    SLOT_PLUME: {"atk_flat": 311.0},
    SLOT_SANDS: {"hp_pct": 46.6, "atk_pct": 46.6, "def_pct": 46.6, "er": 51.8, "em": 187.0},
    SLOT_GOBLET: {
        "hp_pct": 46.6,
        "atk_pct": 46.6,
        "def_pct": 46.6,
        "em": 187.0,
        # 元素伤害 46.6%，物理伤害 58.3%
        **{key: 46.6 for key in DAMAGE_MAINS},
        "dmg_physical": 58.3,
    },
    SLOT_CIRCLET: {
        "hp_pct": 46.6,
        "atk_pct": 46.6,
        "def_pct": 46.6,
        "em": 187.0,
        "crit_rate": 31.1,
        "crit_dmg": 62.2,
        "heal": 35.9,
    },
}


# ---- 换算 ----------------------------------------------------------------
def pieces_for_resin(resin: float, extra_rate: float = EXTRA_DROP_RATE,
                     set_share: float = SET_SHARE,
                     resin_per_run: float = RESIN_PER_RUN) -> dict:
    """树脂 → 期望件数。

    返回 ``{"runs", "total", "target_set", "off_set"}``：

    * ``runs``      —— 刷了几次（``树脂/20``，可以是小数）；
    * ``total``     —— 五星件数期望（``runs × 1.065``）；
    * ``target_set``—— 其中属目标套的件数期望（``total × 50%``）；
    * ``off_set``   —— 另一套的件数期望（只能当散件用）。
    """
    if resin_per_run <= 0:
        raise ValueError("resin_per_run 必须为正数")
    runs = max(0.0, float(resin or 0) / float(resin_per_run))
    total = runs * (1.0 + float(extra_rate))
    return dict(runs=runs, total=total,
                target_set=total * float(set_share),
                off_set=total * (1.0 - float(set_share)))


def effective_points(q4: float = FOUR_SUB_RATE) -> float:
    """每件的期望词条点数：初始 3 条=8 点、4 条=9 点 → ``8 + q4``。"""
    q = min(1.0, max(0.0, float(q4)))
    return 8.0 + q


def resin_cost(slot: str, main: str, off_piece: bool = False,
               extra_rate: float = EXTRA_DROP_RATE,
               set_share: float = SET_SHARE,
               resin_per_run: float = RESIN_PER_RUN) -> float:
    """某个槽位想要某个主词条的**期望树脂**（``inf`` 表示该槽位出不了这个词条）。

    * 目标套槽：``resin_per_run / (extra_rate 修正后的目标套期望 × p)``
    * 散件槽：``resin_per_run / (件数期望 × p)``（散件不限套装）
    """
    prob = (MAIN_STAT_PROB.get(slot) or {}).get(main)
    if not prob:
        return float("inf")
    per_run = 1.0 + float(extra_rate)
    if not off_piece:
        per_run *= float(set_share)
    return float(resin_per_run) / (per_run * float(prob))


def substat_pool(main: str) -> dict:
    """该主词条可用的副词条池（``{key: 权重}``）。

    主词条本身是副词条之一时要从池里去掉（如攻击% 主词条 → 副词条没有攻击%）；
    元素伤害 / 物理伤害 / 治疗加成没有对应副词条 → 池是满的 10 项。
    """
    exclude = main if main in SUBSTAT_WEIGHT else None
    return {key: w for key, w in SUBSTAT_WEIGHT.items() if key != exclude}


def expected_substat_rolls(main: str, q4: float = FOUR_SUB_RATE) -> dict:
    """某主词条下，**每件**的"某属性期望词条数"（``{key: 词条数}``）。

    期望是线性的：把"不放回抽 3/4 条"与"强化只落在已有词条上"都算进去后，
    某属性的期望词条数恰好 = ``点数 × 该属性权重 / 池总权重``。
    """
    pool = substat_pool(main)
    total_weight = float(sum(pool.values()))
    if not total_weight:
        return {}
    points = effective_points(q4)
    return {
        key: points * weight / total_weight
        for key, weight in pool.items()
    }


def expected_substats(main: str, q4: float = FOUR_SUB_RATE) -> dict:
    """某主词条下，**每件**的"某属性期望数值"（``{key: 数值}``，单位与词条本身一致）。"""
    return {
        key: rolls * SUBSTAT_AVG[key]
        for key, rolls in expected_substat_rolls(main, q4).items()
    }


# ---- 主词条组合（背包）---------------------------------------------------
def main_combos() -> list:
    """所有**主词条组合**（花/羽 固定，沙/杯/冠 各自枚举）。

    返回 ``[{"flower": ..., "plume": ..., "sands": ..., "goblet": ..., "circlet": ...}, …]``，
    条数 = 1 × 1 × 5 × 12 × 7 = **420**（杯有 12 种候选：8 类属性伤害 + 攻击/生命/防御/精通）。
    """
    out: list = []
    for flower in MAIN_STAT_PROB[SLOT_FLOWER]:
        for plume in MAIN_STAT_PROB[SLOT_PLUME]:
            for sands in MAIN_STAT_PROB[SLOT_SANDS]:
                for goblet in MAIN_STAT_PROB[SLOT_GOBLET]:
                    for circlet in MAIN_STAT_PROB[SLOT_CIRCLET]:
                        out.append({
                            SLOT_FLOWER: flower,
                            SLOT_PLUME: plume,
                            SLOT_SANDS: sands,
                            SLOT_GOBLET: goblet,
                            SLOT_CIRCLET: circlet,
                        })
    return out


def combo_cost(mains: dict, off_piece_slot: str | None = None,
               extra_rate: float = EXTRA_DROP_RATE,
               set_share: float = SET_SHARE,
               resin_per_run: float = RESIN_PER_RUN) -> float:
    """一套主词条的**期望树脂成本**：``off_piece_slot`` 那个槽按散件算（便宜一半）。"""
    total = 0.0
    for slot in SLOTS:
        main = mains.get(slot)
        total += resin_cost(slot, main, off_piece=(slot == off_piece_slot),
                            extra_rate=extra_rate, set_share=set_share,
                            resin_per_run=resin_per_run)
    return total


def feasible_combos(budget: float,
                    off_piece_slot: str | None = None,
                    q4: float = FOUR_SUB_RATE,
                    extra_rate: float = EXTRA_DROP_RATE,
                    set_share: float = SET_SHARE,
                    resin_per_run: float = RESIN_PER_RUN,
                    limit: int | None = None) -> list:
    """预算内**买得起**的主词条组合。

    * 每个组合都要决定"哪 1 个槽当散件"（``off_piece_slot`` 为 None 时把 5 个槽都试一遍）；
    * 只保留 ``成本 ≤ budget`` 的，按成本从低到高排（**伤害排序要等接上伤害链**）；
    * ``q4`` 目前只影响副词条期望，不参与主词条成本（留着给下一步统一传参）。

    返回 ``[{"mains": {...}, "offPiece": slot, "cost": float}, …]``。
    """
    budget = float(budget or 0)
    slots_tried = [off_piece_slot] if off_piece_slot else list(SLOTS)
    out: list = []
    for mains in main_combos():
        for slot in slots_tried:
            cost = combo_cost(mains, off_piece_slot=slot, extra_rate=extra_rate,
                              set_share=set_share, resin_per_run=resin_per_run)
            if cost <= budget:
                out.append(dict(mains=dict(mains), offPiece=slot, cost=cost))
    out.sort(key=lambda item: item["cost"])
    return out[:limit] if limit else out

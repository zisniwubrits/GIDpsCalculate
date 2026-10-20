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
* 词条数值取参考表 :data:`relic_tables.RELIC_ROWS` 的**平均值**（副本在包内，不 import 主程序）；
* 4 件套的**效果数值不建模**（用户在圣遗物域里自己固定）。

由上面的规则推出的两个关键量：

* 一件"目标套 + 指定部位 + 指定主词条"的期望树脂 ``20 / (1.065 × 0.5 × 1/5 × p)``；
* 一件"散件槽 + 指定部位 + 指定主词条"的期望树脂 ``20 / (1.065 × 1/5 × p)``。

**三级近似**（用户指定，见 AGENTS.md §1.0）：

1. 5 个部位**严格等概率**（1/5）→ `SLOT_SHARE`；
2. 副本两个套装**严格等概率**（50/50）→ `SET_SHARE`；
3. 初始词条数**严格按 3:4 = 4:1**（即 80% 三词条、20% 四词条）→ `FOUR_SUB_RATE = 0.2`。
"""

from __future__ import annotations

from .relic_tables import RELIC_ROWS

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
    "STATS_ORDER",
    "PIECE_MAX_ROLLS",
    "DEFAULT_TRACKED",
    "piece_states",
    "expected_rolls_from_states",
    "best_of_n",
    "best_of_n_states",
    "POOL_KEYS",
    "check_effective",
    "start_line_sets",
    "effective_lines",
    "pass_probability",
    "filtered_piece_states",
    "filtered_summary",
    "resin_per_accepted",
    "state_lattice",
    "suffix_sum",
    "tail_confidence",
    "combo_cost",
    "main_combos",
    "feasible_combos",
]

# ---- 刷取侧常量 ----------------------------------------------------------
RESIN_PER_RUN = 20              # 一次副本 20 树脂
EXTRA_DROP_RATE = 0.065         # 额外掉一件的概率 → 1.065 件/次
SET_SHARE = 0.5                 # 副本两套各 50%（二级近似：严格等概率）
FOUR_SUB_RATE = 0.2             # 初始 4 词条概率；三级近似：初始三:四 = 4:1（BOSS/周本/三合一是 34%）
UPGRADE_ROLLS = 5               # +4/+8/+12/+16/+20
# 槽位用 ASCII 标识（代码里不要用中文当键）；中文只在界面上显示
SLOT_FLOWER = "flower"      # 生之花
SLOT_PLUME = "plume"        # 死之羽
SLOT_SANDS = "sands"        # 时之沙
SLOT_GOBLET = "goblet"      # 空之杯
SLOT_CIRCLET = "circlet"    # 理之冠
SLOTS = (SLOT_FLOWER, SLOT_PLUME, SLOT_SANDS, SLOT_GOBLET, SLOT_CIRCLET)
# 一级近似：5 个部位严格等概率 → 指定部位要乘 1/5
SLOT_SHARE = 1.0 / len(SLOTS)
# 显示用中文名（只在需要给人看的时候用）
SLOT_LABELS = {
    SLOT_FLOWER: "生之花",
    SLOT_PLUME: "死之羽",
    SLOT_SANDS: "时之沙",
    SLOT_GOBLET: "空之杯",
    SLOT_CIRCLET: "理之冠",
}


# ---- 副词条：权重 + 平均值（平均值取自包内副本 relic_tables.RELIC_ROWS）-----
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
    for row in RELIC_ROWS:
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
               slot_share: float = SLOT_SHARE,
               resin_per_run: float = RESIN_PER_RUN) -> float:
    """某个槽位想要某个主词条的**期望树脂**（``inf`` 表示该槽位出不了这个词条）。

    * 目标套槽：``resin_per_run / (件数期望 × 套装份额 × 部位份额 × p)``
    * 散件槽：``resin_per_run / (件数期望 × 部位份额 × p)``（散件不限套装）

    一级近似：**5 个部位严格等概率**（`SLOT_SHARE = 1/5`），所以要"指定部位"时
    必须乘这 1/5，否则成本会偏小 5 倍（曾经踩过）。
    """
    prob = (MAIN_STAT_PROB.get(slot) or {}).get(main)
    if not prob:
        return float("inf")
    per_run = 1.0 + float(extra_rate)
    if not off_piece:
        per_run *= float(set_share)
    per_run *= float(slot_share)
    return float(resin_per_run) / (per_run * float(prob))


def substat_pool(main: str) -> dict:
    """该主词条可用的副词条池（``{key: 权重}``）。

    主词条本身是副词条之一时要从池里去掉（如攻击% 主词条 → 副词条没有攻击%）；
    元素伤害 / 物理伤害 / 治疗加成没有对应副词条 → 池是满的 10 项。
    """
    exclude = main if main in SUBSTAT_WEIGHT else None
    return {key: w for key, w in SUBSTAT_WEIGHT.items() if key != exclude}


def substat_inclusion(main: str) -> dict:
    """每条副词条"**出现在这件上**"的精确概率（不放回加权抽样，不是 4w/W 近似）。"""
    from itertools import combinations

    pool = substat_pool(main)
    out: dict = {key: 0.0 for key in pool}
    for combo in combinations(pool, 4):
        prob = _subset_prob(pool, combo)
        for key in combo:
            out[key] += prob
    return out


def expected_substat_rolls(main: str, q4: float = FOUR_SUB_RATE) -> dict:
    """某主词条下，**每件**的"某属性期望词条数"（``{key: 词条数}``）。

    精确算法：``E[次数_i] = P(该属性出现) × (1 + 强化期望次数)``。

    * ``P(该属性出现)`` 用不放回加权抽样的**精确**入选概率（见 :func:`substat_inclusion`）；
    * 出现之后：初始 1 次 + 5 次强化在 4 条里等概率分（期望 5/4），
      3 词条起手时是 1 + 4/4；按 q4 加权 → ``1 + (q4·5 + (1−q4)·4)/4``。
    """
    inclusion = substat_inclusion(main)
    extra = (float(q4) * UPGRADE_ROLLS + (1.0 - float(q4)) * (UPGRADE_ROLLS - 1)) / 4.0
    return {key: prob * (1.0 + extra) for key, prob in inclusion.items()}


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


# ---- 单槽模型：单件状态分布 → 累积 → N 件里最好的分布 -------------------
# 词条值统一取平均值（用户口径），所以一件圣遗物 = 每个属性的"词条次数"整数向量。
# 一次强化最多让某条从 1 次涨到 6 次（4 条起手 1 + 5 次强化）。
PIECE_MAX_ROLLS = 6
# 默认只跟踪"会进伤害公式"的属性（其余属性只占词条池，不单独建轴）。
DEFAULT_TRACKED = ("crit_rate", "crit_dmg", "atk_pct", "atk_flat", "em")


def _perm_prob(order, pool: dict) -> float:
    """按权重不放回抽出的**有序**序列概率。"""
    total = float(sum(pool.values()))
    prob = 1.0
    used = 0.0
    for key in order:
        prob *= float(pool[key]) / (total - used)
        used += float(pool[key])
    return prob


def _subset_prob(pool: dict, combo) -> float:
    """抽到某个**无序**子集（不计顺序）的概率 = 所有排列的概率之和。"""
    from itertools import permutations

    return sum(_perm_prob(order, pool) for order in permutations(combo))


def _extra_compositions(extra: int, parts: int) -> dict:
    """把 ``extra`` 次额外强化分给 ``parts`` 条词条的所有方式 → 概率（等概率多项式）。"""
    from itertools import product

    out: dict = {}
    total = float(parts) ** extra
    for split in product(range(extra + 1), repeat=parts):
        if sum(split) != extra:
            continue
        # 多项式系数 = extra! / Π split!
        coeff = _factorial(extra)
        for count in split:
            coeff //= _factorial(count)
        out[split] = coeff / total
    return out


def _factorial(n: int) -> int:
    out = 1
    for k in range(2, n + 1):
        out *= k
    return out


def piece_states(main: str, q4: float = FOUR_SUB_RATE,
                 tracked=DEFAULT_TRACKED) -> dict:
    """**单件**圣遗物的状态分布：``{(词条次数向量): 概率}``。

    状态只保留 ``tracked`` 里的属性（别的属性只占词条池，不影响伤害）；
    词条次数是整数，数值 = 次数 × 平均值。

    * 4 条起手（概率 ``1-q4``）：4 条各 1 次 + 5 次强化（多项式分布）；
    * 3 条起手（概率 ``q4``）：3 条各 1 次 + +4 级补第 4 条 1 次 + 4 次强化。
      两种起手最终都是"4 条各至少 1 次"，区别只在总点数 9 / 8。
    """
    from itertools import combinations

    pool = substat_pool(main)
    keys = tuple(pool)
    index = {key: i for i, key in enumerate(tracked)}
    states: dict = {}

    def add(combo, counts, prob: float) -> None:
        vector = [0] * len(tracked)
        for key, count in zip(combo, counts):
            slot = index.get(key)
            if slot is not None:
                vector[slot] += count
        states[tuple(vector)] = states.get(tuple(vector), 0.0) + prob

    # q4 = 初始 4 词条的概率（副本 20%）→ 9 个词条点；否则 3 词条起手 → 8 个点
    for size, extra, weight in ((4, UPGRADE_ROLLS, float(q4)),
                                (4, UPGRADE_ROLLS - 1, 1.0 - float(q4))):
        for combo in combinations(keys, size):
            p_sub = _subset_prob(pool, combo) * weight
            if not p_sub:
                continue
            for split, p_split in _extra_compositions(extra, size).items():
                add(combo, [1 + value for value in split], p_sub * p_split)
    return states


def expected_rolls_from_states(states: dict, tracked=DEFAULT_TRACKED) -> dict:
    """用单件状态分布算"每件各属性的期望词条次数"（键是属性名）。"""
    out: dict = {name: 0.0 for name in tracked}
    for vector, prob in states.items():
        for i, count in enumerate(vector):
            if count:
                out[tracked[i]] += count * prob
    return out


def state_scalar(vector, tracked=DEFAULT_TRACKED) -> float:
    """把一个状态映射成**标量**（默认 = 跟踪属性的词条总数）。

    "最好"必须是标量比较：状态向量之间是偏序，互不支配时没有"最好"这回事，
    而"有效词条最多"本身就是标量，所以先用词条总数排序（之后可换成真实伤害）。
    """
    return float(sum(vector))


def _scalar_distribution(states: dict, score) -> dict:
    """{状态: 概率} → {分数: 概率}（同一分数的状态概率相加）。"""
    out: dict = {}
    for vector, prob in states.items():
        key = score(vector)
        out[key] = out.get(key, 0.0) + prob
    return out


def best_of_n(states: dict, n: int, score=state_scalar) -> dict:
    """N 个胚子里"最好那个"的分数分布（用户的万能通式）。

    ``P_N[s] = S[s]^n − (S[s] − P₁[s])^n``

    * ``S[s]``：单件分数 ≤ s 的累积概率；
    * 物理意义：N 件都不超过 s，减去 N 件都严格劣于 s；
    * 要求按**标量**排序（分数），状态向量本身是偏序、不能直接套这个式子。
    """
    if n <= 0:
        raise ValueError("n 必须为正整数")
    base = _scalar_distribution(states, score) if score else dict(states)
    scores = sorted(base)
    out: dict = {}
    cum = 0.0
    for value in scores:
        p1 = base[value]
        cum = min(1.0, cum + p1)          # S[s]：≤ s 的累积
        if n == 1:
            out[value] = p1
            continue
        below = max(0.0, cum - p1)        # S[s] − P₁[s]：严格劣于 s
        if cum <= 0.0 or p1 <= 0.0:
            out[value] = 0.0
        else:
            # 写成 S^n·(1 − (1−P/S)^n)，避免两个接近 1 的数相减丢精度
            out[value] = cum ** n * (1.0 - (below / cum) ** n)
    return out


def expected_scalar(dist: dict) -> float:
    """一个标量分布 {值: 概率} 的期望。"""
    return sum(value * prob for value, prob in dist.items())


# ---- 口径 B：向量状态的 best-of-N（P_N[v]）--------------------------------
def total_state_key(vector) -> tuple:
    """默认的**全序键**：``(词条总数, 向量本身)``。

    向量之间只有偏序，套不了 :func:`best_of_n`；这里补一个确定性的细化：
    先比词条总数（= 现在的"有效词条数"口径），同分再按向量字典序。
    将来接上真实伤害后，换 ``key=lambda v: (damage(v), tuple(v))`` 即可。
    """
    return (state_scalar(vector), tuple(vector))


def best_of_n_states(states: dict, n: int, key=total_state_key) -> dict:
    """N 个胚子里"最好那个"的**状态分布** ``{状态向量: 概率}``（口径 B）。

    与 :func:`best_of_n` 是同一个通式，只是累积按**全序**做，因此输出到向量层：

        ``P_N[v] = S[v]^n − (S[v] − P₁[v])^n``，``S[v] = Σ_{w ≤ v} P₁[w]``

    参数 ``key`` 必须把状态映射到**可哈希且互不相同**的全序键：

    * 互不相同是硬要求——两个不同状态同键时"最好那个恰好等于 v"没有定义，
      这里直接 ``ValueError``，**不**静默合并（合并后只能得到"分数层"的分布，
      那是 :func:`best_of_n` 的事）；
    * 想让"最好"= 伤害最大，就用 ``key=lambda v: (damage(v), tuple(v))``：
      伤害相同时由向量字典序打破并列。

    概率和保证为 1（``n`` 件独立同分布时的严格结果，非抽样）。
    """
    if n <= 0:
        raise ValueError("n 必须为正整数")
    key = key or total_state_key
    tokens: dict = {}
    owner: dict = {}
    for vector in states:
        token = key(vector)
        if token in owner:
            raise ValueError(
                "排序键不唯一：%r 与 %r 同键 %r，需要更细的排序规则（如追加向量本身）"
                % (owner[token], vector, token))
        owner[token] = vector
        tokens[vector] = token

    out: dict = {}
    cum = 0.0
    for vector in sorted(states, key=lambda v: tokens[v]):
        p1 = states[vector]
        cum = min(1.0, cum + p1)          # S[v]：全序下 ≤ v 的累积
        if n == 1:
            out[vector] = p1
            continue
        below = max(0.0, cum - p1)        # S[v] − P₁[v]：严格劣于 v
        if cum <= 0.0 or p1 <= 0.0:
            out[vector] = 0.0
        else:
            # 同 best_of_n：写成 S^n·(1 − (1−P/S)^n) 避免大 n 时丢精度
            out[vector] = cum ** n * (1.0 - (below / cum) ** n)
    return out


# ---- 带筛选的刷取模型：有效词条 + 接受条件 --------------------------------
# 副词条池：10 项（元素伤害 / 物理 / 治疗加成没有副词条，不进池）
POOL_KEYS = tuple(SUBSTAT_LABELS)


def check_effective(effective) -> tuple:
    """规范化「明显有效词条」集合。

    用户可以任选 **1~10 项**（攻击型通常 4~5 项，辅助可能只有 1 项如充能）：
    顺序保留、去重、必须是副词条池里的键，不得为空。
    """
    if isinstance(effective, str):
        raise ValueError("有效词条要传序列（如 ('crit_rate', 'crit_dmg')），不是单个字符串")
    out: list = []
    for key in effective:
        if key not in SUBSTAT_LABELS:
            raise ValueError("未知词条: %r（可选：%s）" % (key, ", ".join(POOL_KEYS)))
        if key not in out:
            out.append(key)
    if not out:
        raise ValueError("有效词条不能为空")
    return tuple(out)


def start_line_sets(main: str, q4: float = FOUR_SUB_RATE) -> dict:
    """判定时刻「4 条词条集合」的分布：``{(frozenset(4 条), 起手类型): 概率}``。

    判定时机（用户口径）：

    * ``four``（4 条起手，概率 ``q4``）：**+0** 就有 4 条，直接判；
    * ``three``（3 条起手，概率 ``1-q4``）：升到 **+4** 补出第 4 条后再判。

    两种起手的**集合分布相同**（恒等式：先抽 3 条再补 1 条，就是"第 4 次顺序抽样"，
    与直接抽 4 条完全一致；由 ``test_four_and_three_starts_share_the_same_set_distribution``
    守住）。所以这里只算一次"顺序抽 4 条"的概率，再按起手概率分发；
    两种起手的差别只在**后续强化次数**（9 点 vs 8 点），见 :func:`filtered_piece_states`。
    """
    from itertools import combinations

    pool = substat_pool(main)
    keys = tuple(pool)
    p4 = float(q4)
    p3 = 1.0 - p4
    out: dict = {}
    for combo in combinations(keys, 4):
        prob = _subset_prob(pool, combo)
        out[(frozenset(combo), "four")] = prob * p4
        out[(frozenset(combo), "three")] = prob * p3
    return out


def effective_lines(lines, effective) -> int:
    """这 4 条里有几条属于「有效词条」。"""
    return len(frozenset(effective) & frozenset(lines))


def pass_probability(main: str, effective, min_effective: int = 1,
                     q4: float = FOUR_SUB_RATE) -> float:
    """胚子通过接受条件（有效条数 ``>= min_effective``）的概率。"""
    eff = check_effective(effective)
    if min_effective < 0:
        raise ValueError("min_effective 不能为负")
    return sum(prob for (lines, _kind), prob in start_line_sets(main, q4).items()
               if effective_lines(lines, eff) >= min_effective)


def filtered_piece_states(main: str, effective, min_effective: int = 1,
                          q4: float = FOUR_SUB_RATE, tracked=None) -> dict:
    """**通过筛选的件在满级时**的状态分布（条件分布，和为 1）。

    * 未通过的胚子**直接丢弃**（用户口径：不投强化、不产出）；
    * 通过的件继续强化到 +20：4 起手再强化 5 次（9 点），3 起手再强化 4 次（8 点）；
    * 默认 ``tracked = effective``，即状态只保留有效词条的次数；
      传更宽的 ``tracked``（如 ``STATS_ORDER``）可保留其它属性的次数，便于接伤害打分。
    """
    eff = check_effective(effective)
    tracked = tuple(tracked) if tracked is not None else eff
    index = {key: i for i, key in enumerate(tracked)}
    accepted = {key: prob for key, prob in start_line_sets(main, q4).items()
                if effective_lines(key[0], eff) >= min_effective}
    total = sum(accepted.values())
    if total <= 0.0:
        raise ValueError("没有胚子能通过该条件（至少要 %d 个有效词条）" % min_effective)

    states: dict = {}
    for (lines, kind), prob in accepted.items():
        extra = UPGRADE_ROLLS if kind == "four" else UPGRADE_ROLLS - 1
        order = sorted(lines)
        share = prob / total
        for split, p_split in _extra_compositions(extra, 4).items():
            vector = [0] * len(tracked)
            for key, count in zip(order, split):
                slot = index.get(key)
                if slot is not None:
                    vector[slot] += 1 + count
            vector = tuple(vector)
            states[vector] = states.get(vector, 0.0) + share * p_split
    return states


def filtered_summary(main: str, effective, min_effective: int = 1,
                     q4: float = FOUR_SUB_RATE, tracked=None) -> dict:
    """筛选模型的一站式结果：通过率、条件状态分布、有效词条期望、件数期望。"""
    eff = check_effective(effective)
    rate = pass_probability(main, eff, min_effective, q4)
    out = {"pass_rate": rate, "effective": eff, "min_effective": min_effective,
           "tracked": tuple(tracked) if tracked is not None else eff}
    if rate <= 0.0:
        out["states"] = {}
        out["expected_rolls"] = {}
        return out
    states = filtered_piece_states(main, eff, min_effective, q4, tracked=out["tracked"])
    out["states"] = states
    out["expected_rolls"] = expected_rolls_from_states(states, out["tracked"])
    return out


def resin_per_accepted(slot: str, main: str, effective, min_effective: int = 1,
                       off_piece: bool = False, q4: float = FOUR_SUB_RATE) -> float:
    """一件**通过筛选且满级**的圣遗物的期望树脂 = 单件树脂 / 通过率。

    强化材料不建模（用户口径：垃圾胚子本身就是强化材料，不额外算树脂）。
    """
    rate = pass_probability(main, effective, min_effective, q4)
    if rate <= 0.0:
        return float("inf")
    return resin_cost(slot, main, off_piece=off_piece) / rate


# ---- 置信度：n 个胚之后"至少达到 v"的概率（逐分量后缀和）------------------
def state_lattice(dims: int, max_points: int = 9, max_lines: int = 4) -> list:
    """单件可能出现的所有状态向量 v（维度 = 有效词条数）。

    约束来自物理事实：一件五星圣遗物只有 **4 条**副词条、**8 或 9** 个词条点，
    所以 `非零分量数 ≤ 4`、`分量和 ≤ 9`。按"选支撑集 + 正整数拆分"生成，
    不遍历 `10^dims`（dims 大到 10 也不会爆）。
    """
    from itertools import combinations

    if dims <= 0:
        raise ValueError("dims 必须为正整数")
    out = [tuple([0] * dims)]
    for size in range(1, min(max_lines, dims) + 1):
        for support in combinations(range(dims), size):
            for total in range(size, max_points + 1):
                for split in _extra_compositions(total - size, size):
                    vector = [0] * dims
                    for index, extra in zip(support, split):
                        vector[index] = extra + 1
                    out.append(tuple(vector))
    return out


def suffix_sum(states: dict, grid=None) -> dict:
    """逐分量**后缀和**：``q[v] = Σ_{w ≥ v} ω(w)``（每个维度都不小于 v）。

    输入 ``{状态: 权重}``；``grid`` 缺省时用 :func:`state_lattice` 覆盖的全部状态。
    在格点上做多维累积（每维从大到小一遍），复杂度 `O(dims × |grid|)`。
    """
    if not states:
        return {}
    dims = len(next(iter(states)))
    grid = state_lattice(dims) if grid is None else grid
    q = {vector: float(states.get(vector, 0.0)) for vector in grid}
    for axis in range(dims):
        for vector in sorted(grid, key=lambda v: -v[axis]):
            above = list(vector)
            above[axis] += 1
            add = q.get(tuple(above))
            if add:
                q[vector] += add
    return q


def tail_confidence(main: str, effective, k: int, n: int,
                    q4: float = FOUR_SUB_RATE, unit: str = "piece",
                    extra_rate: float = EXTRA_DROP_RATE) -> dict:
    """拿到 ``n`` 次机会之后，"至少有一件每个有效维度都不小于 v"的置信度。

    用户口径：

    * ``effective``：有效词条种类集合（长度 1~5，这里允许 1~10）；
    * ``k``（1~4）：胚的定义。4 条起手看**初始 4 条**里有效条数 ≥ k；
      3 条起手看**初始 3 条 + +4 的那一条**共 4 条里有效条数 ≥ k；
    * ``n`` + ``unit``：计数的单位
      - ``"piece"``（默认）：n 个**通过筛选的胚**；
      - ``"run"``：n **次副本**——每次必掉 1 件、另有 ``extra_rate`` 概率再掉 1 件，
        即每轮 1 或 2 件（各自独立过筛选）；
    * 返回值形状：``{(v1, v2, …): 置信度}``，覆盖所有单件可能出现的 v。

    口径唯一：**任一件逐分量支配 v 即算**（= 逐分量最大值分布的后缀和）

        ``q_v = Σ_{w ≥ v} P₁[w]``，``P[v] = 1 − (1 − q_v)^n``

    ``unit="run"`` 时精确换成 ``1 − [(1−q_v)(1−extra_rate·q_v)]^n``
    （每轮 1 件的概率 ``1−extra_rate``、2 件的概率 ``extra_rate``）。
    """
    from math import expm1, log1p

    eff = check_effective(effective)
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("n 必须是正整数")
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 4:
        raise ValueError("k 取 1~4（胚要求初始可见的 4 条里至少几个有效）")
    if unit not in ("piece", "run"):
        raise ValueError("unit 只能是 'piece'（胚数）或 'run'（刷本次数）")

    states = filtered_piece_states(main, eff, k, q4, tracked=eff)
    single = suffix_sum(states, state_lattice(len(eff)))     # q_v
    out: dict = {}
    for vector, prob in single.items():
        if prob <= 0.0:
            out[vector] = 0.0
        elif prob >= 1.0:
            out[vector] = 1.0
        else:
            if unit == "piece":
                miss = log1p(-prob)                     # log(1−q)
            else:
                # 每轮 1 件的概率 1−r、2 件的概率 r；全不达标 = (1−q)·(1−r·q)
                miss = log1p(-prob) + log1p(-float(extra_rate) * prob)
            # 1 − exp(n·log miss) 用 expm1，避免小 q、大 n 时丢精度
            out[vector] = -expm1(n * miss)
    return out


# ---- 伤害函数抽象层 -------------------------------------------------------
# 只考虑副词条时，会进伤害公式的恰好是这 9 项（顺序固定，下标即 ABI）
STATS_ORDER = (
    "atk_pct",      # 0 百分数
    "atk_flat",     # 1 绝对值
    "hp_pct",       # 2 百分数
    "hp_flat",      # 3 绝对值
    "def_pct",      # 4 百分数
    "def_flat",     # 5 绝对值
    "em",           # 6 绝对值
    "crit_rate",    # 7 百分数
    "crit_dmg",     # 8 百分数
)

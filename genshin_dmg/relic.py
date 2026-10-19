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
    "STATS_ORDER",
    "GraphDamageFn",
    "damage_fn_from_project",
    "PIECE_MAX_ROLLS",
    "DEFAULT_TRACKED",
    "piece_states",
    "expected_rolls_from_states",
    "best_of_n",
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


class GraphDamageFn:
    """**解释层**实现：``stats(9 个 float) → 期望伤害``，内部跑现有工程链。

    这是 DLL 的基准实现（慢但绝对可信）：属性以 ``Graph.extra_own`` 注入该角色
    （算作"自身"，进 ``own::``），再取该角色 ★结果卡的 ``expected``。

    * ``calc(xs)``：单次，返回 ``float``；
    * ``calc_batch(rows)``：批量，``rows`` 是 ``len(xs)//9`` 组扁平输入（行优先），返回 ``list[float]``；
    * 长度不对 / 非有限数 → ``ValueError``（不静默返回 0）。
    """

    def __init__(self, graph, role: str):
        from .graph import Graph

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

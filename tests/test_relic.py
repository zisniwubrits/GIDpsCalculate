# -*- coding: utf-8 -*-
"""圣遗物「刷取换算层」的测试：树脂 → 件数 / 主词条成本 / 副词条期望。

这一层是纯算术，不涉及伤害链，所以断言的都是可以直接手算的数值。
"""

import math
import unittest

from genshin_dmg.GIRelic import relic, relic_adapter, relic_tables


class TestTables(unittest.TestCase):
    def test_substat_weight_total_and_relations(self):
        """权重：生命/攻击/防御 150、双爆 75、其余 100，总 1100。"""
        w = relic.SUBSTAT_WEIGHT
        self.assertEqual(sum(w.values()), 1100)
        self.assertEqual(w["hp_flat"], 150)
        self.assertEqual(w["atk_pct"], 100)
        self.assertEqual(w["crit_rate"], 75)
        self.assertEqual(w["crit_dmg"], 75)
        for key in ("hp_pct", "def_pct", "er", "em"):
            self.assertEqual(w[key], 100, key)
        # 三条固定值（生命/攻击/防御）都是 150
        self.assertEqual(w["def_flat"], 150)

    def test_substat_average_comes_from_reference_table(self):
        """平均值直接取参考表第 4 列（不许另抄一份数字）。"""
        rows = {row[0]: float(row[3]) for row in relic_tables.RELIC_ROWS}
        self.assertAlmostEqual(relic.SUBSTAT_AVG["crit_rate"], rows["暴击率（%）"])
        self.assertAlmostEqual(relic.SUBSTAT_AVG["crit_dmg"], rows["暴击伤害（%）"])
        self.assertAlmostEqual(relic.SUBSTAT_AVG["em"], rows["元素精通"])
        # 参考表里的数值本身
        self.assertAlmostEqual(relic.SUBSTAT_AVG["crit_rate"], 3.305, places=6)
        self.assertAlmostEqual(relic.SUBSTAT_AVG["em"], 19.815, places=6)

    def test_main_stat_probability_sums_to_one(self):
        """每个部位的主词条概率合计 100%；杯含 7 元素 + 物理共 8 类属性伤害，各 5%。"""
        for slot in relic.SLOTS:
            total = sum(relic.MAIN_STAT_PROB[slot].values())
            self.assertAlmostEqual(total, 1.0, places=6, msg=slot)

        cup = relic.MAIN_STAT_PROB[relic.SLOT_GOBLET]
        self.assertEqual(len(relic.DAMAGE_MAINS), 8)          # 7 元素 + 物理
        for key in relic.DAMAGE_MAINS:
            self.assertAlmostEqual(cup[key], 0.05, places=6, msg=key)
        self.assertAlmostEqual(cup["hp_pct"], 0.1925)
        self.assertAlmostEqual(cup["em"], 0.025)

    def test_main_stat_values_match_game_table(self):
        """五星 +20 满级值（用户核对过的那张表）。"""
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_FLOWER]["hp_flat"], 4780)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_PLUME]["atk_flat"], 311)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_SANDS]["atk_pct"], 46.6)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_SANDS]["er"], 51.8)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_SANDS]["em"], 187)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_GOBLET]["dmg_pyro"], 46.6)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_GOBLET]["dmg_physical"], 58.3)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_CIRCLET]["crit_rate"], 31.1)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_CIRCLET]["crit_dmg"], 62.2)
        self.assertAlmostEqual(relic.MAIN_STAT_VALUE[relic.SLOT_CIRCLET]["heal"], 35.9)


class TestPieces(unittest.TestCase):
    def test_pieces_for_resin(self):
        """每次 1 件 + 6.5% 额外 = 1.065 件/次；目标套占一半。"""
        got = relic.pieces_for_resin(360)
        self.assertAlmostEqual(got["runs"], 18.0)              # 360 / 20
        self.assertAlmostEqual(got["total"], 18 * 1.065)       # 19.17
        self.assertAlmostEqual(got["target_set"], 18 * 1.065 * 0.5)
        self.assertAlmostEqual(got["off_set"], 18 * 1.065 * 0.5)
        # 树脂为 0 / 负数 → 一件都没有
        self.assertEqual(relic.pieces_for_resin(0)["total"], 0.0)
        self.assertEqual(relic.pieces_for_resin(-40)["total"], 0.0)

    def test_pieces_accepts_other_resin_per_run(self):
        """浓缩/其它副本口径可以传参（目前主流程只用 20）。"""
        got = relic.pieces_for_resin(60, resin_per_run=20)
        self.assertAlmostEqual(got["runs"], 3.0)


class TestResinCost(unittest.TestCase):
    def test_cost_for_target_set_slot(self):
        """目标套槽：20 / (1.065 × 0.5 × 1/5 × p)（部位严格等概率 → 乘 1/5）。"""
        cost = relic.resin_cost(relic.SLOT_SANDS, "atk_pct")
        p = relic.MAIN_STAT_PROB[relic.SLOT_SANDS]["atk_pct"]
        self.assertAlmostEqual(cost, 20 / (1.065 * 0.5 * 0.2 * p), places=6)
        # 沙·攻击% ≈ 704 树脂
        self.assertAlmostEqual(cost, 704.4, places=1)

    def test_slot_share_is_one_fifth(self):
        """一级近似：5 个部位严格等概率。不加这个因子成本会偏小 5 倍。"""
        self.assertAlmostEqual(relic.SLOT_SHARE, 0.2, places=12)
        base = relic.resin_cost("sands", "atk_pct", slot_share=1.0)
        with_share = relic.resin_cost("sands", "atk_pct")
        self.assertAlmostEqual(with_share, base * 5.0, places=6)

    def test_cost_for_off_piece_slot(self):
        """散件槽不限套装：正好是目标套槽的一半。"""
        target = relic.resin_cost(relic.SLOT_SANDS, "atk_pct")
        off = relic.resin_cost(relic.SLOT_SANDS, "atk_pct", off_piece=True)
        self.assertAlmostEqual(off, target / 2, places=6)
        # 沙·攻击% 的散件槽 ≈ 352 树脂（比目标套槽的 704 便宜一半）
        p = relic.MAIN_STAT_PROB[relic.SLOT_SANDS]["atk_pct"]
        self.assertAlmostEqual(off, 20 / (1.065 * 0.2 * p), places=6)

    def test_cost_of_rare_elemental_cup(self):
        """元素伤害杯每类只有 5% → 明显更贵。"""
        cost = relic.resin_cost(relic.SLOT_GOBLET, "dmg_pyro")
        self.assertAlmostEqual(cost, 20 / (1.065 * 0.5 * 0.2 * 0.05), places=6)
        self.assertAlmostEqual(cost, 3755.9, places=1)
        # 物理单独一类，也一样贵
        self.assertAlmostEqual(relic.resin_cost(relic.SLOT_GOBLET, "dmg_physical"), cost, places=6)

    def test_impossible_main_returns_inf(self):
        """该部位出不了这个词条 → inf（如沙没有暴击率）。"""
        self.assertTrue(math.isinf(relic.resin_cost(relic.SLOT_SANDS, "crit_rate")))
        self.assertTrue(math.isinf(relic.resin_cost(relic.SLOT_FLOWER, "atk_pct")))


class TestSubstats(unittest.TestCase):
    def test_points_per_piece(self):
        """初始 4 条 20% → 每件 8.2 个词条点。"""
        self.assertAlmostEqual(relic.effective_points(0.20), 8.2)
        self.assertAlmostEqual(relic.effective_points(0.0), 8.0)
        self.assertAlmostEqual(relic.effective_points(0.34), 8.34)

    def test_pool_excludes_the_main_stat(self):
        """主词条本身是副词条时，要从池里去掉（沙·攻击% → 池 9 项）。"""
        pool = relic.substat_pool("atk_pct")
        self.assertEqual(len(pool), 9)
        self.assertNotIn("atk_pct", pool)
        self.assertEqual(sum(pool.values()), 1000)
        # 元素伤害主词条没有对应副词条 → 池是满的 10 项
        self.assertEqual(len(relic.substat_pool("dmg_pyro")), 10)
        self.assertEqual(sum(relic.substat_pool("dmg_pyro").values()), 1100)

    def test_expected_rolls_sum_to_points_and_use_exact_inclusion(self):
        """期望词条数合计 = 每件点数；单属性 = 精确入选概率 × 出现后的期望次数。"""
        rolls = relic.expected_substat_rolls("atk_pct")     # 池 9 项（去掉攻击%）
        self.assertAlmostEqual(sum(rolls.values()), 8.2, places=6)

        inclusion = relic.substat_inclusion("atk_pct")
        self.assertAlmostEqual(sum(inclusion.values()), 4.0, places=9)   # 共 4 条副词条
        # 出现之后：初始 1 次 + 0.2×5/4 + 0.8×4/4 = 2.05 次
        self.assertAlmostEqual(rolls["crit_rate"], inclusion["crit_rate"] * 2.05, places=9)
        self.assertAlmostEqual(rolls["em"], inclusion["em"] * 2.05, places=9)
        # 不放回加权抽样下，入选概率略高于"4×权重/总权重"这个近似
        self.assertGreater(inclusion["crit_rate"], 4 * 75 / 1000)
        # 攻击% 被主词条占掉，不在副词条里
        self.assertNotIn("atk_pct", rolls)

    def test_expected_values(self):
        """期望数值 = 期望词条数 × 平均词条值。"""
        values = relic.expected_substats("atk_pct")
        rolls = relic.expected_substat_rolls("atk_pct")
        self.assertAlmostEqual(
            values["crit_dmg"], rolls["crit_dmg"] * relic.SUBSTAT_AVG["crit_dmg"], places=9)
        # 沙·攻击% 下，暴击率的期望数值 ≈ 0.673 词条 × 3.305
        self.assertAlmostEqual(values["crit_rate"], rolls["crit_rate"] * 3.305, places=9)

    def test_four_sub_rate_changes_expectation(self):
        """初始 4 词条概率越高，词条期望越多（副本 20% / BOSS 34%）。"""
        domain = relic.expected_substats("atk_pct", q4=0.20)
        boss = relic.expected_substats("atk_pct", q4=0.34)
        self.assertGreater(boss["crit_rate"], domain["crit_rate"])


class TestMainCombos(unittest.TestCase):
    def test_candidate_counts(self):
        """沙 5 / 杯 12（8 类属性伤害 + 攻击/生命/防御/精通）/ 冠 7 → 组合 420。"""
        self.assertEqual(len(relic.MAIN_STAT_PROB[relic.SLOT_SANDS]), 5)
        self.assertEqual(len(relic.MAIN_STAT_PROB[relic.SLOT_GOBLET]), 12)
        self.assertEqual(len(relic.MAIN_STAT_PROB[relic.SLOT_CIRCLET]), 7)
        self.assertEqual(len(relic.main_combos()), 1 * 1 * 5 * 12 * 7)

    def test_each_combo_covers_all_slots(self):
        """每个组合都给出 5 个槽位，且主词条在该槽位的候选表里。"""
        for combo in relic.main_combos():
            self.assertEqual(set(combo), set(relic.SLOTS))
            for slot, main in combo.items():
                self.assertIn(main, relic.MAIN_STAT_PROB[slot], slot)

    def test_combo_cost_sums_slots_and_off_piece_is_cheaper(self):
        """总成本 = 各槽相加；把某槽当散件 → 总成本少掉那个槽的一半。"""
        combo = {
            relic.SLOT_FLOWER: "hp_flat",
            relic.SLOT_PLUME: "atk_flat",
            relic.SLOT_SANDS: "atk_pct",
            relic.SLOT_GOBLET: "atk_pct",
            relic.SLOT_CIRCLET: "crit_rate",
        }
        target = relic.combo_cost(combo)
        manual = sum(relic.resin_cost(slot, main) for slot, main in combo.items())
        self.assertAlmostEqual(target, manual, places=6)

        off = relic.combo_cost(combo, off_piece_slot=relic.SLOT_GOBLET)
        goblet = relic.resin_cost(relic.SLOT_GOBLET, "atk_pct")
        self.assertAlmostEqual(off, target - goblet / 2, places=6)

    def test_budget_filters_combos(self):
        """预算太低 → 一套都买不起；预算足够 → 全部组合都可行。"""
        self.assertEqual(relic.feasible_combos(1000), [])         # 最低成本 ≈ 2421
        every = relic.feasible_combos(100000)
        self.assertEqual(len(every), len(relic.main_combos()) * len(relic.SLOTS))
        for item in every:
            self.assertIn(item["offPiece"], relic.SLOTS)
            self.assertLessEqual(item["cost"], 100000)

    def test_feasible_combos_sorted_and_within_budget(self):
        """返回结果按成本从低到高、都不超预算。"""
        got = relic.feasible_combos(8000)
        self.assertTrue(got)
        costs = [item["cost"] for item in got]
        self.assertEqual(costs, sorted(costs))
        self.assertLessEqual(max(costs), 8000)
        # 每一条的"哪个槽当散件"只会是 5 个部位之一
        self.assertTrue({item["offPiece"] for item in got} <= set(relic.SLOTS))

    def test_can_pin_the_off_piece_slot(self):
        """指定散件槽（比如固定让杯当散件）时，只按那一个槽折算。"""
        got = relic.feasible_combos(100000, off_piece_slot=relic.SLOT_GOBLET)
        self.assertEqual(len(got), len(relic.main_combos()))
        self.assertTrue(all(item["offPiece"] == relic.SLOT_GOBLET for item in got))

    def test_limit(self):
        self.assertEqual(len(relic.feasible_combos(100000, limit=7)), 7)


class TestSinglePieceModel(unittest.TestCase):
    """单槽模型：单件状态分布 → 累积 → N 件里最好的分布（万能通式）。"""

    def test_piece_states_is_a_distribution(self):
        """单件状态分布：概率和为 1，状态里只出现被跟踪的属性。"""
        for q4 in (0.0, 0.2, 0.34, 1.0):
            states = relic.piece_states("atk_pct", q4=q4)
            self.assertAlmostEqual(sum(states.values()), 1.0, places=9)
            for vector in states:
                self.assertEqual(len(vector), len(relic.DEFAULT_TRACKED))

    def test_piece_states_match_analytic_expectation(self):
        """枚举出来的期望词条次数，必须与解析公式一模一样（最强的正确性检查）。"""
        for main in ("atk_pct", "crit_rate", "em", "dmg_pyro"):
            states = relic.piece_states(main)
            got = relic.expected_rolls_from_states(states)
            want = relic.expected_substat_rolls(main)
            for key in relic.DEFAULT_TRACKED:
                self.assertAlmostEqual(got[key], want.get(key, 0.0), places=9,
                                       msg="%s/%s" % (main, key))

    def test_piece_states_points_follow_q4(self):
        """初始 4 词条概率越高，单件词条点越多（20% → 8.2 点，全是 4 条 → 9 点）。"""
        every = tuple(relic.SUBSTAT_WEIGHT)          # 全部 10 条副词条，才能数出总点数

        def points(q4):
            states = relic.piece_states("atk_pct", q4=q4, tracked=every)
            return sum(relic.expected_rolls_from_states(states, tracked=every).values())

        self.assertAlmostEqual(points(0.0), 8.0, places=9)
        self.assertAlmostEqual(points(1.0), 9.0, places=9)
        self.assertAlmostEqual(points(0.2), 8.2, places=9)

    def test_scalar_is_the_effective_roll_count(self):
        """默认标量 = 词条总数（"有效词条最多"就是按这个排序）。"""
        self.assertEqual(relic.state_scalar((1, 0, 2, 0, 3)), 6.0)

    def test_best_of_n_is_a_distribution(self):
        """N 件最好的分数分布：概率和为 1，且 N=1 时就是单件分布。"""
        states = relic.piece_states("atk_pct")
        single = relic.best_of_n(states, 1)
        for value, prob in single.items():
            self.assertAlmostEqual(prob, sum(
                p for vector, p in states.items() if relic.state_scalar(vector) == value))
        for n in (2, 3, 10, 50):
            dist = relic.best_of_n(states, n)
            self.assertAlmostEqual(sum(dist.values()), 1.0, places=9, msg=n)

    def test_best_of_n_matches_brute_force_for_two(self):
        """N=2 时用暴力枚举对拍：两件的分数取 max。"""
        states = relic.piece_states("atk_pct")
        base = relic.best_of_n(states, 1)

        brute: dict = {}
        for a, pa in base.items():
            for b, pb in base.items():
                key = max(a, b)
                brute[key] = brute.get(key, 0.0) + pa * pb
        got = relic.best_of_n(states, 2)
        for value in set(brute) | set(got):
            self.assertAlmostEqual(got.get(value, 0.0), brute.get(value, 0.0), places=12,
                                   msg=value)

    def test_more_pieces_never_hurt(self):
        """胚子越多，期望最好分数单调不减（随机占优）。"""
        states = relic.piece_states("atk_pct")
        values = [relic.expected_scalar(relic.best_of_n(states, n))
                  for n in (1, 2, 3, 5, 10, 20, 50)]
        for before, after in zip(values, values[1:]):
            self.assertLessEqual(before, after + 1e-12)

    def test_higher_q4_improves_the_best_of_n(self):
        """4 词条起手概率更高（BOSS 34% vs 副本 20%）→ 期望更好。"""
        domain = relic.best_of_n(relic.piece_states("atk_pct", q4=0.20), 10)
        boss = relic.best_of_n(relic.piece_states("atk_pct", q4=0.34), 10)
        self.assertGreater(relic.expected_scalar(boss), relic.expected_scalar(domain))


class TestBestOfNStates(unittest.TestCase):
    """口径 B：向量状态的 P_N[v]（"最好那个恰好等于这个状态"）。

    与 TestSinglePieceModel 的区别：那边压成标量分数（"恰好 N 点"），
    这边保留向量（"恰好 3 暴击 / 2 攻击%"），靠全序键把并列打破。
    """

    def test_is_a_distribution_and_n1_is_identity(self):
        states = relic.piece_states("atk_pct")
        self.assertEqual(relic.best_of_n_states(states, 1), states)
        for n in (2, 3, 10, 50):
            dist = relic.best_of_n_states(states, n)
            self.assertEqual(set(dist), set(states))      # 状态集不变，只是概率重分配
            self.assertAlmostEqual(sum(dist.values()), 1.0, places=9, msg=n)

    def test_projects_onto_the_scalar_formula(self):
        """按默认键的第一分量（词条总数）投影 → 必须与 best_of_n 完全一致。"""
        states = relic.piece_states("crit_dmg")
        for n in (1, 2, 5, 20):
            projected: dict = {}
            for vector, prob in relic.best_of_n_states(states, n).items():
                key = relic.state_scalar(vector)
                projected[key] = projected.get(key, 0.0) + prob
            scalar = relic.best_of_n(states, n)
            for key in set(projected) | set(scalar):
                self.assertAlmostEqual(projected.get(key, 0.0), scalar.get(key, 0.0),
                                       places=12, msg=(n, key))

    def test_matches_brute_force_for_two(self):
        """N=2 暴力枚举所有有序对，取键最大的那个向量。"""
        states = relic.piece_states("atk_pct")
        items = list(states.items())

        brute: dict = {}
        for va, pa in items:
            for vb, pb in items:
                best = va if relic.total_state_key(va) >= relic.total_state_key(vb) else vb
                brute[best] = brute.get(best, 0.0) + pa * pb
        got = relic.best_of_n_states(states, 2)
        for vector in set(brute) | set(got):
            self.assertAlmostEqual(got.get(vector, 0.0), brute.get(vector, 0.0),
                                   places=12, msg=vector)

    def test_custom_key_behaves_like_damage(self):
        """自定义全序键（模拟"真实伤害 + 向量打破并列"）也要与暴力枚举一致。"""
        # 假的"伤害"：双爆权重高、防御无用 —— 只为验证 key 通道，不是真实公式
        weights = (2.0, 1.0, 0.0, 0.0, 0.0)

        def key(vector):
            return (sum(w * c for w, c in zip(weights, vector)), tuple(vector))

        states = relic.piece_states("atk_pct")
        items = list(states.items())
        brute: dict = {}
        for va, pa in items:
            for vb, pb in items:
                best = va if key(va) >= key(vb) else vb
                brute[best] = brute.get(best, 0.0) + pa * pb
        got = relic.best_of_n_states(states, 2, key=key)
        for vector in set(brute) | set(got):
            self.assertAlmostEqual(got.get(vector, 0.0), brute.get(vector, 0.0),
                                   places=12, msg=vector)

    def test_more_pieces_never_hurt_under_any_key(self):
        def key(vector):
            return (vector[1] * 2.0 + vector[0], tuple(vector))   # 偏爱小攻击 + 攻击%

        states = relic.piece_states("atk_pct")
        values = [sum(key(v)[0] * p
                      for v, p in relic.best_of_n_states(states, n, key=key).items())
                  for n in (1, 2, 3, 5, 10, 20)]
        for before, after in zip(values, values[1:]):
            self.assertLessEqual(before, after + 1e-12)

    def test_duplicate_keys_are_rejected(self):
        """两个不同状态同键 → "恰好等于 v" 无定义，必须报错而不是静默合并。"""
        states = relic.piece_states("atk_pct")
        with self.assertRaises(ValueError):
            relic.best_of_n_states(states, 2, key=lambda vector: relic.state_scalar(vector))

    def test_rejects_non_positive_n(self):
        states = relic.piece_states("atk_pct")
        for n in (0, -1):
            with self.assertRaises(ValueError):
                relic.best_of_n_states(states, n)


class TestFilteredModel(unittest.TestCase):
    """带筛选的刷取模型：有效词条集合 + 初始胚子接受条件。

    口径（用户确认）：
    * 4 起手在 **+0** 判定（4 条都能看到）；
    * 3 起手在 **+4** 判定（补出第 4 条之后）；
    * 未通过的胚子**直接丢弃**，不投强化、不产出；
    * 预算只算树脂（垃圾胚子充当强化材料）。
    """

    EFF3 = ("crit_rate", "crit_dmg", "atk_flat")

    def test_start_line_sets_is_a_distribution(self):
        sets = relic.start_line_sets("atk_pct")
        self.assertAlmostEqual(sum(sets.values()), 1.0, places=12)
        for (lines, kind), prob in sets.items():
            self.assertEqual(len(lines), 4)          # 判定时刻一律 4 条
            self.assertIn(kind, ("four", "three"))
            self.assertGreaterEqual(prob, 0.0)

    def test_three_start_set_distribution_matches_explicit_enumeration(self):
        """3 起手 = 先抽 3 条再补 1 条；用有序枚举独立验证（不是直接抽 4 条）。"""
        pool = relic.substat_pool("atk_pct")
        total = float(sum(pool.values()))
        keys = tuple(pool)

        four: dict = {}
        for a in keys:
            for b in keys:
                if b == a:
                    continue
                for c in keys:
                    if c in (a, b):
                        continue
                    p = (pool[a] / total) * (pool[b] / (total - pool[a])) \
                        * (pool[c] / (total - pool[a] - pool[b]))
                    rest = total - pool[a] - pool[b] - pool[c]
                    for d in keys:
                        if d in (a, b, c):
                            continue
                        q = frozenset((a, b, c, d))
                        four[q] = four.get(q, 0.0) + p * pool[d] / rest

        got: dict = {}
        for (lines, kind), prob in relic.start_line_sets("atk_pct", q4=0.0).items():
            if kind == "three":
                got[lines] = got.get(lines, 0.0) + prob
        self.assertEqual(set(got), set(four))
        for lines in four:
            self.assertAlmostEqual(got[lines], four[lines], places=14, msg=sorted(lines))

    def test_four_and_three_starts_share_the_same_set_distribution(self):
        """恒等式：先抽 3 条再补 1 条 == 直接顺序抽 4 条（第 4 次抽样同一件事）。

        所以两种起手**判定时刻的集合分布相同**，差别只在后续强化次数（9 点 vs 8 点）。
        这里守住这条恒等式，防止有人"优化"成错误的近似。
        """
        four = relic.start_line_sets("atk_pct", q4=1.0)
        three = relic.start_line_sets("atk_pct", q4=0.0)
        four_sets = {lines: prob for (lines, kind), prob in four.items() if kind == "four"}
        three_sets = {lines: prob for (lines, kind), prob in three.items() if kind == "three"}
        self.assertEqual(set(four_sets), set(three_sets))
        for lines, prob in four_sets.items():
            self.assertAlmostEqual(prob, three_sets[lines], places=14, msg=sorted(lines))

    def test_pass_probability_is_monotone_in_k(self):
        rates = [relic.pass_probability("atk_pct", self.EFF3, k) for k in range(0, 5)]
        self.assertAlmostEqual(rates[0], 1.0, places=12)      # 要求 0 个必然通过
        for before, after in zip(rates, rates[1:]):
            self.assertGreaterEqual(before, after)
        self.assertGreater(rates[1], rates[2])

    def test_pass_probability_k4_means_all_four_effective(self):
        eff = tuple(relic.POOL_KEYS)
        self.assertAlmostEqual(relic.pass_probability("atk_pct", eff, 4), 1.0, places=12)
        # 只允许 3 个有效词条 → 永远凑不满 4 个
        self.assertEqual(relic.pass_probability("atk_pct", eff[:3], 4), 0.0)

    def test_effective_set_sizes_one_to_five(self):
        """有效词条数量 1~5 都要支持（辅助可能只有 1 个）。"""
        main = "dmg_pyro"                     # 元素伤害主词条：不在副词条池里，池是满的 10 项
        for size in (1, 2, 3, 4, 5):
            eff = tuple(relic.POOL_KEYS[:size])
            k = min(2, size)
            rate = relic.pass_probability(main, eff, k)
            self.assertGreater(rate, 0.0, msg=size)
            self.assertLessEqual(rate, 1.0, msg=size)
            states = relic.filtered_piece_states(main, eff, k)
            self.assertAlmostEqual(sum(states.values()), 1.0, places=12, msg=size)

    def test_filtered_states_are_conditional_and_agree_with_accept_condition(self):
        states = relic.filtered_piece_states("atk_pct", self.EFF3, 2)
        self.assertAlmostEqual(sum(states.values()), 1.0, places=12)
        for vector in states:
            # 只有有效词条进状态，所以非零分量数 = 这条件的有效词条条数
            self.assertGreaterEqual(sum(1 for count in vector if count), 2)
            self.assertLessEqual(sum(vector), 9)

    def test_no_filter_equals_plain_piece_states(self):
        """条件放宽到"至少 1 个有效"且有效集合覆盖全池时，必须等于不筛选的分布。"""
        eff = tuple(relic.POOL_KEYS)
        filtered = relic.filtered_piece_states("atk_pct", eff, 1, tracked=eff)
        plain = relic.piece_states("atk_pct", tracked=eff)
        self.assertEqual(set(filtered), set(plain))
        for vector in plain:
            self.assertAlmostEqual(filtered[vector], plain[vector], places=14, msg=vector)

    def test_pass_rate_mixes_start_types(self):
        """q4 越大（4 起手越多），通过率随 4 起手/3 起手的差异单调变化。"""
        eff = self.EFF3
        domain = relic.pass_probability("atk_pct", eff, 2, q4=0.20)
        boss = relic.pass_probability("atk_pct", eff, 2, q4=0.34)
        four_only = relic.pass_probability("atk_pct", eff, 2, q4=1.0)
        three_only = relic.pass_probability("atk_pct", eff, 2, q4=0.0)
        self.assertAlmostEqual(domain, 0.2 * four_only + 0.8 * three_only, places=12)
        self.assertAlmostEqual(boss, 0.34 * four_only + 0.66 * three_only, places=12)

    def test_resin_per_accepted_is_base_over_pass_rate(self):
        base = relic.resin_cost("sands", "atk_pct")
        rate = relic.pass_probability("atk_pct", self.EFF3, 2)
        self.assertAlmostEqual(
            relic.resin_per_accepted("sands", "atk_pct", self.EFF3, 2),
            base / rate, places=9)
        # 无条件（全池、k=1）时必须等于不筛选的树脂
        eff = tuple(relic.POOL_KEYS)
        self.assertAlmostEqual(relic.resin_per_accepted("sands", "atk_pct", eff, 1),
                               base, places=9)
        # 不可能达成的条件 → inf
        self.assertEqual(relic.resin_per_accepted("sands", "atk_pct", eff[:3], 4),
                         float("inf"))

    def test_summary_reports_pass_rate_and_expected_rolls(self):
        summary = relic.filtered_summary("atk_pct", self.EFF3, 2)
        self.assertAlmostEqual(summary["pass_rate"],
                               relic.pass_probability("atk_pct", self.EFF3, 2), places=12)
        rolls = summary["expected_rolls"]
        self.assertEqual(set(rolls), set(self.EFF3))
        self.assertGreaterEqual(rolls["atk_flat"], 0.0)

    def test_rejects_bad_effective_sets(self):
        for bad in ([], ("not_a_stat",), "crit_rate"):
            with self.assertRaises(ValueError):
                relic.check_effective(bad)
        with self.assertRaises(ValueError):
            relic.pass_probability("atk_pct", self.EFF3, -1)
        with self.assertRaises(ValueError):
            relic.filtered_piece_states("atk_pct", self.EFF3, 4)


class TestDamageFn(unittest.TestCase):
    """伤害函数抽象层：9 个属性 → 期望伤害（解释层实现）。"""

    def make(self):
        """一个最小工程：角色面板 → 基础值 → 暴击区 → ★结果。"""
        from genshin_dmg.graph import Graph, GraphNode

        g = Graph()
        g.add(GraphNode("r1", "role", fields={
            "role_name": "测试",
            "panel": ("atk = 1000\natk_pct = 0\natk_flat = 0\n"
                      "crit_rate = 50\ncrit_dmg = 100"),
        }))
        g.add(GraphNode("n1", "base", fields={
            "stat_base": "atk*(1+atk_pct/100)+atk_flat", "multiplier": "200"}))
        g.add(GraphNode("n2", "crit", fields={
            "crit_rate": "crit_rate", "crit_damage": "crit_dmg"}))
        g.add(GraphNode("n3", "result"))
        for nid in ("n1", "n2", "n3"):
            g.nodes[nid].role = "测试"
        g.connect("n1", "n2")
        g.connect("n2", "n3")
        return g

    def test_stats_order_is_the_nine_substats(self):
        self.assertEqual(relic.STATS_ORDER, (
            "atk_pct", "atk_flat", "hp_pct", "hp_flat", "def_pct",
            "def_flat", "em", "crit_rate", "crit_dmg"))
        self.assertEqual(len(relic.STATS_ORDER), 9)

    def test_baseline_matches_plain_evaluation(self):
        """全 0 注入时，伤害函数 = 不做任何注入的工程求值。"""
        g = self.make()
        fn = relic_adapter.damage_fn_from_project(g, "测试")
        base = fn.calc([0] * 9)
        self.assertAlmostEqual(base, 3000.0, places=6)   # 1000×200%×(1+0.5×1.0)

    def test_injects_attack_percent(self):
        """攻击% 注入后基础值变大，伤害必须变高。"""
        fn = relic_adapter.damage_fn_from_project(self.make(), "测试")
        base = fn.calc([0] * 9)
        got = fn.calc([50, 0, 0, 0, 0, 0, 0, 0, 0])      # atk_pct = 50
        self.assertAlmostEqual(got, base * 1.5, places=6)

    def test_injects_flat_attack_and_crit_damage(self):
        fn = relic_adapter.damage_fn_from_project(self.make(), "测试")
        base = fn.calc([0] * 9)
        self.assertAlmostEqual(fn.calc([0, 311, 0, 0, 0, 0, 0, 0, 0]),
                               base * (1000 + 311) / 1000, places=6)
        # 暴伤 +100 → 期望倍率从 1.5 变成 2.0
        self.assertAlmostEqual(fn.calc([0] * 8 + [100]), base * 2.0 / 1.5, places=6)

    def test_injection_counts_as_own(self):
        """圣遗物属性算"自身"（own::），不是别人给的拐（in::）。"""
        g = self.make()
        fn = relic_adapter.damage_fn_from_project(g, "测试")
        fn.calc([50, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertAlmostEqual(g.variables["测试__own__atk_pct"], 50.0, places=9)
        self.assertAlmostEqual(g.variables.get("测试__in__atk_pct", 0.0), 0.0, places=9)

    def test_batch_equals_single_calls(self):
        fn = relic_adapter.damage_fn_from_project(self.make(), "测试")
        rows = [[0] * 9, [50] + [0] * 8, [0, 311] + [0] * 7, [0] * 8 + [50]]
        flat = [value for row in rows for value in row]
        got = fn.calc_batch(flat)
        want = [fn.calc(row) for row in rows]
        self.assertEqual(len(got), len(want))
        for got_value, want_value in zip(got, want):
            self.assertAlmostEqual(got_value, want_value, places=9)

    def test_rejects_bad_input(self):
        fn = relic_adapter.damage_fn_from_project(self.make(), "测试")
        with self.assertRaises(ValueError):
            fn.calc([0] * 8)                      # 少一个
        with self.assertRaises(ValueError):
            fn.calc([0] * 10)                     # 多一个
        with self.assertRaises(ValueError):
            fn.calc([float("nan")] + [0] * 8)
        with self.assertRaises(ValueError):
            fn.calc_batch([0] * 10)               # 不是 9 的倍数

    def test_unknown_role(self):
        with self.assertRaises(ValueError):
            relic_adapter.damage_fn_from_project(self.make(), "不存在的角色")


if __name__ == "__main__":                                  # pragma: no cover
    unittest.main()

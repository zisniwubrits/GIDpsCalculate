# -*- coding: utf-8 -*-
"""圣遗物「刷取换算层」的测试：树脂 → 件数 / 主词条成本 / 副词条期望。

这一层是纯算术，不涉及伤害链，所以断言的都是可以直接手算的数值。
"""

import math
import unittest

from genshin_dmg import nodes, relic


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
        rows = {row[0]: float(row[3]) for row in nodes.RELIC_ROWS}
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
        """目标套槽：20 / (1.065 × 0.5 × p)。"""
        cost = relic.resin_cost(relic.SLOT_SANDS, "atk_pct")
        p = relic.MAIN_STAT_PROB[relic.SLOT_SANDS]["atk_pct"]
        self.assertAlmostEqual(cost, 20 / (1.065 * 0.5 * p), places=6)
        # 用户表里的例子：沙·攻击% ≈ 141 树脂
        self.assertAlmostEqual(cost, 140.9, places=1)

    def test_cost_for_off_piece_slot(self):
        """散件槽不限套装：20 / (1.065 × p)，正好是目标套槽的一半。"""
        target = relic.resin_cost(relic.SLOT_SANDS, "atk_pct")
        off = relic.resin_cost(relic.SLOT_SANDS, "atk_pct", off_piece=True)
        self.assertAlmostEqual(off, target / 2, places=6)
        # 沙·攻击% 的散件槽 ≈ 70.4 树脂（比目标套槽的 140.9 便宜一半）
        self.assertAlmostEqual(off, 20 / (1.065 * 0.2666), places=6)

    def test_cost_of_rare_elemental_cup(self):
        """元素伤害杯每类只有 5% → 明显更贵。"""
        cost = relic.resin_cost(relic.SLOT_GOBLET, "dmg_pyro")
        self.assertAlmostEqual(cost, 20 / (1.065 * 0.5 * 0.05), places=6)
        self.assertAlmostEqual(cost, 751.2, places=1)
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
        self.assertEqual(relic.feasible_combos(300), [])          # 最低成本 ≈ 484
        every = relic.feasible_combos(100000)
        self.assertEqual(len(every), len(relic.main_combos()) * len(relic.SLOTS))
        for item in every:
            self.assertIn(item["offPiece"], relic.SLOTS)
            self.assertLessEqual(item["cost"], 100000)

    def test_feasible_combos_sorted_and_within_budget(self):
        """返回结果按成本从低到高、都不超预算。"""
        got = relic.feasible_combos(1500)
        self.assertTrue(got)
        costs = [item["cost"] for item in got]
        self.assertEqual(costs, sorted(costs))
        self.assertLessEqual(max(costs), 1500)
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


if __name__ == "__main__":                                  # pragma: no cover
    unittest.main()

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

    def test_expected_rolls_are_linear_and_sum_to_points(self):
        """期望词条数合计 = 每件点数；某属性 = 点数 × 权重 / 池权重。"""
        rolls = relic.expected_substat_rolls("atk_pct")     # 池 9 项（去掉攻击%）
        self.assertAlmostEqual(sum(rolls.values()), 8.2, places=6)
        total_weight = 1000.0
        self.assertAlmostEqual(rolls["crit_rate"], 8.2 * 75 / total_weight, places=9)
        self.assertAlmostEqual(rolls["em"], 8.2 * 100 / total_weight, places=9)
        # 攻击% 被主词条占掉，不在副词条里
        self.assertNotIn("atk_pct", rolls)

    def test_expected_values(self):
        """期望数值 = 期望词条数 × 平均词条值。"""
        values = relic.expected_substats("atk_pct")
        rolls = relic.expected_substat_rolls("atk_pct")
        self.assertAlmostEqual(
            values["crit_dmg"], rolls["crit_dmg"] * relic.SUBSTAT_AVG["crit_dmg"], places=9)
        # 沙·攻击% 下，暴击率的期望数值约 2.03%
        self.assertAlmostEqual(values["crit_rate"], 0.615 * 3.305, places=6)

    def test_four_sub_rate_changes_expectation(self):
        """初始 4 词条概率越高，词条期望越多（副本 20% / BOSS 34%）。"""
        domain = relic.expected_substats("atk_pct", q4=0.20)
        boss = relic.expected_substats("atk_pct", q4=0.34)
        self.assertGreater(boss["crit_rate"], domain["crit_rate"])


if __name__ == "__main__":                                  # pragma: no cover
    unittest.main()

# -*- coding: utf-8 -*-
"""「函数表示」的测试：编译出的程序必须与解释层（GraphDamageFn）给出同样的伤害。"""

import unittest

from genshin_dmg.GIRelic import relic, relic_program as rp


def simple():
    """基础值 → 暴击区 → ★结果。"""
    from genshin_dmg.graph import Graph, GraphNode

    g = Graph()
    g.add(GraphNode("r1", "role", fields={"role_name": "T", "panel": (
        "atk = 1000\natk_pct = 0\natk_flat = 0\ncrit_rate = 50\ncrit_dmg = 100")}))
    g.add(GraphNode("n1", "base", fields={
        "stat_base": "atk*(1+atk_pct/100)+atk_flat", "multiplier": "200"}))
    g.add(GraphNode("n2", "crit", fields={"crit_rate": "crit_rate", "crit_damage": "crit_dmg"}))
    g.add(GraphNode("n3", "result"))
    for nid in ("n1", "n2", "n3"):
        g.nodes[nid].role = "T"
    g.connect("n1", "n2")
    g.connect("n2", "n3")
    return g


def full():
    """基础值 → 增伤 → 抗性 → 防御 → 暴击 → ★结果。"""
    from genshin_dmg.graph import Graph, GraphNode

    g = Graph()
    g.add(GraphNode("r1", "role", fields={"role_name": "T", "panel": (
        "atk = 1200\natk_pct = 0\natk_flat = 0\ncrit_rate = 60\ncrit_dmg = 120\n"
        "dmg = 46.6\nres_shred = 20\ndef_shred = 0\nignore_def = 0")}))
    g.add(GraphNode("n1", "base", fields={
        "stat_base": "atk*(1+atk_pct/100)+atk_flat", "multiplier": "150"}))
    g.add(GraphNode("n2", "dmg", fields={"dmg_net": "dmg"}))
    g.add(GraphNode("n3", "res", fields={"resistance": "10 - res_shred"}))
    g.add(GraphNode("n4", "def", fields={
        "char_level": "90", "enemy_level": "90",
        "def_reduction": "def_shred", "ignore_def": "ignore_def"}))
    g.add(GraphNode("n5", "crit", fields={"crit_rate": "crit_rate", "crit_damage": "crit_dmg"}))
    g.add(GraphNode("n6", "result"))
    for i in range(1, 7):
        g.nodes["n%d" % i].role = "T"
    for a, b in (("n1", "n2"), ("n2", "n3"), ("n3", "n4"), ("n4", "n5"), ("n5", "n6")):
        g.connect(a, b)
    return g


class TestProgram(unittest.TestCase):
    def test_compiles_core_chain(self):
        prog = rp.compile_project(simple(), "T")
        self.assertEqual([s["op"] for s in prog["stages"]], ["base", "crit", "result"])
        self.assertEqual(prog["stats_order"], list(relic.STATS_ORDER))

    def test_matches_interpreter_simple(self):
        g = simple()
        prog = rp.compile_project(g, "T")
        fn = relic.GraphDamageFn(g, "T")
        for stats in ([0] * 9, [50] + [0] * 8, [0, 311] + [0] * 7, [0] * 8 + [100]):
            self.assertAlmostEqual(rp.run_expected(prog, stats), fn.calc(stats), places=9)

    def test_matches_interpreter_full_chain(self):
        g = full()
        prog = rp.compile_project(g, "T")
        fn = relic.GraphDamageFn(g, "T")
        for stats in ([0] * 9, [30, 200] + [0] * 7, [0] * 7 + [20, 40], [80, 50, 0, 0, 0, 0, 300, 0, 0]):
            self.assertAlmostEqual(rp.run_expected(prog, stats), fn.calc(stats), places=9)

    def test_run_returns_branches(self):
        prog = rp.compile_project(simple(), "T")
        got = rp.run(prog, [0] * 9)
        self.assertAlmostEqual(got["noncrit"], 2000.0, places=9)
        self.assertAlmostEqual(got["crit"], 4000.0, places=9)
        self.assertAlmostEqual(got["expected"], 3000.0, places=9)

    def test_crit_rate_is_clamped(self):
        """暴击率超过 100% 时封顶（与工程链一致）。"""
        prog = rp.compile_project(simple(), "T")
        got = rp.run(prog, [0] * 7 + [150, 100])
        self.assertAlmostEqual(got["expected"], got["crit"], places=9)

    def test_not_compilable_for_foreign_card(self):
        """链上出现不支持的卡片 → NotCompilable（调用方回退解释层）。"""
        g = simple()
        from genshin_dmg.graph import GraphNode

        g.add(GraphNode("n9", "vartable", fields={}))
        g.nodes["n9"].role = "T"
        g.connect("n9", "n3")            # 结果卡的上游换成变量表卡
        with self.assertRaises(rp.NotCompilable):
            rp.compile_project(g, "T")

    def test_not_compilable_for_unknown_name(self):
        g = simple()
        g.nodes["n1"].fields["stat_base"] = "不存在的名字 * 2"
        with self.assertRaises(rp.NotCompilable):
            rp.compile_project(g, "T")

    def test_empty_or_invalid_stats(self):
        prog = rp.compile_project(simple(), "T")
        with self.assertRaises(ValueError):
            rp.run(prog, [0] * 8)


def with_add():
    """两条基础值链 → 「加法合并」→ 暴击区 → ★结果。"""
    from genshin_dmg.graph import Graph, GraphNode

    g = Graph()
    g.add(GraphNode("r1", "role", fields={"role_name": "T", "panel": (
        "atk = 1000\natk_pct = 0\natk_flat = 0\ncrit_rate = 50\ncrit_dmg = 100")}))
    g.add(GraphNode("b1", "base", fields={
        "stat_base": "atk*(1+atk_pct/100)+atk_flat", "multiplier": "100"}))
    g.add(GraphNode("b2", "base", fields={"stat_base": "atk", "multiplier": "50"}))
    g.add(GraphNode("ad", "add"))
    g.add(GraphNode("cr", "crit", fields={"crit_rate": "crit_rate", "crit_damage": "crit_dmg"}))
    g.add(GraphNode("rs", "result"))
    for nid in ("b1", "b2", "ad", "cr", "rs"):
        g.nodes[nid].role = "T"
    g.connect("b1", "ad", 0)
    g.connect("b2", "ad", 1)
    g.connect("ad", "cr")
    g.connect("cr", "rs")
    return g


class TestAddMerge(unittest.TestCase):
    def test_multi_input_add_compiles_and_matches(self):
        """「加法合并」多输入：各分支分量相加，结果必须与工程一致。"""
        g = with_add()
        prog = rp.compile_project(g, "T")
        first = prog["stages"][0]
        self.assertEqual(first["op"], "add")
        self.assertEqual(len(first["branches"]), 2)

        fn = relic.GraphDamageFn(g, "T")
        for stats in ([0] * 9, [50] + [0] * 8, [0] * 8 + [100], [30, 200] + [0] * 7):
            self.assertAlmostEqual(rp.run_expected(prog, stats), fn.calc(stats), places=9)

    def test_add_without_inputs_is_not_compilable(self):
        g = with_add()
        # 直接清掉两条输入
        g.links = [l for l in g.links if l.dst != "ad"]
        with self.assertRaises(rp.NotCompilable):
            rp.compile_project(g, "T")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

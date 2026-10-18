# -*- coding: utf-8 -*-
"""「域对照表」：行域 × 列域 的期望伤害矩阵。

口径（用户确认）：每行 = 一个只含单域、且域内有 ★结果 的文件；
每列 = 一个单域文件（拐力来源）；左上角再选一个固定拐力域，对所有组合都加一次。
单元格 = 行角色在「该列 out:: + 固定 out::」作用下的期望伤害。
"""

import json
import tempfile
import unittest
from pathlib import Path

from genshin_dmg import matrix
from genshin_dmg.graph import Graph, GraphNode, Link


class TestMatrix(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def make(self, name, role, panel, *, result=True, extra_nodes=0):
        """造一个"角色 + 基础值 + ★结果"的工程文件（行域）。"""
        g = Graph()
        g.add(GraphNode("r1", "role", fields={"role_name": role, "panel": panel}))
        g.add(GraphNode("b1", "base", fields={
            "stat_base": "atk", "stat_big": "atk_pct", "stat_flat": "0",
            "multiplier": "100"}, role=role))
        if result:
            g.add(GraphNode("res", "result", fields={}, inputs=1, role=role))
            g.links.append(Link("b1", "res", 0))
        for i in range(extra_nodes):                     # 造"多域文件"用
            g.add(GraphNode("r%d" % (i + 2), "role", fields={"role_name": "别的%d" % i}))
        path = self.dir / name
        path.write_text(json.dumps(g.to_dict(), ensure_ascii=False), encoding="utf-8")
        return path

    def buff(self, name, role, panel):
        return self.make(name, role, panel, result=False)

    def test_two_rows_two_cols_with_fixed_buff(self):
        row_a = self.make("行A.json", "甲", "atk = 1000 + in::atk\natk_pct = in::atk_pct")
        row_b = self.make("行B.json", "乙", "atk = 2000 + in::atk\natk_pct = in::atk_pct")
        col1 = self.buff("列1.json", "拐1", "out::atk_pct = 100")
        col2 = self.buff("列2.json", "拐2", "out::atk_pct = 200")
        fixed = self.buff("固定.json", "固", "out::atk = 500")

        table = matrix.build(
            "%s\n%s" % (row_a, row_b),
            "%s\n%s" % (col1, col2),
            str(fixed),
            str(self.dir),
        )
        self.assertEqual(table[0], ["固定.固", "列1.拐1", "列2.拐2"])
        self.assertEqual(table[1][0], "行A.甲")
        # (1000 + 500) × (1 + 100%) / (1 + 200%)
        self.assertEqual(table[1][1:], ["3000.00", "4500.00"])
        # (2000 + 500) × (1 + 100%) / (1 + 200%)
        self.assertEqual(table[2][1:], ["5000.00", "7500.00"])

    def test_no_fixed_buff(self):
        row = self.make("行.json", "甲", "atk = 1000 + in::atk\natk_pct = in::atk_pct")
        col = self.buff("列.json", "拐", "out::atk_pct = 50")
        table = matrix.build(str(row), str(col), "", str(self.dir))
        self.assertEqual(table[0][0], "行 \\ 列")          # 没选固定拐力时的角标
        self.assertEqual(table[1][1], "1500.00")          # 1000 × 1.5

    def test_row_without_result_is_dash(self):
        row = self.make("无结果.json", "甲", "atk = 1000", result=False)
        col = self.buff("列.json", "拐", "out::atk_pct = 50")
        table = matrix.build(str(row), str(col), "", str(self.dir))
        self.assertEqual(table[1], ["无结果.甲", "—"])

    def test_multi_domain_file_needs_explicit_domain(self):
        """文件里有多个域时，必须写 `文件::域`；不写就补不出来（给短横）。"""
        row = self.make("多域.json", "甲", "atk = 1000", extra_nodes=1)
        table = matrix.build(str(row), "", "", str(self.dir))
        # 没写域名又有多域 → 行标签只给文件名（没有列可选）
        self.assertEqual(table[1][0], "多域")
        # 明确写了域名就能算
        table2 = matrix.build("%s::甲" % row, "", "", str(self.dir))
        self.assertEqual(table2[1][0], "多域.甲")

    def test_missing_file_is_dash(self):
        table = matrix.build(str(self.dir / "没有.json"), "", "", str(self.dir))
        self.assertEqual(table[0], ["行 \\ 列"])
        self.assertTrue(table[1][0].endswith("没有"))       # 行标签仍给出文件名

    def test_multiple_fixed_buffs_are_summed(self):
        """固定拐力可以多选：多个来源的 out:: 同名相加，角标把名字列出来。"""
        row = self.make("行.json", "甲", "atk = 1000 + in::atk\natk_pct = in::atk_pct")
        col = self.buff("列.json", "拐", "out::atk_pct = 50")
        f1 = self.buff("砂糖.json", "砂", "out::atk = 200")
        f2 = self.buff("瓦.json", "瓦", "out::atk = 300")
        table = matrix.build(str(row), str(col), "%s\n%s" % (f1, f2), str(self.dir))
        self.assertEqual(table[0][0], "砂糖.砂 + 瓦.瓦")
        # (1000 + 200 + 300) × 1.5
        self.assertEqual(table[1][1], "2250.00")

    def test_fixed_label_is_plain_when_nothing_picked(self):
        row = self.make("行.json", "甲", "atk = 1000")
        self.assertEqual(matrix.build(str(row), "", "", str(self.dir))[0][0], "行 \\ 列")

    def test_arrow_from_other_domain_counts_as_fixed_buff(self):
        """指向对照表左上角的箭头（角色 / 外部域）也当固定拐力，可多来源相加。"""
        row = self.make("行.json", "甲", "atk = 1000 + in::atk\natk_pct = in::atk_pct")
        col = self.buff("列.json", "拐", "out::atk_pct = 50")
        f1 = self.buff("砂糖.json", "砂", "out::atk = 200")

        # 在「本工程」里搭：角色卡 + 对照表卡，箭头从角色指到对照表
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "瓦", "panel": "out::atk = 300"}))
        g.add(GraphNode("m1", "matrix", fields={
            "row_files": str(row), "col_files": str(col), "fixed_file": str(f1),
            "run_id": "t1"}))
        g.links.append(Link("ra", "m1", 0))
        out = g.evaluate()
        table = out["nodes"]["m1"]["rows"]
        # 1000 + 200（固定拐力那格） + 300（箭头） = 1500，再 ×1.5
        self.assertEqual(table[1][1], "2250.00")

    def test_arrow_from_external_domain(self):
        """外部域卡指进对照表也要算；外部域的 out:: 从被引用的文件里读。"""
        row = self.make("行.json", "甲", "atk = 1000 + in::atk")
        donor = self.buff("捐赠.json", "捐", "out::atk = 400")
        g = Graph()
        g.add(GraphNode("x1", "external", fields={"ext_sources": "%s::捐" % donor}))
        g.add(GraphNode("m1", "matrix", fields={
            "row_files": str(row), "col_files": "", "fixed_file": "", "run_id": "t1"}))
        g.links.append(Link("x1", "m1", 0))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["m1"]["rows"][1][0], "行.甲")

    def test_row_and_col_ports_only_affect_that_row_and_col(self):
        """行接入点只加那一行、列接入点只加那一列，与左上角的全局拐力相加。"""
        row1 = self.make("行1.json", "甲", "atk = 1000 + in::atk")
        row2 = self.make("行2.json", "乙", "atk = 1000 + in::atk")
        col1 = self.buff("列1.json", "拐1", "out::atk = 8")     # 列文件自己也声明了一份
        col2 = self.buff("列2.json", "拐2", "out::atk = 0")

        g = Graph()
        g.add(GraphNode("r_g", "role", fields={"role_name": "全", "panel": "out::atk = 1"}))
        g.add(GraphNode("r_r", "role", fields={"role_name": "行", "panel": "out::atk = 2"}))
        g.add(GraphNode("r_c", "role", fields={"role_name": "列", "panel": "out::atk = 4"}))
        g.add(GraphNode("m1", "matrix", fields={
            "row_files": "%s\n%s" % (row1, row2),
            "col_files": "%s\n%s" % (col1, col2),
            "fixed_file": "",
            "run_id": "t1",
        }))
        # 端口：0 = 全局；1 = 第 1 行；1000+1 = 第 2 列
        g.links.append(Link("r_g", "m1", 0))
        g.links.append(Link("r_r", "m1", 1))
        g.links.append(Link("r_c", "m1", 1001))
        table = g.evaluate()["nodes"]["m1"]["rows"]
        # 行1 列1：1000 + 1（全局）+ 2（行1）+ 8（列1 自己）= 1011
        self.assertEqual(table[1][1], "1011.00")
        # 行1 列2：1000 + 1 + 2 + 4（第 2 列的接入点）= 1007
        self.assertEqual(table[1][2], "1007.00")
        # 行2 列1：1000 + 1 + 8 = 1009（行2 没接拐力）
        self.assertEqual(table[2][1], "1009.00")
        # 行2 列2：1000 + 1 + 4 = 1005
        self.assertEqual(table[2][2], "1005.00")

    def test_multi_domain_file_uses_the_requested_domains_result(self):
        """一个文件里有多个域时，单元格要取**指定域**的那张 ★结果。

        用户报：`data/米c0::factor7` 算出来的数不对 —— 原来取的是 out["result"]
        （第一张连上的结果卡，往往属于另一个域）。
        """
        g = Graph()
        for role, atk in (("甲", 1000), ("乙", 3000)):
            g.add(GraphNode("r_%s" % role, "role", fields={"role_name": role, "panel": ""}))
            g.add(GraphNode("b_%s" % role, "base", fields={
                "stat_base": "atk", "stat_big": "atk_pct", "stat_flat": "0",
                "multiplier": "100"}, role=role))
            g.add(GraphNode("s_%s" % role, "result", fields={}, inputs=1, role=role))
            g.add(GraphNode("v_%s" % role, "var", fields={
                "defs": "atk = %d\natk_pct = in::atk_pct" % atk}, role=role))
        g.links.append(Link("b_甲", "s_甲", 0))
        g.links.append(Link("b_乙", "s_乙", 0))
        path = self.dir / "双域.json"
        path.write_text(json.dumps(g.to_dict(), ensure_ascii=False), encoding="utf-8")

        table = matrix.build("%s::甲\n%s::乙" % (path, path), "", "", str(self.dir))
        self.assertEqual(table[1][0], "双域.甲")
        self.assertEqual(table[2][0], "双域.乙")
        # 甲的自身 atk=1000 → 1000；乙的 3000（两者不能串）
        self.assertEqual(table[1][1:], [])            # 没有列：只有行标签
        self.assertEqual(matrix._expected(str(path), "甲", {}), 1000.0)
        self.assertEqual(matrix._expected(str(path), "乙", {}), 3000.0)
        # 拐力只作用到指定的那个域
        self.assertEqual(matrix._expected(str(path), "甲", {"atk_pct": 100}), 2000.0)
        self.assertEqual(matrix._expected(str(path), "乙", {"atk_pct": 100}), 6000.0)

    def test_ratio_table_uses_baseline_cell(self):
        """百分比基准：双击设定的那一格是 100%，其余按它算。"""
        values = [[None, 1000.0, 500.0], [None, 2000.0, 750.0]]
        ratios = matrix.ratio_table(values, "0,0")
        self.assertEqual(ratios[0], [100.0, 50.0])
        self.assertEqual(ratios[1], [200.0, 75.0])
        # 换基准：第 2 行、第 2 个数据列（列号从 0 数，不含表头）→ 750
        ratios2 = matrix.ratio_table(values, "1,1")
        self.assertAlmostEqual(ratios2[0][0], 1000 / 750 * 100)
        self.assertAlmostEqual(ratios2[0][1], 500 / 750 * 100)
        self.assertAlmostEqual(ratios2[1][0], 2000 / 750 * 100)
        self.assertAlmostEqual(ratios2[1][1], 100.0)
        # 没设基准 / 基准是 0 / 越界 → 不画百分比
        self.assertEqual(matrix.ratio_table(values, ""), [])
        self.assertEqual(matrix.ratio_table(values, "x"), [])
        self.assertEqual(matrix.ratio_table([[None, 0.0]], "0,0"), [])
        self.assertEqual(matrix.ratio_table(values, "5,5"), [])

    def test_manual_run_required_and_cached(self):
        """没点「计算」不算；同一个 run_id 只算一次（手动启动计算）。"""
        row = self.make("行.json", "甲", "atk = 1000")
        g = Graph()
        g.add(GraphNode("m1", "matrix", fields={
            "row_files": str(row), "col_files": "", "fixed_file": ""}))
        info = g.evaluate()["nodes"]["m1"]
        self.assertIsNone(info["rows"])
        self.assertIn("待计算", info["display"])

        # 点过「计算」：有表；同一个 run_id 再求值不会重算（缓存命中）
        calls = []
        original = matrix.build
        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)
        matrix.build = counting
        matrix.clear_cache()
        try:
            for _ in range(3):
                g2 = Graph()
                g2.add(GraphNode("m1", "matrix", fields={
                    "row_files": str(row), "col_files": "", "fixed_file": "",
                    "run_id": "run-1"}))
                info2 = g2.evaluate()["nodes"]["m1"]
                self.assertIsNotNone(info2["rows"])
        finally:
            matrix.build = original
        self.assertEqual(len(calls), 1)          # 三次求值只真正算了一次
        # 换一个 run_id → 重新算
        matrix.clear_cache()
        table, values = matrix.build_cached(str(row), "", "", "run-2", str(self.dir))
        self.assertIsNotNone(table)

    def test_parse_spec_reuses_external_syntax(self):
        self.assertEqual(matrix.parse_spec("a.json::dds\nb.json"), [
            ("a.json", "dds"), ("b.json", ""),
        ])

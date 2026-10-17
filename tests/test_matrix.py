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
            "row_files": str(row), "col_files": str(col), "fixed_file": str(f1)}))
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
            "row_files": str(row), "col_files": "", "fixed_file": ""}))
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

    def test_parse_spec_reuses_external_syntax(self):
        self.assertEqual(matrix.parse_spec("a.json::dds\nb.json"), [
            ("a.json", "dds"), ("b.json", ""),
        ])

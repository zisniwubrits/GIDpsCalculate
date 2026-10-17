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

    def test_parse_spec_reuses_external_syntax(self):
        self.assertEqual(matrix.parse_spec("a.json::dds\nb.json"), [
            ("a.json", "dds"), ("b.json", ""),
        ])

# -*- coding: utf-8 -*-
"""节点图（纯逻辑，无需图形环境）的行为测试。

覆盖：
  * 「★结果」卡片三元组变量（未暴击 / 暴击 / 期望）登记为全局变量；
  * 变量名非法（关键字 / 带空格 / 数字开头）时忽略；
  * 「变量」卡片可引用结果变量（如 秒伤 = 期望伤害/时间）；
  * 结果链没有暴击区时，结果卡片简洁显示单个数值；
  * 「变量表」卡片实时列出所有变量；
  * 工程 JSON 存档往返后变量仍可解析；
  * 算式字段、环路检测、未知类型兼容、多图互不污染。

运行：``python -m unittest test_graph -v``
"""

import unittest

from genshin_dmg import damage
from genshin_dmg import nodes as nd
from genshin_dmg.expr import eval_expr, fmt_num, parse_num, parse_pct, plain_num
from genshin_dmg.graph import Graph, GraphError, GraphNode


def build(with_crit=True, fields=None):
    """建一条 base(1000×200%=2000) [→ crit] → result 的链。"""
    g = Graph()
    g.add(GraphNode("n1", "base", fields=dict(
        {"stat_base": "1000", "multiplier": "200"}, **(fields or {}))))
    src = "n1"
    if with_crit:
        g.add(GraphNode("n2", "crit"))          # 默认 50% / 100%
        g.connect("n1", "n2")
        src = "n2"
    g.add(GraphNode("n3", "result"))
    g.connect(src, "n3")
    return g, "n3"


def variables_of(g):
    return {v["name"]: v["value"] for v in g.evaluate()["variables"]}


class TestExpr(unittest.TestCase):
    """输入解析与格式化（所有数值框共用）。"""

    def test_expression_and_variables(self):
        self.assertAlmostEqual(parse_num("70+30"), 100.0)
        self.assertAlmostEqual(parse_num("200*3"), 600.0)
        self.assertAlmostEqual(parse_pct("50"), 0.5)
        self.assertAlmostEqual(parse_num("攻击力*2", 0, {"攻击力": 1000}), 2000.0)
        self.assertAlmostEqual(parse_num("（80＋20）×2"), 200.0)     # 全角
        self.assertAlmostEqual(parse_num("1,000+1"), 1001.0)        # 千分位

    def test_invalid_returns_default(self):
        self.assertAlmostEqual(parse_num("", 7.0), 7.0)
        self.assertAlmostEqual(parse_num("1+", 7.0), 7.0)
        self.assertAlmostEqual(parse_num("未知变量", 7.0), 7.0)

    def test_no_eval_attribute_access(self):
        """安全求值：不允许属性访问 / 函数调用。"""
        for bad in ("__import__('os')", "1 .__class__", "(1).__class__"):
            with self.assertRaises(ValueError):
                eval_expr(bad)

    def test_fmt_never_scientific(self):
        for x in (0.0001, 1.5, 123.456, 12345.678, 1.2e8, 5e-7):
            text = fmt_num(x)
            self.assertNotIn("e", text.lower(), text)
        self.assertEqual(fmt_num(2000.0), "2000.00")
        self.assertEqual(fmt_num(12345.678), "12,345.7")
        self.assertEqual(plain_num(2000.0), "2000")
        self.assertEqual(plain_num(0.5), "0.5")


class TestResultVariables(unittest.TestCase):
    def setUp(self):
        self.g, self.result = build(with_crit=True)

    def _set_names(self, nc="", cr="", ex=""):
        node = self.g.nodes[self.result]
        node.fields["var_nc"], node.fields["var_cr"], node.fields["var_ex"] = nc, cr, ex

    def test_triple_registered_as_three_variables(self):
        self._set_names("未暴击伤害", "暴击伤害", "期望伤害")
        out = self.g.evaluate()

        env = {v["name"]: v["value"] for v in out["variables"]}
        self.assertAlmostEqual(env["未暴击伤害"], 2000.0)
        self.assertAlmostEqual(env["暴击伤害"], 4000.0)
        self.assertAlmostEqual(env["期望伤害"], 3000.0)
        self.assertTrue(out["ok"])
        self.assertAlmostEqual(out["result"]["values"]["expected"], 3000.0)

    def test_blank_name_defines_nothing(self):
        self._set_names(ex="期望伤害")
        self.assertEqual(sorted(variables_of(self.g)), ["期望伤害"])

    def test_invalid_names_ignored(self):
        self._set_names("for", "带 空格", "1abc")
        self.assertEqual(variables_of(self.g), {})

    def test_result_variable_usable_in_calc_and_var_card(self):
        self._set_names(ex="期望伤害")
        calc = GraphNode("c1", "calc", fields={"expr": "期望伤害/20*60"})
        var = GraphNode("v1", "var", fields={
            "defs": "时间 = 20\n秒伤 = 期望伤害/时间"})
        self.g.add(calc)
        self.g.add(var)
        out = self.g.evaluate()

        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 9000.0)
        self.assertAlmostEqual(variables_of(self.g)["秒伤"], 150.0)

    def test_var_card_cannot_override_result_variable(self):
        self._set_names(ex="伤害A")
        self.g.add(GraphNode("v1", "var", fields={
            "defs": "伤害A = 999\n总量 = 伤害A * 3"}))
        env = variables_of(self.g)

        self.assertAlmostEqual(env["伤害A"], 3000.0)
        self.assertAlmostEqual(env["总量"], 9000.0)

    def test_var_card_can_forward_reference_result_variable(self):
        """变量卡片里先定义的普通变量可以再被结果变量参与的式子引用。"""
        self._set_names(ex="期望伤害")
        self.g.add(GraphNode("v1", "var", fields={
            "defs": "时间 = 20\n秒伤 = 期望伤害/时间\n总伤 = 秒伤*60"}))
        env = variables_of(self.g)

        self.assertAlmostEqual(env["秒伤"], 150.0)
        self.assertAlmostEqual(env["总伤"], 9000.0)

    def test_result_card_has_no_visible_fields(self):
        self.assertEqual(nd.NODE_TYPES["result"]["fields"], [])
        for key in nd.RESULT_VAR_KEYS:
            self.assertIn(key, self.g.nodes[self.result].fields)

    def test_clear_result_vars(self):
        self._set_names("伤害A", "伤害B", "伤害C")
        self.assertTrue(variables_of(self.g))
        self._set_names()
        self.assertEqual(variables_of(self.g), {})

    def test_project_roundtrip_keeps_variables(self):
        self._set_names("未暴击伤害", "暴击伤害", "期望伤害")
        data = self.g.to_dict()
        back = Graph.from_dict(data)

        env = variables_of(back)
        self.assertAlmostEqual(env["未暴击伤害"], 2000.0)
        self.assertAlmostEqual(env["暴击伤害"], 4000.0)
        self.assertAlmostEqual(env["期望伤害"], 3000.0)

    def test_graphs_do_not_share_variables(self):
        """两张图各自求值，变量互不污染（contextvar 隔离）。"""
        self._set_names(ex="伤害A")
        other = Graph()
        other.add(GraphNode("x1", "var", fields={"defs": "伤害A = 1"}))
        other.evaluate()

        self.assertAlmostEqual(variables_of(self.g)["伤害A"], 3000.0)


class TestResultDisplay(unittest.TestCase):
    def test_no_crit_chain_shows_single_value(self):
        g, result = build(with_crit=False)
        text = g.evaluate()["nodes"][result]["display"]

        self.assertEqual(text, "结果 %s" % fmt_num(2000.0))
        self.assertNotIn("暴击", text)
        self.assertNotIn("期望", text)

    def test_crit_chain_shows_triple(self):
        g, result = build(with_crit=True)
        text = g.evaluate()["nodes"][result]["display"]

        self.assertIn("未暴击 %s" % fmt_num(2000.0), text)
        self.assertIn("暴击 %s" % fmt_num(4000.0), text)
        self.assertIn("期望 %s" % fmt_num(3000.0), text)

    def test_crit_card_with_no_effect_is_concise(self):
        g, result = build(with_crit=True)
        g.nodes["n2"].fields.update({"crit_rate": "0", "crit_damage": "0"})
        info = g.evaluate()["nodes"][result]

        self.assertEqual(info["display"], "结果 %s" % fmt_num(2000.0))
        self.assertFalse(info["isTriple"])

    def test_single_value_result_shows_bound_variable_name(self):
        g, result = build(with_crit=False)
        g.nodes[result].fields["var_ex"] = "总伤害"
        info = g.evaluate()["nodes"][result]

        self.assertEqual(info["display"],
                         "结果 %s ｜ 变量 总伤害" % fmt_num(2000.0))
        self.assertEqual(info["boundNames"], ["总伤害"])

    def test_single_value_result_lists_all_bound_names(self):
        g, result = build(with_crit=False)
        g.nodes[result].fields.update(
            {"var_nc": "未暴击伤害", "var_cr": "暴击伤害", "var_ex": "期望伤害"})
        info = g.evaluate()["nodes"][result]

        self.assertEqual(info["display"],
                         "结果 %s ｜ 变量 未暴击伤害 / 暴击伤害 / 期望伤害"
                         % fmt_num(2000.0))

    def test_triple_result_keeps_names_off_the_label(self):
        g, result = build(with_crit=True)
        g.nodes[result].fields["var_ex"] = "期望伤害"
        text = g.evaluate()["nodes"][result]["display"]

        self.assertNotIn("变量", text)
        self.assertIn("期望 %s" % fmt_num(3000.0), text)

    def test_warning_when_no_result_card(self):
        g = Graph()
        g.add(GraphNode("n1", "base", fields={"stat_base": "1000"}))
        out = g.evaluate()

        self.assertFalse(out["ok"])
        self.assertEqual(out["error"], "没有「结果」卡片")
        self.assertTrue(any("结果" in w for w in out["warnings"]))

    def test_warning_when_chain_has_no_crit(self):
        g, _ = build(with_crit=False)
        self.assertTrue(any("暴击区" in w for w in g.evaluate()["warnings"]))


class TestFactorDisplay(unittest.TestCase):
    def test_every_factor_uses_times_sign(self):
        """所有「本卡系数」的数字都带 × 号（如 暴击系数 ×2.630）。"""
        import re
        g = Graph()
        keys = [k for k, spec in nd.NODE_TYPES.items() if spec.get("factor")]
        self.assertGreaterEqual(len(keys), 10)
        for i, key in enumerate(keys):
            g.add(GraphNode("f%d" % i, key))
        out = g.evaluate()

        for i, key in enumerate(keys):
            text = out["nodes"]["f%d" % i]["factor"]
            self.assertTrue(text, "%s 没有系数文案" % key)
            for m in re.finditer(r"\d[\d.,]*", text):
                self.assertEqual(text[m.start() - 1] if m.start() else "", "×",
                                 "%s 的系数显示缺少 × 号：%s" % (key, text))

    def test_crit_factor_text(self):
        g = Graph()
        g.add(GraphNode("c1", "crit"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["factor"],
                         "暴击系数 ×2.000 ｜ 期望系数 ×1.500")

    def test_factor_matches_damage_module(self):
        """卡片系数与 damage.py 的纯函数结果一致（防止两处公式漂移）。"""
        g = Graph()
        g.add(GraphNode("d1", "def", fields={
            "char_level": "90", "enemy_level": "100", "def_reduction": "30"}))
        g.add(GraphNode("r1", "res", fields={"resistance": "-20"}))
        out = g.evaluate()

        self.assertIn(fmt_num(damage.defense_coefficient(
            90, 100, def_reduction=0.3, ignore_def=0.0)),
            out["nodes"]["d1"]["factor"])
        self.assertIn(fmt_num(damage.resistance_coefficient(-0.2)),
            out["nodes"]["r1"]["factor"])


class TestVarTable(unittest.TestCase):
    def test_empty_table_shows_placeholder(self):
        g = Graph()
        g.add(GraphNode("t1", "vartable"))
        self.assertEqual(g.evaluate()["nodes"]["t1"]["rows"], [["（暂无变量）", ""]])

    def test_table_lists_var_card_variables(self):
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "攻击力 = 1000\n倍率 = 200"}))
        g.add(GraphNode("t1", "vartable"))
        rows = g.evaluate()["nodes"]["t1"]["rows"]

        self.assertIn(["攻击力", "1000"], rows)
        self.assertIn(["倍率", "200"], rows)
        self.assertNotIn("（暂无变量）", [r[0] for r in rows])

    def test_table_tracks_result_variables(self):
        g, result = build(with_crit=True)
        g.add(GraphNode("t1", "vartable"))
        self.assertEqual(g.evaluate()["nodes"]["t1"]["rows"], [["（暂无变量）", ""]])

        g.nodes[result].fields["var_ex"] = "期望伤害"
        self.assertIn(["期望伤害", "3000"], g.evaluate()["nodes"]["t1"]["rows"])

    def test_isolated_cards_have_no_ports(self):
        for key in ("vartable", "const", "text", "calc", "var"):
            spec = nd.NODE_TYPES[key]
            self.assertEqual(spec["inputs"], 0, key)
            self.assertTrue(spec.get("isolated"), key)
        for key in ("vartable", "const", "text"):
            self.assertTrue(nd.NODE_TYPES[key].get("no_output"), key)

    def test_relic_table_exposed_to_frontend(self):
        tables = nd.schema()["tables"]
        self.assertEqual(tables["relic"]["header"], ["属性", "强化区间", "最高区间", "平均值"])
        self.assertEqual(tables["relic"]["rows"], [list(r) for r in nd.RELIC_ROWS])
        self.assertEqual(tables["vars"]["header"], ["变量", "值"])


class TestGraphStructure(unittest.TestCase):
    def test_cycle_detected(self):
        g = Graph()
        g.add(GraphNode("a", "dmg"))
        g.add(GraphNode("b", "boost"))
        g.connect("a", "b")
        g.connect("b", "a")
        with self.assertRaises(GraphError):
            g.node_output("a")

    def test_missing_input_is_zero(self):
        g = Graph()
        g.add(GraphNode("r1", "result"))
        self.assertEqual(g.node_output("r1"), (0.0, 0.0, 0.0))

    def test_add_node_sums_componentwise(self):
        g = Graph()
        g.add(GraphNode("a1", "aggravate", fields={"em": "200"}))
        g.add(GraphNode("a2", "aggravate", fields={"em": "0"}))
        g.add(GraphNode("s1", "add", inputs=2))
        g.connect("a1", "s1", 0)
        g.connect("a2", "s1", 1)
        v = g.node_output("s1")

        self.assertAlmostEqual(v[0], g.node_output("a1")[0] + g.node_output("a2")[0])

    def test_variadic_inputs_clamped(self):
        self.assertEqual(GraphNode("s", "add", inputs=99).inputs, 12)
        self.assertEqual(GraphNode("s", "add", inputs=0).inputs, 1)
        # 非 variadic 卡片忽略输入的端口数设置
        self.assertEqual(GraphNode("d", "dmg", inputs=7).inputs, 1)

    def test_expression_fields_accepted(self):
        g = Graph()
        g.add(GraphNode("b1", "base", fields={
            "stat_base": "500+500", "multiplier": "100*2"}))
        self.assertAlmostEqual(g.node_output("b1")[0], 2000.0)

    def test_unknown_type_skipped_on_load(self):
        data = dict(nodes=[
            dict(id="n1", type="不存在", pos=[0, 0], fields={}),
            dict(id="n2", type="base", pos=[0, 0],
                 fields={"stat_base": "1000", "multiplier": "200"}),
        ], links=[dict(src="n1", dst="n2", port=0)])
        g = Graph.from_dict(data)

        self.assertEqual(list(g.nodes), ["n2"])
        self.assertEqual(g.links, [])

    def test_zoom_clamped(self):
        self.assertEqual(Graph.from_dict(dict(zoom=99)).zoom, 2.5)
        self.assertEqual(Graph.from_dict(dict(zoom=0.01)).zoom, 0.25)
        self.assertEqual(Graph.from_dict(dict(zoom="坏值")).zoom, 1.0)

    def test_link_to_same_port_replaces(self):
        g = Graph()
        g.add(GraphNode("s1", "base", fields={"stat_base": "1000", "multiplier": "100"}))
        g.add(GraphNode("s2", "base", fields={"stat_base": "2000", "multiplier": "100"}))
        g.add(GraphNode("d1", "dmg", fields={"dmg_net": "0"}))
        g.connect("s1", "d1", 0)
        g.connect("s2", "d1", 0)

        self.assertEqual(len(g.links), 1)
        self.assertEqual(g.link_src("d1", 0), "s2")

    def test_remove_node_drops_links(self):
        g, result = build()
        g.remove("n1")
        self.assertNotIn("n1", g.nodes)
        self.assertEqual([l for l in g.links if l.src == "n1"], [])


class TestSchemaForFrontend(unittest.TestCase):
    """前端完全由 /api/schema 驱动，这里守住它的形状。"""

    def setUp(self):
        self.s = nd.schema()

    def test_every_node_type_described(self):
        self.assertEqual(set(self.s["nodeTypes"]), set(nd.NODE_TYPES))

    def test_groups_cover_every_type(self):
        in_groups = [item["type"] for g in self.s["groups"] for item in g["items"]]
        self.assertEqual(sorted(in_groups), sorted(nd.NODE_TYPES))

    def test_presets_have_no_result_card(self):
        for name, items in self.s["presets"].items():
            self.assertNotIn("result", [i["type"] for i in items], name)

    def test_preset_overrides_are_known_fields(self):
        for name, items in self.s["presets"].items():
            for item in items:
                valid = {f["key"] for f in nd.field_specs(item["type"])}
                for k in item["fields"]:
                    self.assertIn(k, valid, "%s/%s" % (name, item["type"]))

    def test_schema_is_json_serializable(self):
        import json
        json.dumps(self.s, ensure_ascii=False)

    def test_combo_options_present(self):
        amp = self.s["nodeTypes"]["amp"]
        formula = next(f for f in amp["fields"] if f["key"] == "formula")
        self.assertIn("无", formula["options"])
        self.assertTrue(any("×2.0" in o for o in formula["options"]))

    def test_amp_key_backward_compatible(self):
        self.assertEqual(nd.amp_key("蒸发·水打火 ×2.0"), "蒸发·水→火")
        self.assertEqual(nd.amp_key("蒸发·水→火"), "蒸发·水→火")
        self.assertEqual(nd.amp_key("无"), "无")


if __name__ == "__main__":
    unittest.main()

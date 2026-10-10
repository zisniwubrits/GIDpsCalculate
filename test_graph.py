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


class TestCardTitles(unittest.TestCase):
    """卡片标题保持干净：不带装饰性 ＋/×，也不带括号里的公式/来源提示。

    提示文本（k 与分母的取值、属性源/基准值源的定义）统一写在 F1 教程里，
    所以这里反过来断言「标题里不出现括号提示」——谁都别再往上加。
    """

    def test_titles_and_labels_have_no_operator_markers(self):
        for key, spec in nd.NODE_TYPES.items():
            for text in (spec["title"], spec["label"]):
                self.assertNotIn("＋", text, "%s 的标题/菜单名仍带 ＋：%s" % (key, text))
                self.assertFalse(text.startswith("×"),
                                 "%s 的标题/菜单名仍以 × 开头：%s" % (key, text))
                self.assertFalse(text.rstrip().endswith("×"),
                                 "%s 的标题/菜单名仍以 × 结尾：%s" % (key, text))

    def test_titles_have_no_parenthetical_hints(self):
        """标题里不再挂括号提示（公式/来源/单位说明都搬到 F1 教程）。"""
        for key, spec in nd.NODE_TYPES.items():
            title = spec["title"]
            self.assertNotRegex(
                title, r"[（(].*[)）]",
                "%s 的标题仍带括号提示：%s" % (key, title))

    def test_specific_titles(self):
        """典型卡片标题，逐个钉住（改名时能立刻发现）。"""
        self.assertEqual(nd.NODE_TYPES["base"]["title"], "基础值")
        self.assertEqual(nd.NODE_TYPES["crit"]["title"], "暴击区")
        self.assertEqual(nd.NODE_TYPES["dmg"]["title"], "增伤区")
        self.assertEqual(nd.NODE_TYPES["star_coeff"]["title"], "星超导系数")
        self.assertEqual(nd.NODE_TYPES["add"]["title"], "加法合并")
        self.assertEqual(nd.NODE_TYPES["coeff"]["title"], "系数")
        self.assertEqual(nd.NODE_TYPES["attr"]["title"], "◈ 属性源")
        self.assertEqual(nd.NODE_TYPES["react_base"]["title"], "◈ 基准值源")
        self.assertEqual(nd.NODE_TYPES["base_boost"]["title"], "基础提升")
        self.assertEqual(nd.NODE_TYPES["em_gain"]["title"], "精通增益")
        self.assertEqual(nd.NODE_TYPES["aggravate"]["title"], "激化值")
        self.assertEqual(nd.NODE_TYPES["transform"]["title"], "剧变反应")
        self.assertEqual(nd.NODE_TYPES["crystal"]["title"], "结晶护盾")
        self.assertEqual(nd.NODE_TYPES["add"]["label"], "加法")
        self.assertEqual(nd.NODE_TYPES["em_gain"]["label"], "精通增益")

    def test_em_gain_field_labels_are_short(self):
        """精通增益卡的两个输入框提示词要短（取值口径见 F1 教程，不写在标签上）。"""
        labels = {f["key"]: f["label"] for f in nd.NODE_TYPES["em_gain"]["fields"]}
        self.assertEqual(labels["k"], "系数 k")
        self.assertEqual(labels["denom"], "分母")


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

    def test_relic_card_has_only_the_table(self):
        """理想圣遗物卡片只有表格：没有多行文本框字段（用户要求去掉那个控件）。"""
        self.assertEqual(nd.NODE_TYPES["const"]["fields"], [])
        spec = nd.schema()["nodeTypes"]["const"]
        self.assertEqual(spec["fields"], [])
        self.assertEqual(spec["table"], "relic")
        self.assertNotIn("content", [f["key"] for f in spec["fields"]])


class TestVarCardFooter(unittest.TestCase):
    """「变量」卡片底部只展示**本卡片定义**的变量（用户要求，原来打印全局总览）。"""

    def footer(self, graph, nid):
        return graph.evaluate()["nodes"][nid]["varsText"]

    def test_only_own_variables_are_listed(self):
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "攻击力 = 1000\n倍率 = 200"}))
        g.add(GraphNode("v2", "var", fields={"defs": "防御 = 500"}))

        self.assertEqual(self.footer(g, "v1"), "变量: 攻击力=1000, 倍率=200")
        self.assertEqual(self.footer(g, "v2"), "变量: 防御=500")
        # v1 不该出现 v2 的「防御」
        self.assertNotIn("防御", self.footer(g, "v1"))

    def test_values_are_the_effective_ones(self):
        """同名以「后定义者」为准：卡片上显示生效值，与其它卡片实际用到的一致。"""
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "倍率 = 200"}))
        g.add(GraphNode("v2", "var", fields={"defs": "倍率 = 300"}))

        self.assertEqual(self.footer(g, "v1"), "变量: 倍率=300")
        self.assertEqual(self.footer(g, "v2"), "变量: 倍率=300")

    def test_result_variable_override_is_shown(self):
        """被 ★结果 三元组覆盖的名字：卡片仍列出，值显示覆盖后的生效值。"""
        g = Graph()
        g.add(GraphNode("b", "base", fields={"stat_base": "1000", "multiplier": "100"}))
        g.add(GraphNode("r", "result", inputs=1, fields={"var_ex": "倍率"}))
        g.add(GraphNode("v1", "var", fields={"defs": "倍率 = 999"}))
        g.connect("b", "r")

        self.assertEqual(self.footer(g, "v1"), "变量: 倍率=1000")

    def test_empty_and_broken_lines(self):
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": ""}))
        g.add(GraphNode("v2", "var", fields={"defs": "# 注释\n\n坏行没有等号"}))
        g.add(GraphNode("v3", "var", fields={"defs": "好 = 1\n坏 = (("}))

        self.assertEqual(self.footer(g, "v1"), "变量: (无)")
        self.assertEqual(self.footer(g, "v2"), "变量: (无)")
        # 表达式算不出来的行明说「未解析」，不再静默消失
        self.assertEqual(self.footer(g, "v3"), "变量: 好=1, 坏=未解析")

    def test_duplicate_names_listed_once(self):
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "甲 = 1\n甲 = 2"}))
        self.assertEqual(self.footer(g, "v1"), "变量: 甲=2")

    def test_var_table_card_still_lists_everything(self):
        """全局总览仍在「变量表」卡片里（别把两件事混在一起）。"""
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "攻击力 = 1000\n倍率 = 200"}))
        g.add(GraphNode("v2", "var", fields={"defs": "防御 = 500"}))
        g.add(GraphNode("t1", "vartable"))

        rows = g.evaluate()["nodes"]["t1"]["rows"]
        self.assertEqual([r[0] for r in rows], ["攻击力", "倍率", "防御"])

    def test_split_var_line_accepts_three_separators(self):
        from genshin_dmg.graph import split_var_line
        self.assertEqual(split_var_line("甲 = 1"), ("甲", "1"))
        self.assertEqual(split_var_line("甲：1"), ("甲", "1"))
        self.assertEqual(split_var_line("甲: 1"), ("甲", "1"))
        self.assertIsNone(split_var_line(""))
        self.assertIsNone(split_var_line("   "))
        self.assertIsNone(split_var_line("# 甲 = 1"))
        self.assertIsNone(split_var_line("没有分隔符"))
        self.assertIsNone(split_var_line("= 1"))


class TestSetVarCard(unittest.TestCase):
    """「赋值变量」卡片：把上游输出按所选分量赋给一个变量（纯汇点，不进结果链）。"""

    def build(self, pick="期望", name="面板攻击力"):
        g = Graph()
        g.add(GraphNode("n1", "base", fields={"stat_base": "1000", "multiplier": "200"}))
        g.add(GraphNode("n2", "crit"))            # 默认 50% / 100% → 2000 / 4000 / 3000
        g.add(GraphNode("s1", "setvar", fields={"var_name": name, "pick": pick}))
        g.connect("n1", "n2")
        g.connect("n2", "s1")
        return g

    def test_registers_picked_component(self):
        for pick, expect in (("未暴击", 2000.0), ("暴击", 4000.0), ("期望", 3000.0)):
            self.assertEqual(variables_of(self.build(pick=pick)), {"面板攻击力": expect})

    def test_default_pick_is_expected(self):
        """没填「取值」（旧存档）→ 按「期望」处理。"""
        g = Graph()
        g.add(GraphNode("n1", "base", fields={"stat_base": "1000", "multiplier": "200"}))
        g.add(GraphNode("s1", "setvar", fields={"var_name": "面板"}))
        g.connect("n1", "s1")

        self.assertEqual(variables_of(g), {"面板": 2000.0})

    def test_dirty_pick_falls_back_to_expected(self):
        g = self.build(pick="坏值")
        self.assertEqual(variables_of(g), {"面板攻击力": 3000.0})

    def test_blank_or_invalid_name_not_registered(self):
        for name in ("", "  ", "for", "带 空格", "1abc"):
            self.assertEqual(variables_of(self.build(name=name)), {})

    def test_card_shows_assigned_variable_and_value(self):
        out = self.build(name="面板", pick="期望").evaluate()["nodes"]["s1"]
        self.assertEqual(out["display"], "赋值 面板 = %s" % fmt_num(3000.0))
        self.assertEqual(out["boundNames"], ["面板"])

        blank = self.build(name="").evaluate()["nodes"]["s1"]
        self.assertEqual(blank["display"], "未指定变量名")
        self.assertEqual(blank["boundNames"], [])

    def test_usable_by_other_cards_and_var_card(self):
        """赋值出来的变量与结果变量一样通用（变量卡片 / 其它卡片都能引用）。"""
        g = self.build(name="面板")
        g.add(GraphNode("v1", "var", fields={"defs": "秒伤 = 面板/20"}))
        self.assertAlmostEqual(variables_of(g)["秒伤"], 150.0)   # 3000/20

    def test_setvar_wins_name_conflict_with_result_card(self):
        """同名优先级：赋值变量卡 > ★结果卡三元组卡 > 变量卡片。"""
        g = self.build(name="伤害", pick="未暴击")               # 2000
        g.add(GraphNode("r1", "result", fields={"var_ex": "伤害"}))   # 3000
        g.connect("n2", "r1")
        g.add(GraphNode("v1", "var", fields={"defs": "伤害 = 999"}))
        self.assertEqual(variables_of(g)["伤害"], 2000.0)

    def test_sink_card_has_input_but_no_output_port(self):
        spec = nd.NODE_TYPES["setvar"]
        self.assertEqual(spec["inputs"], 1)
        self.assertTrue(spec.get("sink"))            # 前端据此不画输出端口
        self.assertFalse(spec.get("isolated"))
        self.assertFalse(spec.get("no_output"))      # 但仍有底部输出行（显示赋值结果）
        self.assertTrue(nd.node_schema("setvar")["sink"])

    def test_sink_card_does_not_join_result_chain(self):
        g = self.build(name="面板")
        g.add(GraphNode("r1", "result"))
        g.connect("n2", "r1")

        out = g.evaluate()
        self.assertTrue(out["ok"])
        self.assertNotIn("setvar", out["chainTypes"])   # 汇点不在结果链上
        self.assertAlmostEqual(out["result"]["values"]["expected"], 3000.0)


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

    def test_input_count_comes_from_card_type(self):
        """端口数由卡片类型决定：加法卡固定 2 路，不接受运行时扩展（已去掉该能力）。"""
        self.assertEqual(nd.NODE_TYPES["add"]["inputs"], 2)
        self.assertNotIn("variadic", nd.NODE_TYPES["add"])
        # 旧存档里写什么端口数都按类型归一化
        self.assertEqual(GraphNode("s", "add", inputs=99).inputs, 2)
        self.assertEqual(GraphNode("s", "add", inputs=0).inputs, 2)
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

    def test_collapsed_flag_roundtrips(self):
        """折叠是界面状态，但要能随工程 JSON 往返（evaluate 回传的规范图也不丢）。"""
        data = dict(nodes=[
            dict(id="n1", type="dmg", pos=[10, 20], fields={}, collapsed=True),
            dict(id="n2", type="res", pos=[30, 40], fields={}),
        ], links=[])
        g = Graph.from_dict(data)

        self.assertTrue(g.nodes["n1"].collapsed)
        self.assertFalse(g.nodes["n2"].collapsed)          # 旧工程没有该字段 → 展开
        back = Graph.from_dict(g.to_dict())
        self.assertTrue(back.nodes["n1"].collapsed)
        self.assertFalse(back.nodes["n2"].collapsed)

    def test_collapsed_accepts_string_and_garbage(self):
        """JSON 里写成 "false"/坏值时按布尔语义安全解析。"""
        g = Graph.from_dict(dict(nodes=[
            dict(id="n1", type="dmg", fields={}, collapsed="false"),
            dict(id="n2", type="dmg", fields={}, collapsed="坏值"),
        ]))
        self.assertFalse(g.nodes["n1"].collapsed)
        self.assertFalse(g.nodes["n2"].collapsed)

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

    def test_bare_cards(self):
        """bare 是「便签式卡片」的界面提示：文本卡与变量卡（卡片内就是一大块文本框）。"""
        bare = [k for k, v in self.s["nodeTypes"].items() if v["bare"]]
        self.assertEqual(bare, ["text", "var"])

    def test_schema_has_no_variadic_flag(self):
        """不再向前端暴露 variadic：加法卡固定 2 路输入，已去掉运行时扩展能力。"""
        for key, spec in self.s["nodeTypes"].items():
            self.assertNotIn("variadic", spec, key)
        self.assertEqual(self.s["nodeTypes"]["add"]["inputs"], 2)

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

# -*- coding: utf-8 -*-
"""乘区节点编辑器（画布）的行为测试。

覆盖：
  * 「★结果」卡片三元组变量（未暴击 / 暴击 / 期望）登记为全局变量；
  * 变量名非法（关键字 / 带空格）时忽略；
  * 「变量」卡片可引用结果变量（如 秒伤 = 期望伤害/时间）；
  * 结果链没有暴击区时，结果卡片简洁显示单个数值；
  * 「变量表」卡片（样式同理想圣遗物）实时列出所有变量；
  * 工程 JSON 存档往返后变量仍可解析。

需要可用的 Tk 环境；无图形环境时整类跳过。
"""

import re
import unittest

try:
    import tkinter as tk
except ImportError:                       # pragma: no cover - 无 tkinter 的环境
    tk = None

from genshin_dmg import nodeboard as nb


def _make_root():
    """创建隐藏的 Tk 根窗口；不可用时返回 None。"""
    if tk is None:
        return None
    try:
        root = tk.Tk()
    except Exception:                     # pragma: no cover - 无显示环境
        return None
    root.withdraw()
    return root


def _count_entries(widget):
    """统计控件树里的输入框数量。"""
    total = 0
    for child in widget.winfo_children():
        if child.winfo_class() in ("TEntry", "Entry"):
            total += 1
        total += _count_entries(child)
    return total


class _BoardTest(unittest.TestCase):
    """共享一个隐藏 Tk 根窗口的画布测试基类。"""

    @classmethod
    def setUpClass(cls):
        cls.root = _make_root()
        if cls.root is None:
            raise unittest.SkipTest("无可用 Tk 图形环境")

    @classmethod
    def tearDownClass(cls):
        if cls.root is not None:
            cls.root.destroy()

    def setUp(self):
        self.board = nb.NodeBoard(self.root)
        self.addCleanup(self.board.destroy)

    def make_chain(self, with_crit: bool):
        """建一条 base(1000×200%=2000) [→ crit] → result 的链，返回结果卡片 id。"""
        base = self.board.add_node("base")
        self.board.nodes[base]["vars"]["stat_base"].set("1000")
        self.board.nodes[base]["vars"]["multiplier"].set("200")
        src = base
        if with_crit:
            crit = self.board.add_node("crit")        # 默认 50% / 100% → 期望 3000
            self.board.links.append(dict(src=base, dst=crit, port=0))
            src = crit
        result = self.board.add_node("result")
        self.board.links.append(dict(src=src, dst=result, port=0))
        self.board.refresh_outputs()
        return result


class TestResultVariables(_BoardTest):
    def setUp(self):
        super().setUp()
        self.result = self.make_chain(with_crit=True)

    def _set_names(self, nc="", cr="", ex=""):
        v = self.board.nodes[self.result]["vars"]
        v["var_nc"].set(nc)
        v["var_cr"].set(cr)
        v["var_ex"].set(ex)

    def test_triple_registered_as_three_variables(self):
        """三元组分别命名为三个变量，且数值与结果一致。"""
        self._set_names("未暴击伤害", "暴击伤害", "期望伤害")
        self.board.refresh_outputs()

        self.assertAlmostEqual(nb.VAR_ENV["未暴击伤害"], 2000.0)
        self.assertAlmostEqual(nb.VAR_ENV["暴击伤害"], 4000.0)
        self.assertAlmostEqual(nb.VAR_ENV["期望伤害"], 3000.0)

        nc, cr, ex = self.board.evaluate()
        self.assertAlmostEqual(nb.VAR_ENV["未暴击伤害"], nc)
        self.assertAlmostEqual(nb.VAR_ENV["暴击伤害"], cr)
        self.assertAlmostEqual(nb.VAR_ENV["期望伤害"], ex)

    def test_blank_name_defines_nothing(self):
        """留空表示不定义；只填一个也能单独生效。"""
        self._set_names(ex="期望伤害")
        self.board.refresh_outputs()

        self.assertEqual(sorted(nb.VAR_ENV), ["期望伤害"])

    def test_invalid_names_ignored(self):
        """关键字、含空格、以数字开头等非法名不登记。"""
        self._set_names("for", "带 空格", "1abc")
        self.board.refresh_outputs()

        self.assertEqual(nb.VAR_ENV, {})

    def test_result_variable_usable_in_calc_and_var_card(self):
        """结果变量可被计算卡与变量卡片引用。"""
        self._set_names(ex="期望伤害")
        calc = self.board.add_node("calc")
        self.board.nodes[calc]["vars"]["expr"].set("期望伤害/20*60")   # 3000/20*60
        var = self.board.add_node("var")
        self.board.nodes[var]["vars"]["defs"].set("时间 = 20\n秒伤 = 期望伤害/时间")
        self.board.refresh_outputs()

        self.assertIn("9000", self.board.nodes[calc]["out"].get())
        self.assertAlmostEqual(nb.VAR_ENV["秒伤"], 150.0)

    def test_var_card_cannot_override_result_variable(self):
        """同名时以结果卡片为准，派生值也用结果值计算。"""
        self._set_names(ex="伤害A")
        var = self.board.add_node("var")
        self.board.nodes[var]["vars"]["defs"].set("伤害A = 999\n总量 = 伤害A * 3")
        self.board.refresh_outputs()

        self.assertAlmostEqual(nb.VAR_ENV["伤害A"], 3000.0)
        self.assertAlmostEqual(nb.VAR_ENV["总量"], 9000.0)

    def test_result_card_keeps_original_look(self):
        """结果卡片外观不变：可见字段为空，变量名存在隐藏字段里（右键弹窗设置）。"""
        self.assertEqual(nb.NODE_TYPES["result"]["fields"], [])
        self.assertEqual([k for k, _ in nb.RESULT_VAR_FIELDS],
                         ["var_nc", "var_cr", "var_ex"])
        for key in nb.RESULT_VAR_KEYS:
            self.assertIn(key, self.board.nodes[self.result]["vars"])
        self.assertEqual(_count_entries(self.board.nodes[self.result]["frame"]), 0)

    def test_clear_result_vars(self):
        """清除结果变量后不再登记。"""
        self._set_names("伤害A", "伤害B", "伤害C")
        self.board.refresh_outputs()
        self.assertTrue(nb.VAR_ENV)

        self.board._clear_result_vars(self.result)
        self.board.refresh_outputs()
        self.assertEqual(nb.VAR_ENV, {})

    def test_right_click_dialog_has_three_fields(self):
        """右键设置弹窗里有三个变量名输入框，取消后不改动原值。"""
        self._set_names(ex="原期望")
        self.board.refresh_outputs()
        seen = {}

        def close():
            for w in self.board.winfo_children():
                if isinstance(w, tk.Toplevel):
                    seen["entries"] = _count_entries(w)
                    w.destroy()

        self.board.after(120, close)          # 自动关掉弹窗，避免阻塞
        self.board.after(3000, close)         # 兜底，防止极端情况下卡住
        self.board._ask_result_vars(self.result)

        self.assertEqual(seen.get("entries"), 3)
        self.assertAlmostEqual(nb.VAR_ENV["原期望"], 3000.0)   # 取消未改动

    def test_project_roundtrip_keeps_variables(self):
        """JSON 工程存档往返后变量名与数值保留。"""
        self._set_names("未暴击伤害", "暴击伤害", "期望伤害")
        self.board.refresh_outputs()
        data = self.board.to_dict()

        self.board.clear_board()
        self.board.from_dict(data)
        self.board.refresh_outputs()

        self.assertAlmostEqual(nb.VAR_ENV["未暴击伤害"], 2000.0)
        self.assertAlmostEqual(nb.VAR_ENV["暴击伤害"], 4000.0)
        self.assertAlmostEqual(nb.VAR_ENV["期望伤害"], 3000.0)


class TestResultDisplay(_BoardTest):
    def test_no_crit_chain_shows_single_value(self):
        """结果链没有暴击区 → 结果卡片只显示一个数值（简洁）。"""
        result = self.make_chain(with_crit=False)
        text = self.board.nodes[result]["out"].get()

        self.assertEqual(text, "结果 %s" % nb._fmt(2000.0))
        self.assertNotIn("暴击", text)
        self.assertNotIn("期望", text)

    def test_crit_chain_shows_triple(self):
        """链上经过暴击区 → 仍显示 未暴击 ｜ 暴击 ｜ 期望。"""
        result = self.make_chain(with_crit=True)
        text = self.board.nodes[result]["out"].get()

        self.assertIn("未暴击 %s" % nb._fmt(2000.0), text)
        self.assertIn("暴击 %s" % nb._fmt(4000.0), text)
        self.assertIn("期望 %s" % nb._fmt(3000.0), text)

    def test_crit_card_with_no_effect_is_concise(self):
        """暴击区若三条路数值相同（0% 暴击率 / 0% 暴伤），同样简洁显示。"""
        result = self.make_chain(with_crit=True)
        crit = next(k for k, n in self.board.nodes.items() if n["type"] == "crit")
        self.board.nodes[crit]["vars"]["crit_rate"].set("0")
        self.board.nodes[crit]["vars"]["crit_damage"].set("0")
        self.board.refresh_outputs()

        text = self.board.nodes[result]["out"].get()
        self.assertEqual(text, "结果 %s" % nb._fmt(2000.0))

    def test_single_value_result_shows_bound_variable_name(self):
        """单值结果带上绑定的变量名，方便对照引用。"""
        result = self.make_chain(with_crit=False)
        self.board.nodes[result]["vars"]["var_ex"].set("总伤害")
        self.board.refresh_outputs()

        self.assertEqual(self.board.nodes[result]["out"].get(),
                         "结果 %s ｜ 变量 总伤害" % nb._fmt(2000.0))

    def test_single_value_result_lists_all_bound_names(self):
        """三个名字都绑定时依次列出（单值下三个变量同值）。"""
        result = self.make_chain(with_crit=False)
        v = self.board.nodes[result]["vars"]
        v["var_nc"].set("未暴击伤害")
        v["var_cr"].set("暴击伤害")
        v["var_ex"].set("期望伤害")
        self.board.refresh_outputs()

        self.assertEqual(self.board.nodes[result]["out"].get(),
                         "结果 %s ｜ 变量 未暴击伤害 / 暴击伤害 / 期望伤害"
                         % nb._fmt(2000.0))

    def test_triple_result_keeps_names_off_the_label(self):
        """有暴击区时仍只显示三元组（名字不额外堆在卡片上）。"""
        result = self.make_chain(with_crit=True)
        self.board.nodes[result]["vars"]["var_ex"].set("期望伤害")
        self.board.refresh_outputs()

        text = self.board.nodes[result]["out"].get()
        self.assertNotIn("变量", text)
        self.assertIn("期望 %s" % nb._fmt(3000.0), text)


class TestFactorDisplay(_BoardTest):
    def _factor_cards(self):
        for key, spec in nb.NODE_TYPES.items():
            if spec.get("factor") and not spec.get("no_output"):
                yield key, spec

    def test_every_factor_uses_times_sign(self):
        """所有“本卡系数”的数字都带 × 号（如 暴击系数 ×2.630）。"""
        keys = []
        for key, _spec in self._factor_cards():
            keys.append(key)
            self.board.add_node(key)
        self.board.refresh_outputs()
        self.assertGreaterEqual(len(keys), 10)

        for nid, n in self.board.nodes.items():
            spec = nb.NODE_TYPES[n["type"]]
            if not spec.get("factor"):
                continue
            text = str(spec["factor"](self.board._getter(n), []))
            for m in re.finditer(r"\d[\d.,]*", text):
                self.assertEqual(text[m.start() - 1] if m.start() else "", "×",
                                 "%s 的系数显示缺少 × 号：%s" % (n["type"], text))

    def test_crit_factor_text(self):
        """具体文案：暴击系数 ×2.000 ｜ 期望系数 ×1.500（默认 50% / 100%）。"""
        nid = self.board.add_node("crit")
        self.board.refresh_outputs()
        spec = nb.NODE_TYPES["crit"]
        self.assertEqual(str(spec["factor"](self.board._getter(self.board.nodes[nid]), [])),
                         "暴击系数 ×2.000 ｜ 期望系数 ×1.500")


class TestVarTable(_BoardTest):
    def _table(self, nid):
        return self.board.nodes[nid]["table"]

    def test_empty_table_shows_placeholder(self):
        """没有变量时变量表给出占位提示行。"""
        nid = self.board.add_node("vartable")
        self.board.refresh_outputs()

        table = self._table(nid)
        self.assertEqual(table.header, ("变量", "值"))
        self.assertEqual(table.rows, [("（暂无变量）", "")])

    def test_table_lists_var_card_variables(self):
        """变量卡片定义的变量会出现在变量表里（名称 / 值两列）。"""
        var = self.board.add_node("var")
        self.board.nodes[var]["vars"]["defs"].set("攻击力 = 1000\n倍率 = 200")
        nid = self.board.add_node("vartable")
        self.board.refresh_outputs()

        rows = self._table(nid).rows
        self.assertIn(("攻击力", "1000"), rows)
        self.assertIn(("倍率", "200"), rows)
        self.assertNotIn("（暂无变量）", [r[0] for r in rows])

    def test_table_tracks_result_variables(self):
        """结果卡片命名的三元组变量也会实时出现在变量表里。"""
        result = self.make_chain(with_crit=True)
        nid = self.board.add_node("vartable")
        self.board.refresh_outputs()
        self.assertEqual(self._table(nid).rows, [("（暂无变量）", "")])

        self.board.nodes[result]["vars"]["var_ex"].set("期望伤害")
        self.board.refresh_outputs()
        self.assertIn(("期望伤害", "3000"), self._table(nid).rows)

    def test_table_copy_and_look(self):
        """表格可复制（含表头 TSV），且样式与理想圣遗物一致。"""
        var = self.board.add_node("var")
        self.board.nodes[var]["vars"]["defs"].set("攻击力 = 1000")
        nid = self.board.add_node("vartable")
        self.board.refresh_outputs()

        text = self._table(nid).copy_text()
        self.assertEqual(text, "变量\t值\n攻击力\t1000")

        relic = self.board.add_node("const")
        relic_table = self._table(relic)
        self.assertEqual(relic_table.header,
                         ("属性", "强化区间", "最高区间", "平均值"))
        self.assertEqual(relic_table.rows, [tuple(r) for r in nb.RELIC_ROWS])
        self.assertEqual(self._table(nid).outer.cget("bg"),
                         relic_table.outer.cget("bg"))

    def test_vartable_card_has_no_ports(self):
        """变量表是无端口卡片（不参与连线计算）。"""
        spec = nb.NODE_TYPES["vartable"]
        self.assertEqual(spec["inputs"], 0)
        self.assertTrue(spec.get("isolated"))
        self.assertTrue(spec.get("no_output"))
        nid = self.board.add_node("vartable")
        self.board.draw_all()
        self.assertEqual(self.board.nodes[nid]["ports"], {})


if __name__ == "__main__":
    unittest.main()

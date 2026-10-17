# -*- coding: utf-8 -*-
"""角色命名空间（``角色::变量``）的作用域测试。

用户确认的口径：
* 分隔符 ``::``；**无前缀 = 全局**（向后兼容）
* 角色容器里的卡片：变量卡片 / ★结果三元组 / 赋值变量卡登记的名字都自动带角色前缀
* 读变量时**先本角色、再全局**（就近解析）；显式写 ``胡桃::攻击力`` 在任何地方都取得到
* 名字里禁止 ``__``（保留给内部拼接），变量表对外显示 ``角色::变量``

运行：``python -m pytest test_role_namespace.py -q``
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from genshin_dmg import damage as dmg
from genshin_dmg import nodes as nd
from genshin_dmg.expr import demangle, env_key, is_sub_ns, mangle, qualify, valid_var_name
from genshin_dmg.graph import Graph, GraphNode, Link


def var_card(nid, defs, role=""):
    return GraphNode(nid, "var", fields={"defs": defs}, role=role)


def table_card(nid="t1"):
    return GraphNode(nid, "vartable")


class TestNameSyntax(unittest.TestCase):
    def test_mangle_and_demangle_roundtrip(self):
        self.assertEqual(mangle("雷神::攻击力*2"), "雷神__攻击力*2")
        self.assertEqual(demangle("雷神__攻击力"), "雷神::攻击力")
        self.assertEqual(demangle("攻击力"), "攻击力")
        self.assertEqual(env_key("雷神::攻击力"), "雷神__攻击力")

    def test_valid_var_name_accepts_namespace(self):
        self.assertEqual(valid_var_name("雷神::攻击力"), "雷神::攻击力")
        self.assertEqual(valid_var_name(" 雷神 :: 攻击力 "), "雷神::攻击力")
        self.assertEqual(valid_var_name("攻击力"), "攻击力")

    def test_valid_var_name_rejects_reserved_and_junk(self):
        for bad in ("", "  ", "::", "a__b", "雷神::a__b", "雷神::", "1abc", "a b", "a-b",
                    "雷神:::攻击力", "雷神::攻击力::"):
            self.assertEqual(valid_var_name(bad), "", bad)

    def test_valid_var_name_accepts_sub_namespace(self):
        """多段命名空间（消除"生效值/自身/给出去/收进来"歧义）都算合法名字。"""
        self.assertEqual(valid_var_name("火神::own::atk"), "火神::own::atk")
        self.assertEqual(valid_var_name("火神 :: out :: atk"), "火神::out::atk")
        # 前导 :: = "本角色的"，规范化时去掉
        self.assertEqual(valid_var_name("::out::atk"), "out::atk")
        self.assertEqual(valid_var_name("::in::攻击力"), "in::攻击力")
        self.assertEqual(valid_var_name("雷神::攻击力::x"), "雷神::攻击力::x")

    def test_mangle_sub_namespace(self):
        self.assertEqual(mangle("火神::out::atk*2"), "火神__out__atk*2")
        self.assertEqual(mangle("::in::atk"), "in__atk")
        self.assertEqual(demangle("火神__out__atk"), "火神::out::atk")
        self.assertEqual(env_key("火神::out::atk"), "火神__out__atk")

    def test_is_sub_ns(self):
        self.assertTrue(is_sub_ns("火神::out::atk"))
        self.assertTrue(is_sub_ns("own::atk"))
        self.assertFalse(is_sub_ns("火神::atk"))
        self.assertFalse(is_sub_ns("own"))          # 变量本身叫 own 不算
        self.assertFalse(is_sub_ns("atk"))

    def test_qualify(self):
        self.assertEqual(qualify("攻击力", "雷神"), "雷神::攻击力")
        self.assertEqual(qualify("攻击力", ""), "攻击力")
        # 已经写了前缀就不再套一层
        self.assertEqual(qualify("胡桃::攻击力", "雷神"), "胡桃::攻击力")
        # 子命名空间：本角色的 own/out/in
        self.assertEqual(qualify("out::atk", "火神"), "火神::out::atk")
        self.assertEqual(qualify("::in::atk", "火神"), "火神::in::atk")


class TestScoping(unittest.TestCase):
    """同名变量在两个角色里互不干扰，且就近解析。"""

    def build(self):
        g = Graph()
        # 全局变量
        g.add(var_card("g1", "攻击力 = 100\n暴击 = 5"))
        # 两个角色各有一张变量卡，都定义了「攻击力」
        g.add(var_card("v1", "攻击力 = 1000", role="雷神"))
        g.add(var_card("v2", "攻击力 = 2000", role="胡桃"))
        return g

    def test_each_role_keeps_its_own_value(self):
        out = self.build().evaluate()
        names = {v["name"]: v["value"] for v in out["variables"]}

        self.assertEqual(names["攻击力"], 100)                 # 全局那份
        self.assertEqual(names["雷神::攻击力"], 1000)
        self.assertEqual(names["胡桃::攻击力"], 2000)

    def test_variable_table_shows_display_names(self):
        g = self.build()
        g.add(table_card())
        rows = dict(g.evaluate()["nodes"]["t1"]["rows"])

        self.assertEqual(rows["雷神::攻击力"], "1000")
        self.assertEqual(rows["胡桃::攻击力"], "2000")
        self.assertEqual(rows["攻击力"], "100")

    def test_var_card_footer_lists_qualified_names(self):
        out = self.build().evaluate()

        self.assertEqual(out["nodes"]["v1"]["varsText"], "变量: 雷神::攻击力=1000")
        self.assertEqual(out["nodes"]["v2"]["varsText"], "变量: 胡桃::攻击力=2000")
        self.assertEqual(out["nodes"]["g1"]["varsText"], "变量: 攻击力=100, 暴击=5")

    def test_nearest_scope_wins_when_reading(self):
        """卡片在 雷神 里写「攻击力」→ 取 1000；在外面写 → 取全局 100。"""
        g = self.build()
        inside = GraphNode("c1", "calc", fields={"expr": "攻击力"},
                           role="雷神")
        outside = GraphNode("c2", "calc", fields={"expr": "攻击力"})
        g.add(inside)
        g.add(outside)
        out = g.evaluate()

        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 1000)
        self.assertEqual(out["nodes"]["c2"]["values"]["noncrit"], 100)

    def test_falls_back_to_global_when_role_has_no_such_name(self):
        g = self.build()
        card = GraphNode("c1", "calc", fields={"expr": "暴击"}, role="雷神")
        g.add(card)
        # 雷神 里没有「暴击」→ 用全局的 5
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 5)

    def test_explicit_namespace_works_from_anywhere(self):
        g = self.build()
        card = GraphNode("c1", "calc", fields={"expr": "胡桃::攻击力 + 雷神::攻击力"},
                         role="雷神")
        g.add(card)
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 3000)

    def test_fullwidth_colons_accepted(self):
        g = self.build()
        card = GraphNode("c1", "calc", fields={"expr": "雷神：：攻击力"})
        g.add(card)
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 1000)

    def test_undefined_namespaced_variable_reports_display_name(self):
        g = self.build()
        card = GraphNode("c1", "calc", fields={"expr": "胡桃::防御力"})
        g.add(card)
        text = g.evaluate()["nodes"]["c1"]["display"]

        self.assertIn("未定义变量: 胡桃::防御力", text)
        self.assertNotIn("__", text)            # 内部拼接符不能露出来


class TestRegistration(unittest.TestCase):
    """结果卡片三元组 / 赋值变量卡登记的名字也带角色前缀。"""

    def test_result_card_variables_are_qualified(self):
        g = Graph()
        g.add(GraphNode("b", "base", fields={"stat_base": "1000", "multiplier": "100"},
                        role="雷神"))
        g.add(GraphNode("r", "result", fields={"var_ex": "期望伤害"}, role="雷神"))
        g.connect("b", "r")
        out = g.evaluate()

        names = {v["name"] for v in out["variables"]}
        self.assertIn("雷神::期望伤害", names)
        self.assertIn("雷神::期望伤害", out["nodes"]["r"]["boundNames"])
        self.assertIn("变量 雷神::期望伤害", out["nodes"]["r"]["display"])

    def test_setvar_registers_qualified_name(self):
        g = Graph()
        g.add(GraphNode("b", "base", fields={"stat_base": "1000", "multiplier": "100"},
                        role="胡桃"))
        g.add(GraphNode("s", "setvar", fields={"var_name": "面板攻击力", "pick": "期望"},
                        role="胡桃"))
        g.connect("b", "s")
        out = g.evaluate()

        self.assertIn("胡桃::面板攻击力", {v["name"] for v in out["variables"]})
        self.assertEqual(out["nodes"]["s"]["boundNames"], ["胡桃::面板攻击力"])
        # 展示用 fmt_num（带千分位与两位小数），这里只断言名字对
        self.assertIn("赋值 胡桃::面板攻击力 = ", out["nodes"]["s"]["display"])

    def test_same_name_in_two_roles_does_not_collide(self):
        """两张赋值卡在两个角色里登记同名变量，各自独立。"""
        g = Graph()
        for i, role in enumerate(("雷神", "胡桃"), start=1):
            g.add(GraphNode("b%d" % i, "base",
                            fields={"stat_base": str(100 * i), "multiplier": "100"},
                            role=role))
            g.add(GraphNode("s%d" % i, "setvar",
                            fields={"var_name": "面板", "pick": "期望"}, role=role))
            g.connect("b%d" % i, "s%d" % i)
        names = {v["name"]: v["value"] for v in g.evaluate()["variables"]}

        self.assertEqual(names["雷神::面板"], 100)      # 100 × 100%
        self.assertEqual(names["胡桃::面板"], 200)      # 200 × 100%

    def test_result_variable_can_still_be_read_locally(self):
        """结果变量在**同一个角色**里可以按裸名读（就近解析）。"""
        g = Graph()
        g.add(GraphNode("b", "base", fields={"stat_base": "1000", "multiplier": "100"},
                        role="雷神"))
        g.add(GraphNode("r", "result", fields={"var_ex": "期望伤害"}, role="雷神"))
        g.add(GraphNode("c", "calc", fields={"expr": "期望伤害/20*60"}, role="雷神"))
        g.connect("b", "r")

        self.assertEqual(g.evaluate()["nodes"]["c"]["values"]["noncrit"], 3000)


class TestRolePanel(unittest.TestCase):
    """角色面板化：面板项 = 本角色命名空间里的变量（固定 ASCII 词表）。

    规则（用户确认）：**卡片字段留空 → 用本角色面板兜底**；字段写了值就以卡片为准。
    """

    def graph(self, defs, role="火神"):
        g = Graph()
        g.add(GraphNode("role", "role", fields={"role_name": role}))
        g.add(var_card("v1", defs, role=role))
        return g

    def add(self, g, nid, card_type, role="火神", **fields):
        # 参数名不能叫 kind：aggravate 卡片自己就有个字段叫 kind
        n = GraphNode(nid, card_type, fields=fields, role=role)
        g.add(n)
        return n

    def value(self, g, nid):
        return g.evaluate()["nodes"][nid]["values"]["noncrit"]

    def test_atk_feeds_base_stat(self):
        g = self.graph("atk = 2000\natk_pct = 50\natk_flat = 100")
        self.add(g, "b", "base", stat_base="", stat_big="", stat_flat="", multiplier="200")
        # (2000×1.5 + 100) × 200% = 6200
        self.assertEqual(self.value(g, "b"), 6200)

    def test_field_written_by_user_wins(self):
        g = self.graph("atk = 2000")
        self.add(g, "b", "base", stat_base="1000", multiplier="200")
        self.assertEqual(self.value(g, "b"), 2000)      # 用卡片上的 1000，不用面板

    def test_without_macro_falls_back_to_field_default(self):
        g = self.graph("atk = 2000")                    # 没定义 atk_pct
        self.add(g, "d", "dmg", dmg_net="")             # 增伤区净% 留空
        self.assertEqual(self.value(g, "d"), 0.0)       # 默认 0 → dmg 卡无输入时输出 0

    def test_dmg_and_res_shred(self):
        g = self.graph("dmg = 50\nres_shred = 40")
        self.add(g, "b", "base", stat_base="1000", multiplier="100")
        self.add(g, "d", "dmg", dmg_net="")
        self.add(g, "r", "res", resistance="")
        g.connect("b", "d")
        g.connect("d", "r")
        out = g.evaluate()
        self.assertEqual(out["nodes"]["d"]["values"]["noncrit"], 1500)   # ×1.5
        self.assertEqual(out["nodes"]["r"]["values"]["noncrit"], 1800)   # 减抗 40 → ×1.2

    def test_crit_panel(self):
        g = self.graph("crit_rate = 70\ncrit_dmg = 140")
        self.add(g, "b", "base", stat_base="1000", multiplier="100")
        self.add(g, "c", "crit", crit_rate="", crit_damage="")
        g.connect("b", "c")
        v = g.evaluate()["nodes"]["c"]["values"]
        self.assertAlmostEqual(v["crit"], 2400.0, places=6)              # 1+140%
        self.assertAlmostEqual(v["expected"], 1980.0, places=6)          # 1+0.7×1.4

    def test_em_feeds_several_cards(self):
        g = self.graph("em = 200")
        self.add(g, "b", "base", stat_base="1000", multiplier="100")
        self.add(g, "a", "amp", formula="蒸发·水打火 ×2.0", em="")
        self.add(g, "agg", "aggravate", kind="超激化", level="90", em="")
        g.connect("b", "a")
        out = g.evaluate()
        # 蒸发 ×2.0 + 精通加成（em 由面板喂进来）
        self.assertIn("×2.695", out["nodes"]["a"]["factor"])
        # 激化值 = 等级基准 × 1.15 × (1 + 5×200/1400)，与公式函数逐位对齐
        self.assertAlmostEqual(out["nodes"]["agg"]["values"]["noncrit"],
                               dmg.aggravate_value("超激化", 200, 0.0, 90), places=6)
        self.assertGreater(out["nodes"]["agg"]["values"]["noncrit"],
                           dmg.aggravate_value("超激化", 0.0, 0.0, 90))

    def test_month_dmg_feeds_base_boost(self):
        g = self.graph("month_dmg = 50")
        self.add(g, "b", "base", stat_base="1000", multiplier="100")
        self.add(g, "bb", "base_boost", base_boost="")
        g.connect("b", "bb")
        self.assertEqual(self.value(g, "bb"), 1500)                      # ×(1+50%)

    def test_panel_is_per_role(self):
        """火神的面板不喂胡桃的卡片（要靠拐力箭头才会）。"""
        g = self.graph("atk = 2000")
        self.add(g, "b2", "base", role="胡桃", stat_base="", multiplier="100")
        # 胡桃 没定义 atk → 走字段默认 1000
        self.assertEqual(self.value(g, "b2"), 1000)

    def test_global_variable_also_works_as_panel(self):
        """没有角色时，全局变量同样能当面板（就近解析的延伸）。"""
        g = Graph()
        g.add(var_card("v1", "atk = 3000"))
        self.add(g, "b", "base", role="", stat_base="", multiplier="100")
        self.assertEqual(self.value(g, "b"), 3000)

    def test_panel_macro_can_be_used_in_expressions(self):
        """面板项也是变量：字段里可以写算式引用它。"""
        g = self.graph("atk = 2000")
        self.add(g, "b", "base", stat_base="atk*1.5", multiplier="100")
        self.assertEqual(self.value(g, "b"), 3000)


class TestBuffArrows(unittest.TestCase):
    """拐力箭头：角色卡 → 角色卡，把源角色**声明过的 out::** 加到目标角色的同名项上。

    用户确认：多来源**相加**；**不传递**；而且**只有 `out::` 才给出去** ——
    面板里的普通项（`atk` / `atk_pct` …）是"自己用的属性表"，不发拐力。
    """

    @staticmethod
    def preset(defs):
        """模拟"程序填进变量卡的预设代码"，只补用户没写过的宏（用户写的优先）。"""
        lines = [defs] if defs else []
        for k in nd.PANEL_MACRO_KEYS:
            if ("%s =" % k) not in defs:
                lines.append("%s = own::%s + in::%s" % (k, k, k))
        return "\n".join(lines)

    def build(self, grants, target_defs="atk = 1000", target="火神", source="辅助"):
        target_defs = self.preset(target_defs)
        g = Graph()
        g.add(GraphNode("r_src", "role", fields={"role_name": source}))
        g.add(GraphNode("r_dst", "role", fields={"role_name": target}))
        g.add(var_card("v_src", grants, role=source))
        g.add(var_card("v_dst", target_defs, role=target))
        g.add(GraphNode("b", "base",
                        fields={"stat_base": "", "stat_big": "", "multiplier": "100"},
                        role=target))
        return g

    def base_value(self, g):
        return g.evaluate()["nodes"]["b"]["values"]["noncrit"]

    def test_arrow_adds_source_panel_onto_target(self):
        g = self.build("out::atk_pct = 40")
        self.assertEqual(self.base_value(g), 1000)          # 没箭头：只有自己
        g.links.append(Link("r_src", "r_dst", 0))
        self.assertEqual(self.base_value(g), 1400)          # 拐上 40% 攻击

    def test_plain_panel_entry_does_not_grant(self):
        """新口径：面板里的普通项（没写 out::）**不发拐力**，箭头等于白拖。"""
        g = self.build("atk_pct = 40")
        g.links.append(Link("r_src", "r_dst", 0))
        self.assertEqual(self.base_value(g), 1000)
        # 源自己的计算照旧不受影响（面板项还是它自己的属性）
        g.add(GraphNode("bs", "base",
                        fields={"stat_base": "", "stat_big": "atk_pct", "multiplier": "100"},
                        role="辅助"))
        self.assertEqual(g.evaluate()["nodes"]["bs"]["values"]["noncrit"], 1400)

    def test_own_value_wins_no_auto_sum(self):
        """取消自动相加后：自身写了 10 就以 10 为准（以前是 20 → 50%）。"""
        g = self.build("out::atk_pct = 40", target_defs="atk = 1000\natk_pct = 10")
        g.links.append(Link("r_src", "r_dst", 0))
        self.assertEqual(self.base_value(g), 1100)
        # 想要"自身 + 拐"，自己在变量卡里写出来
        g2 = self.build("out::atk_pct = 40",
                        target_defs="atk = 1000\n总 = own::atk_pct + in::atk_pct")
        g2.add(GraphNode("b2", "base",
                         fields={"stat_base": "", "stat_big": "总", "multiplier": "100"},
                         role="火神"))
        g2.links.append(Link("r_src", "r_dst", 0))
        # 目标没写自身 atk_pct → own:: 是 0，所以 总 = 0 + 40 → 1000×1.4
        self.assertEqual(g2.evaluate()["nodes"]["b2"]["values"]["noncrit"], 1400)

    def test_multiple_sources_add_up(self):
        g = self.build("out::atk_pct = 40")
        g.add(GraphNode("r_src2", "role", fields={"role_name": "另一个辅助"}))
        g.add(var_card("v_src2", "out::atk_pct = 25", role="另一个辅助"))
        g.links.append(Link("r_src", "r_dst", 0))
        g.links.append(Link("r_src2", "r_dst", 0))
        self.assertEqual(self.base_value(g), 1650)          # 40+25 = 65%

    def test_not_propagated(self):
        """不传递：C→A、A→B 时 B 只拿 A 自己声明过的 out::（不含 C 给 A 的拐）。"""
        g = self.build("out::atk_pct = 40")
        g.add(GraphNode("r_c", "role", fields={"role_name": "拐A的"}))
        g.add(var_card("v_c", "out::atk_pct = 100", role="拐A的"))
        g.links.append(Link("r_c", "r_src", 0))             # C → A
        g.links.append(Link("r_src", "r_dst", 0))           # A → B
        # A 对外提供的仍是自己声明的 40（不因为收到 C 的 100 而变成 140）
        self.assertEqual(self.base_value(g), 1400)

    def test_source_role_is_not_buffed_by_its_own_grant(self):
        """自己给自己上拐的箭头无效（自连被忽略），源角色自己的计算不变。"""
        g = self.build("out::atk_pct = 40", target_defs="atk = 1000")
        g.nodes["r_dst"].fields["role_name"] = "辅助"        # 让箭头变成 A→A
        g.links.append(Link("r_src", "r_dst", 0))
        self.assertEqual(self.base_value(g), 1000)

    def test_arrow_between_invalid_roles_is_ignored(self):
        g = self.build("out::atk_pct = 40")
        g.nodes["r_src"].fields["role_name"] = "有 空格"     # 非法角色名
        g.links.append(Link("r_src", "r_dst", 0))
        self.assertEqual(self.base_value(g), 1000)

    def test_unrelated_role_is_unaffected(self):
        g = self.build("out::atk_pct = 40")
        g.add(GraphNode("b3", "base",
                        fields={"stat_base": "", "stat_big": "", "multiplier": "100"},
                        role="胡桃"))
        g.add(var_card("v3", "atk = 500", role="胡桃"))
        g.links.append(Link("r_src", "r_dst", 0))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["b3"]["values"]["noncrit"], 500)   # 胡桃没被拐

    def test_granted_macro_appears_in_variable_table(self):
        g = self.build("out::atk_pct = 40", target_defs="atk = 1000\natk_pct = 10")
        g.add(GraphNode("t", "vartable"))
        g.links.append(Link("r_src", "r_dst", 0))
        rows = dict(g.evaluate()["nodes"]["t"]["rows"])
        self.assertEqual(rows["火神::atk_pct"], "10")        # 自身优先（不再自动加拐）
        self.assertEqual(rows["辅助::atk_pct"], "40")        # 源角色对外声明的那份

    def test_target_expression_using_macro_sees_the_grant(self):
        """目标角色里以面板宏写的算式也吃到拐（变量那一轮会带着拐力重跑）。"""
        g = self.build("out::atk = 500", target_defs="atk = 1000\ntotal = atk * 2")
        g.links.append(Link("r_src", "r_dst", 0))
        names = {v["name"]: v["text"] for v in g.evaluate()["variables"]}
        # 取消自动相加：自身写了 1000 → atk 就是 1000（不再加收进来的 500）
        self.assertEqual(names["火神::total"], "2000")

    def test_buff_edges_helper(self):
        g = self.build("out::atk_pct = 40")
        g.links.append(Link("r_src", "r_dst", 0))
        self.assertEqual(g.buff_edges(), [("辅助", "火神")])


class TestRoleCardPanel(unittest.TestCase):
    """角色卡自带的「面板」字段（右键「角色面板…」弹窗编辑）与拐力统计。"""

    def build(self, panel_a="out::atk_pct = 40", panel_b="atk = 1000"):
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助", "panel": panel_a}))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神", "panel": panel_b}))
        return g

    def test_panel_on_role_card_feeds_own_cards(self):
        g = self.build()
        g.add(GraphNode("b", "base", fields={"stat_base": "", "multiplier": "100"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["b"]["values"]["noncrit"], 1000)

    def test_role_card_panel_wins_over_variable_card(self):
        """面板是"正主"：角色卡上的同名宏覆盖变量卡里的定义。"""
        g = self.build(panel_b="atk = 1000")
        g.add(var_card("v", "atk = 500", role="火神"))
        g.add(GraphNode("b", "base", fields={"stat_base": "", "multiplier": "100"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["b"]["values"]["noncrit"], 1000)

    def test_panel_grants_through_arrow(self):
        g = self.build()
        # 面板属性不自动计算：目标角色自己写一行（= 预设代码的形状）才会吃到拐
        g.add(var_card("vb", "atk_pct = own::atk_pct + in::atk_pct", role="火神"))
        g.add(GraphNode("b", "base",
                        fields={"stat_base": "1000", "stat_big": "", "multiplier": "100"},
                        role="火神"))
        g.links.append(Link("ra", "rb", 0))
        self.assertEqual(g.evaluate()["nodes"]["b"]["values"]["noncrit"], 1400)

    def test_panel_ignores_unknown_macro_names(self):
        g = self.build(panel_b="atk = 1000\n乱写的 = 999")
        g.add(GraphNode("b", "base", fields={"stat_base": "", "multiplier": "100"}, role="火神"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["b"]["values"]["noncrit"], 1000)
        self.assertNotIn("火神::乱写的", {v["name"] for v in out["variables"]})

    def test_buff_stats_shape(self):
        g = self.build()
        g.links.append(Link("ra", "rb", 0))
        stats = g.evaluate()["buffStats"]

        self.assertEqual(stats["辅助"]["out"],
                         [dict(macro="atk_pct", label="攻击%", value=40.0, role="火神")])
        self.assertEqual(stats["火神"]["in"],
                         [dict(macro="atk_pct", label="攻击%", value=40.0, role="辅助")])
        self.assertEqual(stats["辅助"]["in"], [])
        self.assertEqual(stats["火神"]["out"], [])

    def test_panel_and_buff_markers(self):
        """卡片上的可见标注：panelFields（哪些字段吃面板）与 buffed（是否含拐）。"""
        g = self.build()
        g.add(GraphNode("b", "base", fields={"stat_base": "", "multiplier": "100"}, role="火神"))
        g.links.append(Link("ra", "rb", 0))
        info = g.evaluate()["nodes"]["b"]

        self.assertEqual(info["panelFields"], ["白值"])
        self.assertTrue(info["buffed"])
        # 没被拐、也没吃面板的卡片不标
        g2 = self.build()
        g2.add(GraphNode("b", "base", fields={"stat_base": "1000"}, role="火神"))
        info2 = g2.evaluate()["nodes"]["b"]
        self.assertEqual(info2["panelFields"], [])
        self.assertFalse(info2["buffed"])


class TestPanelCustomOut(unittest.TestCase):
    """角色卡面板里的**自定义对外项**：``out::名字 = 值``。

    场景（用户要求）：「角色面板…」弹窗里能直接加一行"我对外提供多少"，
    不必再拖一张变量卡手写 ``out::名字``。名字规则由后端定
    （``nodes.valid_panel_custom_name`` / schema 的 ``panelCustomPattern``）。
    """

    def build(self, panel_a="out::atk_pct = 40", panel_b=""):
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助", "panel": panel_a}))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神", "panel": panel_b}))
        g.links.append(Link("ra", "rb", 0))
        return g

    def test_custom_out_row_grants(self):
        """面板里写 ``out::atk_pct = 40`` 与变量卡写 ``out::atk_pct = 40`` 等效。"""
        g = self.build()
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        g.add(GraphNode("c2", "calc", fields={"expr": "out::atk_pct"}, role="辅助"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 40)   # 目标收到拐
        self.assertEqual(out["nodes"]["c2"]["values"]["noncrit"], 40)   # 源对外就是这个值

    def test_custom_out_row_is_not_a_panel_macro(self):
        """自定义项不是面板宏：目标角色**不会**自动拿到 ``火神::atk_pct``，要走 in::。"""
        g = self.build()
        g.add(GraphNode("c1", "calc", fields={"expr": "atk_pct"}, role="火神"))
        out = g.evaluate()
        self.assertNotIn("火神::atk_pct", {v["name"] for v in out["variables"]})
        self.assertIn("未定义变量", out["nodes"]["c1"]["display"])

    def test_custom_name_can_differ_from_own(self):
        """自定义项可以有自己的值：对面收到的是这一行，不是面板里的宏。"""
        g = self.build(panel_a="atk_pct = 10\nout::atk_pct = 40")
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 40)
        self.assertIn(("辅助::atk_pct", "10"), {(v["name"], v["text"]) for v in out["variables"]})

    def test_custom_row_shows_up_in_buff_stats(self):
        """自定义名字一样进「角色面板…」弹窗的 OUT / IN 统计（label 回退成名字本身）。"""
        g = self.build()
        stats = g.evaluate()["buffStats"]
        self.assertEqual(
            stats["辅助"]["out"],
            [dict(macro="atk_pct", label="攻击%", value=40.0, role="火神")],
        )

    def test_custom_row_rejects_bad_names(self):
        """非法名字（大写 / ``__`` / 空）不定义，也不参与拐力。"""
        g = self.build(panel_a="out::Bad = 1\nout::a__b = 2\nout:: = 3\nout::good_one = 4")
        g.add(GraphNode("c1", "calc", fields={"expr": "in::good_one"}, role="火神"))
        out = g.evaluate()
        names = {v["name"] for v in out["variables"]}
        self.assertIn("辅助::good_one", names)          # 变量表里显示的是短名
        self.assertNotIn("辅助::Bad", names)
        self.assertNotIn("辅助::a__b", names)
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 4)

    def test_panel_custom_name_rule(self):
        ok = nd.valid_panel_custom_name
        self.assertEqual(ok("atk_gift"), "atk_gift")
        self.assertEqual(ok("  buff2  "), "buff2")
        for bad in ("", "  ", "Bad", "2x", "a__b", "a b", "atk", "atk_pct", "拐力A", "a::b"):
            self.assertEqual(ok(bad), "", bad)

    def test_weapon_panel_not_used(self):
        """武器没有面板字段 —— 它的自定义对外项仍走变量卡（回归保护）。"""
        g = Graph()
        g.add(GraphNode("rw", "weapon", fields={"role_name": "护摩", "panel": "out::x = 9"}))
        g.add(GraphNode("ra", "role", fields={"role_name": "火神"}))
        g.add(var_card("vw", "out::x = 9", role="护摩"))
        g.links.append(Link("rw", "ra", 0))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::x"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 9)


class TestSubNamespaces(unittest.TestCase):
    """子命名空间（``own`` / ``out`` / ``in``）：消除"生效值/自身/给出去/收进来"的歧义。

    用户确认的四个名字（以火神自己写 out::atk_pct=10、收到辅助 40 为例）：
      * 火神::atk_pct      = 10（生效值 = 自己写的那个值）
      * 火神::own::atk_pct = 10（纯自身）
      * 火神::out::atk_pct = 10（对外提供的：**只有显式写 out:: 才有**）
      * 火神::in::atk_pct  = 40（收进来的，多来源相加）
    并且：**任意变量都支持**（没写 out:: 的变量 out 就是 0、in 也是 0）、
    **角色内可省略角色名**。
    """

    def build(self, link=True):
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助", "panel": "out::atk_pct = 40"}))
        g.add(GraphNode("rb", "role",
                        fields={"role_name": "火神", "panel": "atk = 1000\nout::atk_pct = 10"}))
        g.add(var_card("vb", "攻击力 = 2000", role="火神"))
        if link:
            g.links.append(Link("ra", "rb", 0))
        return g

    def calc(self, g, nid, expr, role="火神"):
        g.add(GraphNode(nid, "calc", fields={"expr": expr}, role=role))
        return g.evaluate()["nodes"][nid]["values"]["noncrit"]

    def test_four_names(self):
        g = self.build()
        self.assertEqual(self.calc(g, "c1", "atk_pct"), 10)          # 生效值 = 自己写的
        self.assertEqual(self.calc(g, "c2", "own::atk_pct"), 10)     # 纯自身
        self.assertEqual(self.calc(g, "c3", "out::atk_pct"), 10)     # 显式声明过才对外
        self.assertEqual(self.calc(g, "c4", "::in::atk_pct"), 40)    # 收进来
        # 前导 :: 与不写一样，都指"本角色"
        self.assertEqual(self.calc(g, "c5", "in::atk_pct"), 40)

    def test_full_names_work_from_anywhere(self):
        g = self.build()
        self.assertEqual(self.calc(g, "c1", "火神::atk_pct", role=""), 10)
        self.assertEqual(self.calc(g, "c2", "火神::in::atk_pct", role=""), 40)
        self.assertEqual(self.calc(g, "c3", "火神::own::atk_pct", role=""), 10)
        # 从别的角色里看也一样（全名不受就近解析影响）
        self.assertEqual(self.calc(g, "c4", "火神::in::atk_pct", role="胡桃"), 40)

    def test_any_variable_supports_sub_namespaces(self):
        """非面板宏、也没写 out:: 的变量：own 是它自己的值，out / in 都是 0。"""
        g = self.build()
        self.assertEqual(self.calc(g, "c1", "攻击力"), 2000)
        self.assertEqual(self.calc(g, "c2", "own::攻击力"), 2000)
        self.assertEqual(self.calc(g, "c3", "out::攻击力"), 0)     # 没声明就不对外提供
        self.assertEqual(self.calc(g, "c4", "in::攻击力"), 0)
        self.assertEqual(self.calc(g, "c5", "火神::in::攻击力", role=""), 0)

    def test_in_sums_multiple_sources(self):
        g = self.build()
        g.add(GraphNode("rc", "role", fields={"role_name": "另一个辅助", "panel": "out::atk_pct = 25"}))
        g.links.append(Link("rc", "rb", 0))
        self.assertEqual(self.calc(g, "c1", "::in::atk_pct"), 65)     # 40 + 25（多来源在 in 里相加）
        self.assertEqual(self.calc(g, "c2", "::own::atk_pct"), 10)    # 自身不受影响
        self.assertEqual(self.calc(g, "c3", "atk_pct"), 10)           # 生效值仍是自己写的

    def test_not_propagated(self):
        """不传递：C→A、A→B 时 B 只拿到 A 声明的 out::（不含 C 给 A 的）。"""
        g = self.build(link=False)
        g.add(GraphNode("rc", "role", fields={"role_name": "拐A的", "panel": "out::atk_pct = 100"}))
        g.links.append(Link("rc", "ra", 0))
        g.links.append(Link("ra", "rb", 0))
        self.assertEqual(self.calc(g, "c1", "辅助::in::atk_pct", role=""), 100)   # A 收到了
        self.assertEqual(self.calc(g, "c2", "辅助::out::atk_pct", role=""), 40)   # 对外仍是自己声明的
        self.assertEqual(self.calc(g, "c3", "::in::atk_pct"), 40)                 # B 只拿 A 的 out

    def test_variable_table_does_not_list_sub_namespaces(self):
        """子命名空间只在表达式里可用，不往变量表里灌三倍的行。"""
        g = self.build()
        g.add(GraphNode("t", "vartable"))
        names = [r[0] for r in g.evaluate()["nodes"]["t"]["rows"]]
        self.assertIn("火神::atk_pct", names)
        self.assertIn("火神::攻击力", names)
        self.assertFalse([n for n in names if "own::" in n or "out::" in n or "in::" in n], names)
        # 接口返回的变量列表同样干净
        api = [v["name"] for v in g.evaluate()["variables"]]
        self.assertFalse([n for n in api if "own::" in n or "out::" in n or "in::" in n], api)

    def test_usable_in_field_expressions_and_fallbacks(self):
        """卡片字段里（含算式）可以直接用子命名空间。"""
        g = self.build()
        g.add(GraphNode("b", "base",
                        fields={"stat_base": "atk + in::atk_pct * 10", "multiplier": "100"},
                        role="火神"))
        # atk=1000（面板），in::atk_pct=40 → 1000 + 400 = 1400
        self.assertEqual(g.evaluate()["nodes"]["b"]["values"]["noncrit"], 1400)

    def test_usable_inside_variable_definitions(self):
        """变量卡片的定义也能引用（第二轮解析时子命名空间已注入）。"""
        g = self.build()
        g.add(var_card("vc", "总攻击 = atk + in::atk_pct", role="火神"))
        g.add(GraphNode("c1", "calc", fields={"expr": "总攻击"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 1040)


class TestDeferredDefinitions(unittest.TestCase):
    """引用了 `in::`/`own::` 的定义要能生效（这些名字要等拐力算完才存在）。

    修复的 bug：变量卡片与角色面板都在拐力之前解析，早先算不出来就**静默丢掉** ——
    表现是"写了 `in::` 的面板项莫名不生效，下游报未定义变量"。
    """

    def test_in_resolves_without_any_buff(self):
        """没有拐力时 `in::atk_pct` 就是 0（而不是"未定义"）。"""
        g = Graph()
        g.add(GraphNode("rb", "role",
                        fields={"role_name": "火神", "panel": "atk = 1000\natk_pct = in::atk_pct"}))
        g.add(GraphNode("b", "base",
                        fields={"stat_base": "", "stat_big": "", "multiplier": "100"},
                        role="火神"))
        # atk=1000、atk_pct=0 → 1000×1.0
        self.assertEqual(g.evaluate()["nodes"]["b"]["values"]["noncrit"], 1000)

    def test_in_resolves_in_panel_and_var_card_alike(self):
        """同样的写法在面板与变量卡里结果一致（都要能解析）。

        新口径（用户：own:: 不论如何不计入 in:: 的拐）：面板/变量卡写
        ``X = in::X`` 只是"我的 X 等于收进来的那份"，**不等于自己声明了 X**；
        所以 own::X 仍是 0（"自己写的值"只有普通定义 `X = 数值` 才算）。
        """
        for where in ("panel", "var"):
            g = Graph()
            g.add(GraphNode("ra", "role", fields={"role_name": "辅助", "panel": "out::atk_pct = 40"}))
            if where == "panel":
                g.add(GraphNode("rb", "role", fields={
                    "role_name": "火神", "panel": "atk = 1000\natk_pct = in::atk_pct"}))
            else:
                g.add(GraphNode("rb", "role", fields={"role_name": "火神", "panel": "atk = 1000"}))
                g.add(var_card("vb", "atk_pct = in::atk_pct", role="火神"))
            g.links.append(Link("ra", "rb", 0))
            g.add(GraphNode("c1", "calc", fields={"expr": "own::atk_pct"}, role="火神"))
            g.add(GraphNode("c2", "calc", fields={"expr": "atk_pct"}, role="火神"))
            out = g.evaluate()
            # 生效值 = 收进来的 40；自身值仍是 0（没写普通定义）
            self.assertEqual(out["nodes"]["c2"]["values"]["noncrit"], 40, where)
            self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 0, where)

    def test_panel_items_can_reference_each_other(self):
        """角色面板里的项可以引用同一角色卡上先写的项（原来角色卡自己没作用域，引用不到）。"""
        g = Graph()
        g.add(GraphNode("rb", "role", fields={
            "role_name": "火神", "panel": "atk = 2000\natk_pct = 10\natk_flat = atk*0.05"}))
        g.add(GraphNode("b", "base",
                        fields={"stat_base": "", "stat_big": "", "stat_flat": "",
                                "multiplier": "100"},
                        role="火神"))
        # (2000×1.1 + 100) × 100% = 2300
        self.assertEqual(g.evaluate()["nodes"]["b"]["values"]["noncrit"], 2300)

    def test_var_card_can_reference_panel_macro(self):
        g = Graph()
        g.add(GraphNode("rb", "role", fields={"role_name": "火神", "panel": "atk = 1000"}))
        g.add(var_card("vb", "小攻击 = atk*0.1", role="火神"))
        g.add(GraphNode("c1", "calc", fields={"expr": "小攻击"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 100)

    def test_unresolvable_definition_is_not_kept_forever(self):
        """真算不出来的定义仍然只是"不定义"，不能把求值搞崩。"""
        g = Graph()
        g.add(GraphNode("rb", "role",
                        fields={"role_name": "火神", "panel": "atk_pct = 根本没这个变量"}))
        g.add(GraphNode("c1", "calc", fields={"expr": "atk_pct"}, role="火神"))
        out = g.evaluate()
        self.assertIn("未定义变量", out["nodes"]["c1"]["display"])
        # 第二次求值也不受第一次延迟列表影响
        self.assertIn("未定义变量", g.evaluate()["nodes"]["c1"]["display"])


class TestOutDeclarations(unittest.TestCase):
    """显式声明"对外提供的值"：``out::X = 值``（角标：拐力箭头用它，默认才 = 自身）。

    用户实战场景（面板外拐）：b 只写 ``out::atk_pct = 40``，拖箭头 b→a，
    a 什么都不用写 —— a 的 ``atk_pct`` 本身就是 40。
    """

    def build(self, b_defs="out::atk_pct = 40", with_a_def=False):
        g = Graph()
        g.add(GraphNode("rb", "role", fields={"role_name": "b"}))
        g.add(var_card("vb", b_defs, role="b"))
        g.add(GraphNode("ra", "role", fields={"role_name": "a"}))
        if with_a_def:
            g.add(var_card("va", "atk_pct = in::atk_pct", role="a"))
        g.add(GraphNode("base", "attr",
                        fields={"stat_base": "1000", "stat_big": "atk_pct", "stat_flat": "0"},
                        role="a"))
        g.links.append(Link("rb", "ra", 0))
        return g

    def test_out_declaration_grants(self):
        """b 声明 out::atk_pct = 40，箭头 b→a；a 写一行预设代码即可用上。"""
        g = self.build()
        g.add(var_card("va2", "atk_pct = own::atk_pct + in::atk_pct", role="a"))
        # 属性源的大增益% 写 atk_pct → 1000×(1+0.40) = 1400
        self.assertEqual(g.evaluate()["nodes"]["base"]["values"]["noncrit"], 1400)
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="a"))
        g.add(GraphNode("x", "calc", fields={"expr": "atk_pct"}, role="a"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 40)   # 收进来的
        self.assertEqual(out["nodes"]["x"]["values"]["noncrit"], 40)    # 生效值（自身 0 + 40）

    def test_out_user_definition_is_not_overwritten(self):
        """回归：以前 out:: 是派生键，用户写 40 会被覆盖成 0。"""
        g = self.build()
        names = {(v["name"], v["text"]) for v in g.evaluate()["variables"]}
        self.assertIn(("b::atk_pct", "40"), names)      # 没另外定义自身 → 同时作为自身值

    def test_out_can_differ_from_own(self):
        """显式 out:: 与自身值可以不同：自己面板 10、对外提供 40。"""
        g = self.build(b_defs="atk_pct = 10\nout::atk_pct = 40")
        g.add(GraphNode("c1", "calc", fields={"expr": "own::atk_pct"}, role="b"))
        g.add(GraphNode("c2", "calc", fields={"expr": "out::atk_pct"}, role="b"))
        g.add(GraphNode("c3", "calc", fields={"expr": "in::atk_pct"}, role="a"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 10)     # 自身
        self.assertEqual(out["nodes"]["c2"]["values"]["noncrit"], 40)     # 对外
        self.assertEqual(out["nodes"]["c3"]["values"]["noncrit"], 40)     # 收进来的就是 out

    def test_in_declaration_is_ignored(self):
        """in:: 是"收进来的"，由拐力派生；用户写它不生效。"""
        g = self.build()
        g.add(var_card("vx", "in::atk_pct = 999", role="a"))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="a"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)

class TestExternalDomain(unittest.TestCase):
    """「外部域」卡片：跨文件读取另一个工程里某个域声明过的 out::（当拐力来源）。"""

    def setUp(self):
        from genshin_dmg import external as ext

        self.ext = ext
        ext.clear_cache()                    # 每个用例从干净的缓存开始
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write_project(self, name, build):
        """把 build() 造出的图存成一个工程文件，返回路径。"""
        g = Graph()
        build(g)
        path = self.dir / name
        path.write_text(json.dumps(g.to_dict(), ensure_ascii=False), encoding="utf-8")
        return path

    def build_consumer(self, file_path, ext_role="胡桃", source_id="x1"):
        g = Graph()
        g.add(GraphNode(source_id, "external",
                        fields={"ext_file": str(file_path), "ext_role": ext_role}))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神"}))
        g.links.append(Link(source_id, "rb", 0))
        return g

    def test_reads_out_from_another_file(self):
        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))
            # 变量卡里也能声明（显式带角色前缀，这样不依赖"卡片落在区域里"的几何判定）
            g.add(var_card("va", "胡桃::out::dmg = 30"))

        path = self.write_project("donor.json", build)
        g = self.build_consumer(path)
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        g.add(GraphNode("c2", "calc", fields={"expr": "in::dmg"}, role="火神"))
        out = g.evaluate()["nodes"]
        self.assertEqual(out["c1"]["values"]["noncrit"], 40)
        self.assertEqual(out["c2"]["values"]["noncrit"], 30)

    def test_card_output_is_the_sum(self):
        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))
            g.add(var_card("va", "胡桃::out::dmg = 30"))

        path = self.write_project("donor.json", build)
        g = self.build_consumer(path)
        g.add(GraphNode("cx", "external",
                        fields={"ext_file": str(path), "ext_role": "胡桃"}))
        out = g.evaluate()["nodes"]
        self.assertEqual(out["x1"]["values"]["noncrit"], 70)     # 40 + 30，一眼看出读到没

    def test_relative_path_uses_project_dir(self):
        """相对路径按**当前工程所在目录**解析；不带扩展名时自动补 .json（用户要求）。"""
        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))

        self.write_project("dds.json", build)
        for filled in ("dds.json", "dds"):
            g = self.build_consumer(filled)
            g.base_dir = str(self.dir)          # 相当于前端在载荷里带的 dir
            g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
            self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40, filled)

    def test_single_domain_needs_no_name(self):
        """文件里只有一个域时，「里面的域」留空也读得到（前端会把那一栏藏掉）。"""
        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))

        self.write_project("dds.json", build)
        g = self.build_consumer("dds.json", ext_role="")
        g.base_dir = str(self.dir)
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 40)
        # 域名列表也带给前端，好让它藏掉那一栏
        self.assertEqual(out["nodes"]["x1"]["extDomains"], ["胡桃"])

    def test_two_domains_need_a_name(self):
        """有两个域时留空不猜（免得读错人的拐力）。"""
        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))
            g.add(GraphNode("rb", "role", fields={"role_name": "雷神",
                                                  "panel": "out::atk_pct = 70"}))

        self.write_project("two.json", build)
        g = self.build_consumer("two.json", ext_role="")
        g.base_dir = str(self.dir)
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 0)
        self.assertEqual(sorted(out["nodes"]["x1"]["extDomains"]), ["胡桃", "雷神"])

    def test_relative_path_tries_parent(self):
        """相对路径会试「工程目录 / 它的上一级」；**子目录不猜**（用户口径：有歧义）。"""
        sub = self.dir / "data"
        sub.mkdir()

        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))

        self.write_project("data/幻灭.json", build)

        cases = [
            (str(sub), "幻灭", 40),                # 工程就在 data/ 里，直接命中
            (str(sub), "data/幻灭", 40),           # 多写了一层 → 靠上一级兜
            (str(self.dir), "data/幻灭.json", 40), # 工程在上层，路径写全
            (str(self.dir), "幻灭", 0),            # 只写文件名：不替你去 data/ 里猜
        ]
        for base, filled, want in cases:
            g = self.build_consumer(filled)
            g.base_dir = base
            g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
            self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], want,
                             "%s / %s" % (base, filled))

    def test_extra_bases_from_server(self):
        """服务端补的「上次打开/保存的目录」也会被试（工程目录不对时兜底）。"""
        def build(g):
            g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))
        self.write_project("幻灭.json", build)
        g = self.build_consumer("幻灭")            # 只写文件名
        g.base_dir = str(self.dir / "别处")         # 工程目录里没有
        g.extra_bases = [str(self.dir)]            # 记住的目录里才有
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)

    def test_multi_line_sources(self):
        """一张卡写多行 `文件::域`：多来源分别读，同名求和；面板里显示 文件名.域名。"""
        def build(name, role, panel):
            def make(g):
                g.add(GraphNode("r1", "role", fields={"role_name": role,
                                                      "panel": panel}))
            return self.write_project(name, make)

        a = build("幻灭米提亚.json", "dds", "out::atk_pct = 18")
        b = build("胡桃.json", "胡桃", "out::atk_pct = 30\nout::em = 100")

        g = Graph()
        g.add(GraphNode("x1", "external", fields={
            "ext_sources": "%s::dds\n%s::胡桃" % (a, b)}))
        g.add(GraphNode("r1", "role", fields={"role_name": "火神"}))
        g.links.append(Link("x1", "r1", 0))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        g.add(GraphNode("c2", "calc", fields={"expr": "in::em"}, role="火神"))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 48)   # 18 + 30
        self.assertEqual(out["nodes"]["c2"]["values"]["noncrit"], 100)
        # 面板弹窗的 IN 明细：来源名字是 文件名.域名（用户要求）
        rows = {(r["macro"], r["value"], r["role"]) for r in out["buffStats"]["火神"]["in"]}
        self.assertIn(("atk_pct", 18.0, "幻灭米提亚.dds"), rows)
        self.assertIn(("atk_pct", 30.0, "胡桃.胡桃"), rows)
        self.assertIn(("em", 100.0, "胡桃.胡桃"), rows)

    def test_line_without_domain_uses_the_only_one(self):
        def make(g):
            g.add(GraphNode("r1", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))
        path = self.write_project("dds.json", make)
        g = Graph()
        g.add(GraphNode("x1", "external", fields={"ext_sources": str(path)}))
        g.add(GraphNode("r1", "role", fields={"role_name": "火神"}))
        g.links.append(Link("x1", "r1", 0))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)

    def test_legacy_single_file_fields_still_work(self):
        """老工程只有 ext_file / ext_role：照样读（新字段为空时退回它们）。"""
        def make(g):
            g.add(GraphNode("r1", "role", fields={"role_name": "胡桃",
                                                  "panel": "out::atk_pct = 40"}))
        path = self.write_project("dds.json", make)
        g = Graph()
        g.add(GraphNode("x1", "external",
                        fields={"ext_file": str(path), "ext_role": "胡桃"}))
        g.add(GraphNode("r1", "role", fields={"role_name": "火神"}))
        g.links.append(Link("x1", "r1", 0))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)

    def test_parse_sources_format(self):
        """一行一个 `文件::域`；只认 ::；空行和 # 注释跳过。"""
        parse = self.ext.parse_sources
        self.assertEqual(parse("a.json::dds\nb.json::胡桃"), [("a.json", "dds"), ("b.json", "胡桃")])
        self.assertEqual(parse("  a.json  ::  dds  "), [("a.json", "dds")])
        self.assertEqual(parse("a.json"), [("a.json", "")])
        self.assertEqual(parse("\n\n# 注释\na.json::x\n"), [("a.json", "x")])
        # 新字段为空 → 退回老的两个字段
        self.assertEqual(parse("", "old.json", "老域"), [("old.json", "老域")])
        self.assertEqual(parse("", "", ""), [])
        # 需要名字时：文件名（去扩展名）+ 域名
        self.assertEqual(self.ext.source_label("D:/x/幻灭米提亚.json", "dds"), "幻灭米提亚.dds")
        self.assertEqual(self.ext.source_label("D:/x/a.json", ""), "a")

    def test_missing_file_and_unknown_role_give_zero(self):
        path = self.write_project("donor.json", lambda g: g.add(
            GraphNode("ra", "role", fields={"role_name": "胡桃",
                                            "panel": "out::atk_pct = 40"})))
        for target, role in ((self.dir / "没有这个文件.json", "胡桃"), (path, "不存在")):
            g = self.build_consumer(target, ext_role=role)
            g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
            self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 0)

    def test_plain_panel_items_are_not_granted(self):
        """只有 out:: 才给出去，普通面板项读不到（和文件内规则一致）。"""
        path = self.write_project("donor.json", lambda g: g.add(
            GraphNode("ra", "role", fields={"role_name": "胡桃", "panel": "atk_pct = 40"})))
        g = self.build_consumer(path)
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 0)

    def test_cycle_still_evaluates_own_out(self):
        """文件互相引用时**只切断再往下读**：被引用文件自己的 out:: 照常求值，不是 0。

        用户口径：即使文件间成环，out 的求值字段本身没循环，就该正常算。
        """
        a_path = self.dir / "a.json"
        b_path = self.dir / "b.json"

        def donor(g, role, out, other):
            g.add(GraphNode("r1", "role", fields={"role_name": role,
                                                 "panel": "out::atk_pct = %s" % out}))
            g.add(GraphNode("x1", "external",
                            fields={"ext_file": str(other), "ext_role": ""}))
            g.links.append(Link("x1", "r1", 0))

        ga = Graph()
        donor(ga, "胡桃", 40, b_path)                    # A: out::atk_pct = 40，指向 B
        a_path.write_text(json.dumps(ga.to_dict(), ensure_ascii=False), encoding="utf-8")
        gb = Graph()
        donor(gb, "雷神", 70, a_path)                    # B: out::atk_pct = 70，指回 A
        b_path.write_text(json.dumps(gb.to_dict(), ensure_ascii=False), encoding="utf-8")

        # 各自都读得到自己的 40 / 70（不会因为环变成 0）
        self.assertEqual(self.ext.out_values(str(a_path), "胡桃"), {"atk_pct": 40.0})
        self.assertEqual(self.ext.out_values(str(b_path), "雷神"), {"atk_pct": 70.0})
        # 再读一遍：被切断的那次结果不能进缓存（否则会永久读成 0）
        self.assertEqual(self.ext.out_values(str(a_path), "胡桃"), {"atk_pct": 40.0})
        self.assertEqual(self.ext.out_values(str(b_path), "雷神"), {"atk_pct": 70.0})

        # 实际用到它的工程也能拿到 40（不卡死、不报错）
        consumer = self.build_consumer(a_path, ext_role="胡桃")
        consumer.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        self.assertEqual(consumer.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)

    def test_cycle_is_reported_to_frontend(self):
        """环要能被记录到（后端据此在界面底部提示），且提示里带上文件名。"""
        self.ext.begin()
        a_path = self.dir / "a.json"
        b_path = self.dir / "b.json"

        def donor(g, role, out, other):
            g.add(GraphNode("r1", "role", fields={"role_name": role,
                                                 "panel": "out::atk_pct = %s" % out}))
            g.add(GraphNode("x1", "external",
                            fields={"ext_file": str(other), "ext_role": ""}))
            g.links.append(Link("x1", "r1", 0))

        ga = Graph()
        donor(ga, "胡桃", 40, b_path)
        a_path.write_text(json.dumps(ga.to_dict(), ensure_ascii=False), encoding="utf-8")
        gb = Graph()
        donor(gb, "雷神", 70, a_path)
        b_path.write_text(json.dumps(gb.to_dict(), ensure_ascii=False), encoding="utf-8")

        self.assertEqual(self.ext.out_values(str(a_path), "胡桃"), {"atk_pct": 40.0})
        cycles = self.ext.take_cycles()
        self.assertTrue(cycles, "成环时应该记录下来，好让界面提示")
        reentered, reader = cycles[0]
        self.assertEqual(os.path.basename(reentered), "a.json")
        self.assertEqual(os.path.basename(reader), "b.json")
        # take_cycles 取完就清空（不会把上一次的环重复报出来）
        self.assertEqual(self.ext.take_cycles(), [])

    def test_no_cycle_no_warning(self):
        """没环就什么都不报（别为正常情况弹提示）。"""
        self.ext.begin()
        self.write_project("donor.json", lambda g: g.add(
            GraphNode("r", "role", fields={"role_name": "胡桃",
                                           "panel": "out::atk_pct = 40"})))
        self.assertEqual(self.ext.out_values("donor.json", "", str(self.dir)),
                         {"atk_pct": 40.0})
        self.assertEqual(self.ext.take_cycles(), [])

    def test_cache_follows_file_changes(self):
        """改了被引用的文件要能读到新值（按 mtime 失效，不是永久缓存）。"""
        path = self.dir / "donor.json"
        path.write_text(json.dumps(Graph().to_dict()), encoding="utf-8")
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                              "panel": "out::atk_pct = 40"}))
        path.write_text(json.dumps(g.to_dict(), ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.ext.out_values(str(path), "胡桃"), {"atk_pct": 40.0})
        # 改内容（并把 mtime 往后挪，避免同秒写入看起来没变）
        g2 = Graph()
        g2.add(GraphNode("ra", "role", fields={"role_name": "胡桃",
                                               "panel": "out::atk_pct = 55"}))
        path.write_text(json.dumps(g2.to_dict(), ensure_ascii=False), encoding="utf-8")
        stamp = os.stat(path).st_mtime + 5
        os.utime(path, (stamp, stamp))
        self.assertEqual(self.ext.out_values(str(path), "胡桃"), {"atk_pct": 55.0})


class TestOutSum(unittest.TestCase):
    """同一个域里同名 out:: 写多处要**求和**（用户口径）。

    场景：一个角色域里两张变量卡都写 out::atk = 5，对面收到的 in::atk 应该是 10。
    """

    def build(self):
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助"}))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神"}))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk"}, role="火神"))
        g.add(GraphNode("c2", "calc", fields={"expr": "out::atk"}, role="辅助"))
        g.add(GraphNode("c3", "calc", fields={"expr": "atk"}, role="辅助"))
        g.links.append(Link("ra", "rb", 0))
        return g

    def read(self, g):
        out = g.evaluate()["nodes"]
        return (out["c1"]["values"]["noncrit"], out["c2"]["values"]["noncrit"],
                out["c3"]["values"]["noncrit"])

    def test_two_cards_same_name_sum(self):
        g = self.build()
        g.add(var_card("v1", "out::atk = 5", role="辅助"))
        g.add(var_card("v2", "out::atk = 5", role="辅助"))
        # 对面收到 10；本角色的 out:: 也是 10；普通名（没单独定义）跟着是 10
        self.assertEqual(self.read(g), (10, 10, 10))

    def test_single_card_is_not_double_counted(self):
        """回归：变量卡本来会解析两轮，逐条贡献要按"哪张卡第几行"记账，不能翻倍。"""
        g = self.build()
        g.add(var_card("v1", "out::atk = 5", role="辅助"))
        self.assertEqual(self.read(g), (5, 5, 5))

    def test_two_lines_in_one_card_sum(self):
        g = self.build()
        g.add(var_card("v1", "out::atk = 5\nout::atk = 3", role="辅助"))
        self.assertEqual(self.read(g), (8, 8, 8))

    def test_card_plus_panel_sum(self):
        g = self.build()
        g.add(var_card("v1", "out::atk = 5", role="辅助"))
        g.add(GraphNode("rp", "role", fields={"role_name": "辅助", "panel": "out::atk = 7"}))
        self.assertEqual(self.read(g), (12, 12, 12))

    def test_real_definition_still_wins_for_plain_name(self):
        """普通名有真定义时不被 out 合计顶掉（自身值仍是自己写的那个）。"""
        g = self.build()
        g.add(var_card("v1", "atk = 100\nout::atk = 5", role="辅助"))
        g.add(var_card("v2", "out::atk = 5", role="辅助"))
        self.assertEqual(self.read(g), (10, 10, 100))

    def test_different_names_stay_separate(self):
        g = self.build()
        g.add(var_card("v1", "out::atk = 5\nout::dmg = 30", role="辅助"))
        g.add(GraphNode("c4", "calc", fields={"expr": "in::dmg"}, role="火神"))
        out = g.evaluate()["nodes"]
        self.assertEqual(out["c1"]["values"]["noncrit"], 5)    # in::atk
        self.assertEqual(out["c4"]["values"]["noncrit"], 30)   # in::dmg
        # OUT 统计里两个名字各一条，不会合并成一个数
        stats = g.evaluate()["buffStats"]["辅助"]["out"]
        self.assertEqual(sorted((r["macro"], r["value"]) for r in stats),
                         [("atk", 5), ("dmg", 30)])


class TestCustomOutNames(unittest.TestCase):
    """out:: 后面可以是**任意名字**（不限于面板宏），对面用 in::那个名字 收到。"""
    def test_custom_out_name_is_granted(self):
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助"}))
        g.add(var_card("va", "out::拐力A = 20", role="辅助"))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神"}))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::拐力A"}, role="火神"))
        g.add(GraphNode("t", "vartable"))
        g.links.append(Link("ra", "rb", 0))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 20)
        # 自定义名字也要进「角色面板」弹窗的 OUT / IN 统计
        self.assertEqual([r["macro"] for r in out["buffStats"]["辅助"]["out"]], ["拐力A"])
        self.assertEqual([r["macro"] for r in out["buffStats"]["火神"]["in"]], ["拐力A"])
        # 面板属性不自动计算：目标自己写一行（预设代码的形状）才用得上
        g.add(var_card("vb", "拐力A = own::拐力A + in::拐力A", role="火神"))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 20)


class TestNoAutoPanelValue(unittest.TestCase):
    """面板属性**不自动计算**：不写定义就没有该值；写了定义（预设代码的形状）才有。"""

    def test_undefined_without_definition(self):
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助"}))
        g.add(var_card("va", "out::atk_pct = 40", role="辅助"))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神"}))
        g.add(GraphNode("c1", "calc", fields={"expr": "atk_pct"}, role="火神"))
        g.add(GraphNode("c2", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        g.links.append(Link("ra", "rb", 0))
        out = g.evaluate()
        self.assertIn("未定义变量", out["nodes"]["c1"]["display"])   # 没定义就没有
        self.assertEqual(out["nodes"]["c2"]["values"]["noncrit"], 40)  # 拐力仍在 in:: 里

    def test_preset_code_makes_it_work(self):
        """把预设代码（X = own::X + in::X）填进变量卡后就正常了。"""
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助"}))
        g.add(var_card("va", "out::atk_pct = 40", role="辅助"))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神"}))
        g.add(var_card("vb", "atk_pct = own::atk_pct + in::atk_pct", role="火神"))
        g.add(GraphNode("c1", "calc", fields={"expr": "atk_pct"}, role="火神"))
        g.links.append(Link("ra", "rb", 0))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)

    def test_own_value_still_wins_with_preset(self):
        """预设代码里 own:: + in:: 会把自身和拐力加起来（这才是"叠加"的写法）。"""
        g = Graph()
        g.add(GraphNode("ra", "role", fields={"role_name": "辅助"}))
        g.add(var_card("va", "out::atk_pct = 40", role="辅助"))
        g.add(GraphNode("rb", "role", fields={"role_name": "火神"}))
        g.add(var_card("vb", "atk_pct = 10\natk_pct = own::atk_pct + in::atk_pct", role="火神"))
        g.add(GraphNode("c1", "calc", fields={"expr": "in::atk_pct"}, role="火神"))
        g.links.append(Link("ra", "rb", 0))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 40)


class TestWeaponNamespace(unittest.TestCase):
    """武器：继承角色类的命名空间容器 —— 只输出拐力、无面板、不支持 in::。"""

    def build(self, link=True):
        g = Graph()
        g.add(GraphNode("rw", "weapon", fields={"role_name": "武器A"}))
        g.add(var_card("vw", "out::atk_pct = 40", role="武器A"))
        g.add(GraphNode("rr", "role", fields={"role_name": "火神"}))
        g.add(var_card("vr", "atk_pct = own::atk_pct + in::atk_pct", role="火神"))
        g.add(GraphNode("c1", "calc", fields={"expr": "atk_pct"}, role="火神"))
        if link:
            g.links.append(Link("rw", "rr", 0))
        return g

    def test_weapon_grants_to_role(self):
        self.assertEqual(self.g_value(self.build()), 40)

    def g_value(self, g):
        return g.evaluate()["nodes"]["c1"]["values"]["noncrit"]

    def test_weapon_has_no_in_namespace(self):
        """武器不接受拐：in:: 不存在（面板属性也不自动计算，所以要用 out:: 声明给出多少）。"""
        g = self.build()
        g.add(GraphNode("c2", "calc", fields={"expr": "in::atk_pct"}, role="武器A"))
        out = g.evaluate()
        self.assertIn("未定义变量", out["nodes"]["c2"]["display"])
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 40)   # 对外给照旧

    def test_weapon_schema(self):
        sch = nd.node_schema("weapon")
        self.assertTrue(sch["weapon_card"])
        self.assertTrue(sch["role_card"])          # 继承角色类
        self.assertEqual(sch["fields"], [])        # 没有可见字段（名字走右键设置）
        self.assertNotIn("panel_show", sch["hidden_fields"])   # 没有面板
        self.assertIn("role_name", sch["hidden_fields"])

    def test_weapon_variables_are_namespaced(self):
        """武器区域里的变量按 武器名::变量 命名（与角色同一套机制）。"""
        g = self.build()
        g.add(var_card("vw2", "白值 = 500", role="武器A"))
        g.add(GraphNode("c3", "calc", fields={"expr": "白值"}, role="武器A"))
        g.add(GraphNode("c4", "calc", fields={"expr": "武器A::白值"}, role=""))
        out = g.evaluate()
        self.assertEqual(out["nodes"]["c3"]["values"]["noncrit"], 500)
        self.assertEqual(out["nodes"]["c4"]["values"]["noncrit"], 500)


class TestRoleNameValidation(unittest.TestCase):
    def test_bad_role_is_treated_as_global(self):
        for bad in ("", "  ", "有 空格", "a__b", "雷神::x", "1abc"):
            node = GraphNode("v1", "var", fields={"defs": "攻击力 = 1"}, role=bad)
            self.assertEqual(node.role, "", bad)
            self.assertEqual(node.fields["defs"], "攻击力 = 1")

    def test_role_is_persisted_and_inferred_for_old_files(self):
        """归属写进工程 JSON；老文件没这个键时按几何位置补（跨文件读拐力要靠它）。

        以前不存 role（前端每次按位置重算），导致后端单独读一个工程文件时不知道
        域内卡片归谁 —— 域内变量卡写的 out:: 会落到全局，跨文件就什么都读不到。
        """
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "攻击力 = 1"}, role="雷神"))
        self.assertEqual(g.to_dict()["nodes"][0]["role"], "雷神")

        # 老文件：没有 role 键 → 按"卡片中心落在域框内、小区域优先"补
        old = {
            "version": 1, "app": "GenshinDamageCalc", "zoom": 1, "name": "旧",
            "nodes": [
                {"id": "w1", "type": "weapon", "pos": [0, 0], "size": [400, 300],
                 "fields": {"role_name": "dds"}, "inputs": 0},
                {"id": "v1", "type": "var", "pos": [20, 20], "size": [200, 120],
                 "fields": {"defs": "out::atk = 5"}, "inputs": 0},
                {"id": "v2", "type": "var", "pos": [2000, 2000], "size": [200, 120],
                 "fields": {"defs": "x = 1"}, "inputs": 0},
            ],
            "links": [],
        }
        restored = Graph.from_dict(old)
        self.assertEqual(restored.nodes["v1"].role, "dds")
        self.assertEqual(restored.nodes["v2"].role, "")      # 域外的不瞎认


class TestBackwardCompat(unittest.TestCase):
    """无前缀 = 全局：没写角色的卡片行为与从前完全一致。"""

    def test_plain_variables_still_work(self):
        g = Graph()
        g.add(var_card("v1", "攻击力 = 1000\n倍率 = 200"))
        g.add(GraphNode("c1", "calc", fields={"expr": "攻击力 * 倍率"}))
        self.assertEqual(g.evaluate()["nodes"]["c1"]["values"]["noncrit"], 200000)

    def test_role_card_itself_is_harmless(self):
        """容器卡片本身没有端口、不参与计算，出现它不该影响求值。"""
        g = Graph()
        g.add(GraphNode("role", "role", fields={"role_name": "雷神"}))
        g.add(var_card("v1", "攻击力 = 1000", role="雷神"))
        g.add(GraphNode("c1", "calc", fields={"expr": "攻击力"}, role="雷神"))
        out = g.evaluate()

        self.assertIsNone(out["nodes"]["role"]["values"])
        self.assertEqual(out["nodes"]["c1"]["values"]["noncrit"], 1000)


if __name__ == "__main__":
    unittest.main()

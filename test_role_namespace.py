# -*- coding: utf-8 -*-
"""角色命名空间（``角色::变量``）的作用域测试。

用户确认的口径：
* 分隔符 ``::``；**无前缀 = 全局**（向后兼容）
* 角色容器里的卡片：变量卡片 / ★结果三元组 / 赋值变量卡登记的名字都自动带角色前缀
* 读变量时**先本角色、再全局**（就近解析）；显式写 ``胡桃::攻击力`` 在任何地方都取得到
* 名字里禁止 ``__``（保留给内部拼接），变量表对外显示 ``角色::变量``

运行：``python -m pytest test_role_namespace.py -q``
"""

import unittest

from genshin_dmg import nodes as nd
from genshin_dmg.expr import demangle, env_key, mangle, qualify, valid_var_name
from genshin_dmg.graph import Graph, GraphNode


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
        for bad in ("", "  ", "a__b", "雷神::a__b", "雷神::", "::攻击力",
                    "1abc", "a b", "a-b", "雷神::攻击力::x"):
            self.assertEqual(valid_var_name(bad), "", bad)

    def test_qualify(self):
        self.assertEqual(qualify("攻击力", "雷神"), "雷神::攻击力")
        self.assertEqual(qualify("攻击力", ""), "攻击力")
        # 已经写了前缀就不再套一层
        self.assertEqual(qualify("胡桃::攻击力", "雷神"), "胡桃::攻击力")


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


class TestRoleNameValidation(unittest.TestCase):
    def test_bad_role_is_treated_as_global(self):
        for bad in ("", "  ", "有 空格", "a__b", "雷神::x", "1abc"):
            node = GraphNode("v1", "var", fields={"defs": "攻击力 = 1"}, role=bad)
            self.assertEqual(node.role, "", bad)
            self.assertEqual(node.fields["defs"], "攻击力 = 1")

    def test_role_is_not_persisted_in_project_json(self):
        """工程 JSON 不存归属（位置能重算）；但求值回传里带着，便于前端显示。"""
        g = Graph()
        g.add(GraphNode("v1", "var", fields={"defs": "攻击力 = 1"}, role="雷神"))
        self.assertNotIn("role", g.to_dict()["nodes"][0])


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

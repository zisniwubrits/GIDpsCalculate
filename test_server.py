# -*- coding: utf-8 -*-
"""Web 后端（FastAPI）与报告模块的测试。

用 ``fastapi.testclient``（基于 httpx）直接打接口，不需要真的起服务。

运行：``pytest test_server.py -q`` 或 ``python -m unittest test_server``
"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fastapi.testclient import TestClient

from genshin_dmg import nodes as nd
from genshin_dmg import report, tutorial
from genshin_dmg.graph import Graph, GraphNode
from server import dialogs, storage
from server.app import create_app

client = TestClient(create_app())


def sample_graph(with_crit=True, name="测试工程"):
    """base(1000×200%=2000) [→ crit] → result 的工程 JSON。"""
    g = Graph(name=name)
    g.add(GraphNode("n1", "base", pos=(40, 60), fields={
        "stat_base": "1000", "multiplier": "200"}))
    src = "n1"
    if with_crit:
        g.add(GraphNode("n2", "crit", pos=(380, 60)))
        g.connect("n1", "n2")
        src = "n2"
    g.add(GraphNode("n3", "result", pos=(720, 60)))
    g.connect(src, "n3")
    return g.to_dict()


class StorageIsolated(unittest.TestCase):
    """把工程目录与配置文件重定向到临时目录。

    凡是会**写文件**的接口测试都必须继承它 —— 否则测试会往工作区的
    private/projects/ 里扔真实文件（早期真发生过一次）。
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_dir = storage.DEFAULT_DIR
        self._old_cfg = storage.CONFIG_PATH
        storage.DEFAULT_DIR = self.root / "projects"
        storage.CONFIG_PATH = self.root / "save_config.json"
        self.addCleanup(self._restore)

    def _restore(self):
        storage.DEFAULT_DIR = self._old_dir
        storage.CONFIG_PATH = self._old_cfg
        self._tmp.cleanup()

    def stub_dialog(self, path):
        """把原生打开对话框换成返回固定路径（测试里绝不真的弹窗）。"""
        patcher = mock.patch.object(dialogs, "pick_open_file", lambda *a, **k: path)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestApiBasics(unittest.TestCase):
    def test_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn("version", body)
        self.assertIn("webBuilt", body)

    def test_schema_endpoint(self):
        r = client.get("/api/schema")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body["nodeTypes"]), set(nd.NODE_TYPES))
        self.assertTrue(body["groups"])
        self.assertTrue(body["presets"])
        self.assertIn("relic", body["tables"])

    def test_schema_has_chinese_and_is_utf8(self):
        r = client.get("/api/schema")
        self.assertIn("暴击区", r.text)
        self.assertIn("application/json", r.headers["content-type"])

    def test_help_endpoint(self):
        r = client.get("/api/help")
        self.assertEqual(r.status_code, 200)
        self.assertIn("【基本概念】", r.json()["text"])
        self.assertEqual(r.json()["sections"][0], "基本概念")

    def test_root_page_without_build(self):
        """没有 web/dist 时给出可读的后端就绪提示页。"""
        if os.path.isfile(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "web", "dist", "index.html")):
            self.skipTest("已构建前端，跳过占位页断言")
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("后端已启动", r.text)

    def test_unknown_api_path_is_404_json(self):
        r = client.get("/api/不存在")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()["ok"])


class TestEvaluateEndpoint(unittest.TestCase):
    def test_evaluate_ok(self):
        r = client.post("/api/evaluate", json=sample_graph())
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertAlmostEqual(body["result"]["values"]["noncrit"], 2000.0)
        self.assertAlmostEqual(body["result"]["values"]["crit"], 4000.0)
        self.assertAlmostEqual(body["result"]["values"]["expected"], 3000.0)
        self.assertEqual(set(body["nodes"]), {"n1", "n2", "n3"})
        self.assertIn("未暴击", body["nodes"]["n3"]["display"])

    def test_evaluate_returns_plain_numbers_for_copy(self):
        """每个节点都给出纯数字字符串（无千分位、无科学计数法），供前端复制。"""
        data = sample_graph()
        data["nodes"][0]["fields"]["stat_base"] = "1234.5"
        body = client.post("/api/evaluate", json=data).json()
        n3 = body["nodes"]["n3"]

        self.assertEqual(n3["plain"], "2469")
        self.assertEqual(len(n3["plainTriple"]), 3)
        self.assertTrue(all("e" not in s.lower() for s in n3["plainTriple"]))
        self.assertEqual(body["nodes"]["n1"]["plain"], "2469")

    def test_evaluate_returns_normalized_graph(self):
        data = sample_graph()
        data["nodes"][0]["fields"]["stat_base"] = "500+500"
        body = client.post("/api/evaluate", json=data).json()

        self.assertAlmostEqual(body["result"]["values"]["noncrit"], 2000.0)
        self.assertEqual(body["graph"]["nodes"][0]["fields"]["stat_base"], "500+500")
        self.assertEqual(body["graph"]["app"], "GenshinDamageCalc")

    def test_evaluate_variables_and_var_table(self):
        data = sample_graph()
        data["nodes"].append(dict(id="v1", type="var", pos=[40, 400], fields={
            "defs": "时间 = 20\n秒伤 = 期望伤害/时间"}))
        data["nodes"].append(dict(id="t1", type="vartable", pos=[400, 400], fields={}))
        result = next(n for n in data["nodes"] if n["type"] == "result")
        result["fields"]["var_ex"] = "期望伤害"
        body = client.post("/api/evaluate", json=data).json()

        env = {v["name"]: v["value"] for v in body["variables"]}
        self.assertAlmostEqual(env["期望伤害"], 3000.0)
        self.assertAlmostEqual(env["秒伤"], 150.0)
        rows = body["nodes"]["t1"]["rows"]
        self.assertIn(["期望伤害", "3000"], rows)
        self.assertIn(["秒伤", "150"], rows)

    def test_evaluate_without_result_card_is_not_error(self):
        data = sample_graph()
        data["nodes"] = [n for n in data["nodes"] if n["type"] != "result"]
        data["links"] = []
        r = client.post("/api/evaluate", json=data)
        body = r.json()

        self.assertEqual(r.status_code, 200)
        self.assertFalse(body["ok"])
        self.assertIn("结果", body["error"])
        self.assertTrue(body["warnings"])

    def test_evaluate_accepts_wrapped_graph(self):
        r = client.post("/api/evaluate", json={"graph": sample_graph()})
        self.assertTrue(r.json()["ok"])

    def test_bad_json_body(self):
        r = client.post("/api/evaluate", content=b"{",
                        headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])

    def test_non_object_body(self):
        r = client.post("/api/evaluate", json=[1, 2, 3])
        self.assertEqual(r.status_code, 400)

    def test_legacy_project_roundtrip_through_api(self):
        """旧版 tkinter 工程 JSON（含 size / font_size / inputs / 旧配方写法）可直接求值。"""
        legacy = dict(
            version=1, app="GenshinDamageCalc", zoom=1.25, name="旧工程",
            nodes=[
                dict(id="n1", type="base", pos=[40, 60], size=[320, 150],
                     font_size=11.5, inputs=0,
                     fields={"stat_base": "1000", "multiplier": "200"}),
                dict(id="n2", type="amp", pos=[400, 60], size=None,
                     font_size=None, inputs=1,
                     fields={"formula": "蒸发·水→火", "em": "0",
                             "amp_bonus": "0", "shield": False}),
                dict(id="n3", type="crit", pos=[760, 60], size=None,
                     font_size=None, inputs=1,
                     fields={"crit_rate": "50", "crit_damage": "100"}),
                dict(id="n4", type="result", pos=[1100, 60], size=None,
                     font_size=None, inputs=1,
                     fields={"var_nc": "", "var_cr": "", "var_ex": "期望伤害"}),
            ],
            links=[dict(src="n1", dst="n2", port=0),
                   dict(src="n2", dst="n3", port=0),
                   dict(src="n3", dst="n4", port=0)],
        )
        body = client.post("/api/evaluate", json=legacy).json()

        self.assertTrue(body["ok"])
        self.assertAlmostEqual(body["result"]["values"]["noncrit"], 4000.0)   # 2000×2.0
        self.assertAlmostEqual(body["result"]["values"]["expected"], 6000.0)  # ×(1+0.5×1)
        self.assertEqual(body["graph"]["zoom"], 1.25)
        self.assertEqual(body["graph"]["name"], "旧工程")
        self.assertEqual(body["graph"]["nodes"][0]["size"], [320.0, 150.0])
        self.assertEqual([v["name"] for v in body["variables"]], ["期望伤害"])

    def test_cycle_returns_structured_error(self):
        data = dict(nodes=[
            dict(id="a", type="dmg", pos=[0, 0], fields={"dmg_net": "10"}),
            dict(id="b", type="boost", pos=[300, 0], fields={"boost": "10"}),
            dict(id="r", type="result", pos=[600, 0], fields={}),
        ], links=[dict(src="a", dst="b", port=0), dict(src="b", dst="a", port=0),
                  dict(src="b", dst="r", port=0)])
        body = client.post("/api/evaluate", json=data).json()

        self.assertFalse(body["ok"])
        self.assertIn("环路", body["error"])
        self.assertEqual(body["result"], None)
        self.assertIn("环路", body["nodes"]["r"]["error"])

    def test_concurrent_requests_do_not_share_variables(self):
        """两次求值互不污染（变量走 contextvar，不是模块全局）。"""
        first = sample_graph()
        first["nodes"].append(dict(id="v1", type="var", pos=[0, 0],
                                   fields={"defs": "A = 1"}))
        second = sample_graph()
        second["nodes"].append(dict(id="v2", type="var", pos=[0, 0],
                                    fields={"defs": "B = 2"}))

        a = client.post("/api/evaluate", json=first).json()
        b = client.post("/api/evaluate", json=second).json()
        names_a = {v["name"] for v in a["variables"]}
        names_b = {v["name"] for v in b["variables"]}

        self.assertEqual(names_a, {"A"})
        self.assertEqual(names_b, {"B"})


class TestReportEndpoint(StorageIsolated):
    """导出结果：生成报告 + 直接落盘（所以要隔离到临时目录，别写进工作区）。"""

    def test_report_contains_inputs_and_result(self):
        r = client.post("/api/report", json=sample_graph())
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["filename"].endswith(".txt"))
        self.assertTrue(Path(body["path"]).is_file())
        text = body["text"]
        for token in ("原神 · 直伤伤害计算", "【节点卡片】", "【连线】",
                      "【结果】", "未暴击伤害", "期望伤害",
                      "【节点求值过程（从结果反向溯源）】", "暴击区"):
            self.assertIn(token, text, token)

    def test_report_has_no_scientific_notation(self):
        data = sample_graph()
        data["nodes"][0]["fields"]["stat_base"] = "12345678"
        text = client.post("/api/report", json=data).json()["text"]
        self.assertNotIn("e+", text.lower())

    def test_report_custom_title_kept_in_text(self):
        body = client.post("/api/report", json=dict(
            graph=sample_graph(), title="我的配队")).json()
        self.assertIn("我的配队", body["text"])

    def test_report_without_result_card(self):
        data = sample_graph()
        data["nodes"] = [n for n in data["nodes"] if n["type"] != "result"]
        data["links"] = []
        text = client.post("/api/report", json=data).json()["text"]
        self.assertIn("还没有「★结果」卡片", text)


class TestReportModule(unittest.TestCase):
    def test_default_filename_format(self):
        import datetime
        name = report.default_filename("直伤伤害", datetime.datetime(2024, 5, 6, 7, 8, 9))
        self.assertEqual(name, "直伤伤害_20240506_070809.txt")

    def test_snapshot_rows(self):
        g = Graph.from_dict(sample_graph())
        sections = report.snapshot(g)
        self.assertEqual([s[0] for s in sections], ["节点卡片", "连线"])
        self.assertEqual(len(sections[0][1]), 3)
        self.assertEqual(sections[1][1][0][1], "n1 -> n2.in0")

    def test_variables_text(self):
        g = Graph.from_dict(sample_graph())
        g.add(GraphNode("v1", "var", fields={"defs": "A = 1"}))
        text = report.variables_text(g)
        self.assertEqual(text, "变量\t值\nA\t1")

    def test_variables_text_empty(self):
        g = Graph.from_dict(sample_graph())
        self.assertIn("（暂无变量）", report.variables_text(g))

    def test_describe_marks_errors(self):
        g = Graph.from_dict(dict(nodes=[
            dict(id="c", type="calc", pos=[0, 0], fields={"expr": "1+"}),
            dict(id="r", type="result", pos=[0, 0], fields={})],
            links=[dict(src="c", dst="r", port=0)]))
        out = g.evaluate()
        self.assertTrue(out["nodes"]["c"]["error"])
        lines = report.describe(g, out)
        self.assertTrue(any("错误" in line for line in lines), lines)


class TestTutorial(unittest.TestCase):
    def test_sections_parsed(self):
        self.assertIn("基本概念", tutorial.SECTIONS)
        self.assertIn("快捷键", tutorial.SECTIONS)

    def test_mentions_every_card_label(self):
        """教程里应该能搜到每张卡片的菜单名，避免文案与卡片脱节。"""
        for key, spec in nd.NODE_TYPES.items():
            label = spec["label"]
            self.assertIn(label, tutorial.HELP_TEXT, "%s (%s)" % (label, key))

    def test_tutorial_json_serializable(self):
        json.dumps(dict(text=tutorial.HELP_TEXT, sections=tutorial.SECTIONS),
                   ensure_ascii=False)


class TestFrontendStaleness(unittest.TestCase):
    """前端产物过期的判定要能从接口看到（否则界面缺功能时无从下手）。

    这里的临时目录要**照真实层级**搭：`<web>/dist/index.html` + `<web>/src/...`。
    （早先只用 web/dist 当参数、fixture 也没有 src，结果漏掉了「层级传错 →
    产物明明在却报未构建」这个 bug。）
    """

    def make_web(self, web_stale: bool):
        """造一个前端目录：dist 存在，src 按需比 dist 新。"""
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web = Path(tmp.name) / "web"
        (web / "dist" / "assets").mkdir(parents=True)
        (web / "src").mkdir(parents=True)
        (web / "dist" / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        (web / "dist" / "assets" / "index-abc.js").write_text("1", encoding="utf-8")
        (web / "src" / "App.tsx").write_text("// app", encoding="utf-8")
        if web_stale:
            os.utime(web / "src" / "App.tsx", (2_000_000_000, 2_000_000_000))
            os.utime(web / "dist" / "index.html", (1_000_000_000, 1_000_000_000))
        else:
            os.utime(web / "src" / "App.tsx", (1_000_000_000, 1_000_000_000))
            os.utime(web / "dist" / "index.html", (2_000_000_000, 2_000_000_000))

        patcher = mock.patch("server.app.WEB_DIST", str(web / "dist"))
        patcher.start()
        self.addCleanup(patcher.stop)
        return web

    def test_health_reports_staleness_fields(self):
        body = client.get("/api/health").json()
        for key in ("webBuilt", "webStale", "webBuildTime", "webSourceTime", "webReason"):
            self.assertIn(key, body)

    def test_health_sees_existing_build(self):
        """产物存在就必须报 built=True（层级传错的话这里会红）。"""
        self.make_web(web_stale=False)
        body = client.get("/api/health").json()

        self.assertTrue(body["webBuilt"])
        self.assertFalse(body["webStale"])
        self.assertEqual(body["webReason"], "产物是最新的")
        self.assertRegex(body["webBuildTime"], r"^\d{4}-\d{2}-\d{2} ")

    def test_health_flags_stale_build(self):
        self.make_web(web_stale=True)
        body = client.get("/api/health").json()

        self.assertTrue(body["webBuilt"])
        self.assertTrue(body["webStale"])
        self.assertEqual(body["webReason"], "前端源码比构建产物新")

    def test_index_html_is_not_cached_but_assets_are(self):
        """index.html 必须 no-cache：它是入口，缓存住就等于一直用旧 bundle。"""
        self.make_web(web_stale=False)

        index = client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("no-cache", index.headers.get("cache-control", ""))

        asset = client.get("/assets/index-abc.js")
        self.assertEqual(asset.status_code, 200)
        self.assertIn("immutable", asset.headers.get("cache-control", ""))

        # 未命中的前端路由回落 index.html，同样不能缓存
        spa = client.get("/some/route")
        self.assertEqual(spa.status_code, 200)
        self.assertIn("no-cache", spa.headers.get("cache-control", ""))

    def test_index_falls_back_when_dist_missing(self):
        with TemporaryDirectory() as tmp:
            patcher = mock.patch("server.app.WEB_DIST", tmp)
            patcher.start()
            self.addCleanup(patcher.stop)

            r = client.get("/")
            self.assertEqual(r.status_code, 200)
            self.assertIn("后端已启动", r.text)


class TestStorageApi(StorageIsolated):
    """一键保存 / 打开 / 记忆目录的接口测试。"""

    def test_storage_info_reports_default_dir(self):
        body = client.get("/api/storage").json()
        self.assertEqual(body["dir"], str((self.root / "projects").resolve()))
        self.assertEqual(body["defaultDir"], str((self.root / "projects").resolve()))
        self.assertFalse(body["exists"])

    def test_save_project_writes_file_and_creates_dir(self):
        data = sample_graph(name="雷神")
        r = client.post("/api/save/project", json=data)
        body = r.json()

        self.assertEqual(r.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["filename"], "雷神.json")
        path = Path(body["path"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, (self.root / "projects").resolve())
        # 中文不转义、缩进 2（人工可读、可手工编辑）
        text = path.read_text(encoding="utf-8")
        self.assertIn("雷神", text)
        self.assertIn("\n  ", text)
        self.assertEqual(json.loads(text)["app"], "GenshinDamageCalc")

    def test_save_project_overwrites_in_place(self):
        """一键保存是 Ctrl+S 语义：同名直接覆盖，不会越存越多。"""
        first = client.post("/api/save/project", json=sample_graph(name="雷神")).json()
        second = client.post(
            "/api/save/project",
            json=sample_graph(name="雷神", with_crit=False),
        ).json()

        self.assertEqual(first["path"], second["path"])
        files = list((self.root / "projects").iterdir())
        self.assertEqual([f.name for f in files], ["雷神.json"])

    def test_save_project_without_name_uses_fallback(self):
        body = client.post("/api/save/project", json=sample_graph(name="")).json()
        self.assertEqual(body["filename"], "伤害工程.json")

    def test_save_project_sanitizes_dangerous_name(self):
        """名字里带路径分隔符也只能落在当前目录里（写不出 projects/ 之外）。"""
        body = client.post("/api/save/project", json=sample_graph(name="../../逃逸")).json()
        path = Path(body["path"])
        self.assertEqual(path.parent, (self.root / "projects").resolve())
        self.assertNotIn("/", path.name)
        self.assertNotIn("\\", path.name)

    def test_save_report_writes_txt_next_to_project(self):
        r = client.post("/api/report", json=sample_graph(name="雷神"))
        body = r.json()

        self.assertEqual(r.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertRegex(body["filename"], r"^雷神_\d{8}_\d{6}\.txt$")
        path = Path(body["path"])
        self.assertEqual(path.parent, (self.root / "projects").resolve())
        text = path.read_text(encoding="utf-8")
        self.assertIn("【结果】", text)
        self.assertIn("未暴击伤害", text)

    def test_open_project_remembers_directory_and_saves_back(self):
        """核心行为：从哪读就往哪存。"""
        source = self.root / "别处的工程" / "旧工程.json"
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps(sample_graph(name="旧工程"), ensure_ascii=False),
                          encoding="utf-8")
        self.stub_dialog(source)

        opened = client.post("/api/open").json()
        self.assertTrue(opened["ok"])
        self.assertEqual(opened["graph"]["name"], "旧工程")
        self.assertEqual(opened["dir"], str(source.parent.resolve()))
        self.assertEqual(opened["storage"]["dir"], str(source.parent.resolve()))

        saved = client.post("/api/save/project", json=sample_graph(name="旧工程")).json()
        self.assertEqual(Path(saved["path"]).parent, source.parent.resolve())
        self.assertTrue((source.parent / "旧工程.json").is_file())
        # 默认目录里不应该多出东西
        self.assertFalse((self.root / "projects").exists())

    def test_open_project_cancelled_is_not_an_error(self):
        self.stub_dialog("")
        body = client.post("/api/open").json()
        self.assertEqual(body, {"ok": False, "cancelled": True})

    def test_open_project_with_broken_file(self):
        bad = self.root / "坏工程.json"
        bad.write_text("{不是 json", encoding="utf-8")
        self.stub_dialog(bad)

        r = client.post("/api/open")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])

    def test_open_project_when_dialog_unavailable(self):
        """没有图形环境（对话框子进程跑不起来）时返回 None → 当作用户取消。"""
        self.stub_dialog(None)
        self.assertEqual(client.post("/api/open").json(), {"ok": False, "cancelled": True})


if __name__ == "__main__":
    unittest.main()

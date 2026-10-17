# -*- coding: utf-8 -*-
"""工程落盘存储（server/storage.py）的测试。

都在临时目录里跑（monkeypatch 掉 DEFAULT_DIR / CONFIG_PATH），
不会往工作区的 private/ 写任何东西。

运行：``python -m pytest test_storage.py -q``
"""

import datetime
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server import storage


class StorageCase(unittest.TestCase):
    """把默认目录与配置文件都指到临时目录。"""

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


class TestSafeName(StorageCase):
    def test_keeps_chinese_and_strips_illegal(self):
        self.assertEqual(storage.safe_name("雷神"), "雷神")
        self.assertEqual(storage.safe_name("雷神/专武:测试?"), "雷神_专武_测试_")

    def test_path_traversal_cannot_escape(self):
        """斜杠与 .. 都会被清洗掉，写不出当前目录。"""
        name = storage.safe_name("../../etc/passwd")
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)
        path = storage.project_file("../../etc/passwd")
        self.assertEqual(path.parent, storage.current_dir())

    def test_blank_uses_fallback(self):
        self.assertEqual(storage.safe_name(""), storage.DEFAULT_PROJECT_NAME)
        self.assertEqual(storage.safe_name("   "), storage.DEFAULT_PROJECT_NAME)
        self.assertEqual(storage.safe_name("..."), storage.DEFAULT_PROJECT_NAME)

    def test_length_capped(self):
        self.assertLessEqual(len(storage.safe_name("あ" * 500)), 80)


class TestDirectoryMemory(StorageCase):
    def test_first_time_falls_back_to_default(self):
        self.assertEqual(storage.current_dir(), (self.root / "projects").resolve())

    def test_remembers_directory_of_opened_file(self):
        target = self.root / "我的工程" / "雷神.json"
        target.parent.mkdir(parents=True)
        target.write_text("{}", encoding="utf-8")

        remembered = storage.remember_path(target)

        self.assertEqual(remembered, target.parent.resolve())
        self.assertEqual(storage.current_dir(), target.parent.resolve())
        self.assertTrue(storage.CONFIG_PATH.is_file())

    def test_remembering_a_directory_keeps_it(self):
        self.assertEqual(storage.remember_path(self.root), self.root.resolve())
        self.assertEqual(storage.current_dir(), self.root.resolve())

    def test_config_survives_and_is_readable(self):
        storage.remember_path(self.root)
        data = json.loads(storage.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["dir"], str(self.root.resolve()))
        self.assertIn("updated", data)

    def test_broken_config_falls_back(self):
        storage.CONFIG_PATH.write_text("{不是 json", encoding="utf-8")
        self.assertEqual(storage.current_dir(), (self.root / "projects").resolve())

    def test_info_reports_paths(self):
        info = storage.info()
        self.assertEqual(info["dir"], str((self.root / "projects").resolve()))
        self.assertEqual(info["defaultDir"], str((self.root / "projects").resolve()))
        self.assertFalse(info["exists"])


class TestProjectAndReportFiles(StorageCase):
    def test_project_file_name(self):
        self.assertEqual(storage.project_file("雷神").name, "雷神.json")
        self.assertEqual(storage.project_file("").name, "伤害工程.json")

    def test_report_file_has_timestamp_and_never_collides(self):
        now = datetime.datetime(2026, 9, 9, 17, 30, 5)
        path = storage.report_file("雷神", now)
        self.assertEqual(path.name, "雷神_20260909_173005.txt")
        later = storage.report_file("雷神", now + datetime.timedelta(seconds=1))
        self.assertNotEqual(path, later)

    def test_write_json_creates_directory_and_keeps_chinese(self):
        path = storage.project_file("雷神")
        storage.write_json(path, {"name": "雷神", "nodes": [{"id": "n1"}]})

        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("雷神", text)              # 没被转义成 \uXXXX
        self.assertIn("\n  ", text)              # 缩进 2
        self.assertEqual(json.loads(text)["nodes"][0]["id"], "n1")

    def test_write_text(self):
        path = storage.current_dir() / "报告.txt"
        storage.write_text(path, "hello\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "hello\n")

    def test_read_graph_roundtrip(self):
        path = storage.project_file("工程A")
        storage.write_json(path, {"name": "工程A", "nodes": [], "links": []})
        self.assertEqual(storage.read_graph(path)["name"], "工程A")

    def test_read_graph_errors(self):
        with self.assertRaises(ValueError):
            storage.read_graph(self.root / "不存在.json")
        bad = self.root / "坏.json"
        bad.write_text("[1,2,3]", encoding="utf-8")
        with self.assertRaises(ValueError):
            storage.read_graph(bad)

    def test_abs_path_is_absolute(self):
        self.assertTrue(Path(storage.abs_path(".")).is_absolute())


if __name__ == "__main__":
    unittest.main()

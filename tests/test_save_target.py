# -*- coding: utf-8 -*-
"""保存落到哪个文件：从哪读就往哪存（工程名与文件名不一致时别写歪）。"""

import json
import tempfile
import unittest


class TestSaveTarget(unittest.TestCase):
    def setUp(self):
        from server import storage

        self.storage = storage
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = __import__("pathlib").Path(tmp.name)
        self._old_dir = storage.DEFAULT_DIR
        self._old_cfg = storage.CONFIG_PATH
        storage.DEFAULT_DIR = self.root / "projects"
        storage.CONFIG_PATH = self.root / "save_config.json"
        self.addCleanup(self._restore)

    def _restore(self):
        self.storage.DEFAULT_DIR = self._old_dir
        self.storage.CONFIG_PATH = self._old_cfg

    def write(self, name, project_name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": project_name}), encoding="utf-8")
        return path

    def test_same_name_writes_back_to_the_opened_file(self):
        """文件名与工程名不一致：保存要写回**打开的那个文件**，不能另起一个。"""
        opened = self.write("米c0.json", "米奥瓦砂")      # 文件名 ≠ 工程名
        self.storage.remember_path(opened)
        target = self.storage.save_target("米奥瓦砂")
        self.assertEqual(target, opened.resolve())

    def test_renamed_project_gets_a_new_file(self):
        opened = self.write("旧名.json", "旧名")
        self.storage.remember_path(opened)
        target = self.storage.save_target("新名")
        self.assertEqual(target.name, "新名.json")
        self.assertEqual(target.parent, self.root.resolve())

    def test_no_remembered_file_falls_back_to_project_name(self):
        target = self.storage.save_target("某工程")
        self.assertEqual(target.name, "某工程.json")

    def test_broken_remembered_file_falls_back(self):
        broken = self.root / "坏.json"
        broken.write_text("{不是 json", encoding="utf-8")
        self.storage.remember_path(broken)
        self.assertEqual(self.storage.save_target("随便").name, "随便.json")


if __name__ == "__main__":                       # pragma: no cover
    unittest.main()

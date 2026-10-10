# -*- coding: utf-8 -*-
"""前端产物过期检测（server/build_check.py）的测试。

背景：`git pull` 拿到新前端却没重建 web/dist 时，后端会继续发旧界面 ——
接口正常、功能缺失，非常难查。这里的判定就是那条防线，必须可靠。

运行：``python -m pytest test_build_check.py -q``
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server import build_check


def write(path: Path, text: str = "x", mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class BuildCheckCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.web = Path(self._tmp.name) / "web"
        self.web.mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def dist(self, mtime: float) -> Path:
        return write(self.web / "dist" / "index.html", "built", mtime)


class TestStaleness(BuildCheckCase):
    def test_missing_dist_is_stale(self):
        write(self.web / "src" / "App.tsx", mtime=100)
        self.assertTrue(build_check.is_stale(self.web))
        state = build_check.status(self.web)
        self.assertFalse(state["built"])
        self.assertTrue(state["stale"])
        self.assertEqual(state["reason"], "还没有构建产物")

    def test_fresh_when_dist_is_newer(self):
        write(self.web / "src" / "App.tsx", mtime=100)
        self.dist(200)
        self.assertFalse(build_check.is_stale(self.web))
        self.assertEqual(build_check.status(self.web)["reason"], "产物是最新的")

    def test_stale_when_source_is_newer(self):
        """核心场景：pull 下来新前端（源码更新），dist 还是旧的。"""
        write(self.web / "src" / "App.tsx", mtime=300)
        self.dist(200)
        self.assertTrue(build_check.is_stale(self.web))
        self.assertEqual(build_check.status(self.web)["reason"], "前端源码比构建产物新")

    def test_watches_nested_source_dirs(self):
        self.dist(200)
        write(self.web / "src" / "components" / "CardNode.tsx", mtime=400)
        self.assertTrue(build_check.is_stale(self.web))

    def test_watches_config_files(self):
        for name in build_check.SOURCE_FILES:
            with self.subTest(name=name):
                self.dist(200)
                write(self.web / name, mtime=500)
                self.assertTrue(build_check.is_stale(self.web))
                (self.web / name).unlink()

    def test_ignores_node_modules_and_dist(self):
        """node_modules / 其它产物不该触发重建（否则每次装依赖都要重建）。"""
        self.dist(200)
        write(self.web / "node_modules" / "pkg" / "index.js", mtime=900)
        write(self.web / "dist" / "assets" / "index-abc.js", mtime=900)
        self.assertFalse(build_check.is_stale(self.web))

    def test_empty_source_dir_uses_dist_only(self):
        self.dist(200)
        self.assertFalse(build_check.is_stale(self.web))


class TestStatusFields(BuildCheckCase):
    def test_times_are_formatted(self):
        write(self.web / "src" / "App.tsx", mtime=1_700_000_000)
        self.dist(1_700_000_500)
        state = build_check.status(self.web)

        self.assertEqual(state["buildTime"], build_check.format_time(1_700_000_500))
        self.assertEqual(state["sourceTime"], build_check.format_time(1_700_000_000))
        self.assertRegex(state["buildTime"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertIn("index.html", state["distIndex"])

    def test_format_time_handles_none(self):
        self.assertIsNone(build_check.format_time(None))
        self.assertIsNone(build_check.format_time(0))

    def test_json_serializable(self):
        import json
        json.dumps(build_check.status(self.web), ensure_ascii=False)


class TestStatusForDist(BuildCheckCase):
    """按 dist 目录判断的入口（server/app.py 只拿得到 web/dist）。"""

    def test_same_result_as_web_dir(self):
        write(self.web / "src" / "App.tsx", mtime=100)
        self.dist(200)

        by_web = build_check.status(self.web)
        by_dist = build_check.status_for_dist(self.web / "dist")

        self.assertEqual(by_dist, by_web)
        self.assertTrue(by_dist["built"])

    def test_dist_dir_argument_does_not_confuse_levels(self):
        """把 web/dist 误传给 status() 会去找 web/dist/dist → 误报未构建；
        status_for_dist 必须避开这个坑。"""
        write(self.web / "src" / "App.tsx", mtime=100)
        self.dist(200)

        self.assertFalse(build_check.status(self.web / "dist")["built"])   # 层级传错的表现
        self.assertTrue(build_check.status_for_dist(self.web / "dist")["built"])


class TestCli(BuildCheckCase):
    def test_exit_codes_and_output(self):
        import io
        from contextlib import redirect_stdout

        # 缺产物 → 1
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = build_check.main(["--web-dir", str(self.web)])
        self.assertEqual(code, 1)
        self.assertIn("还没有构建产物", buf.getvalue())

        # 产物比源码新 → 0
        write(self.web / "src" / "App.tsx", mtime=100)
        self.dist(200)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = build_check.main(["--web-dir", str(self.web)])
        self.assertEqual(code, 0)
        self.assertIn("产物是最新的", buf.getvalue())

        # --json 输出可解析
        buf = io.StringIO()
        with redirect_stdout(buf):
            build_check.main(["--web-dir", str(self.web), "--json"])
        import json
        self.assertFalse(json.loads(buf.getvalue())["stale"])

    def test_default_web_dir_is_repo_web(self):
        self.assertEqual(build_check.WEB_DIR, build_check.ROOT / "web")
        self.assertTrue(build_check.DIST_INDEX.name == "index.html")


if __name__ == "__main__":
    unittest.main()

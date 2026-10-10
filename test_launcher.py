# -*- coding: utf-8 -*-
"""启动器 launcher.bat 的约束测试。

**为什么必须纯 ASCII**：cmd.exe 按「读文件那一刻的控制台代码页」解析批处理文件。
中文 Windows 双击时控制台是 936(ANSI)，文件里只要出现非 ASCII（中文）字节，
多字节序列就会让解析错位 —— `echo ` 前缀被上一行吃掉，菜单行被当成命令执行：

    '[4]' is not recognized as an internal or external command

实测矩阵（同一份内容，只改编码与起始代码页，各跑 3 次）::

    起始代码页   UTF-8 版(含中文)   纯 ASCII 版
    936          3/3 报错           0/3   ← 双击时的真实场景
    65001        0/3                0/3
    437          0/3                0/3

所以界面文案统一用英文，文件只含 ASCII 字符。改这个文件时别写中文。

运行：``python -m pytest test_launcher.py -q``
"""

import os
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "launcher.bat")


class TestLauncher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(PATH):
            raise unittest.SkipTest("没有 launcher.bat")
        with open(PATH, "rb") as f:
            cls.raw = f.read()

    def test_is_pure_ascii(self):
        """任何 >0x7F 的字节都会在中文 Windows 下造成批处理解析错位。"""
        bad = [i for i, b in enumerate(self.raw) if b > 0x7F]
        if bad:
            line = self.raw[: bad[0]].count(b"\n") + 1
            self.fail(
                "launcher.bat 第 %d 行附近出现非 ASCII 字节（共 %d 处）。"
                "界面文案请用英文，否则中文 Windows 下菜单会被解析错位。"
                % (line, len(bad))
            )

    def test_crlf_line_endings(self):
        """不能有裸 LF（批处理在部分场景下对行尾敏感）。"""
        self.assertGreater(self.raw.count(b"\r\n"), 0)
        self.assertEqual(self.raw.count(b"\n"), self.raw.count(b"\r\n"))

    def test_no_bom(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))

    def test_does_not_touch_console_codepage(self):
        """纯 ASCII 不需要 chcp，免得改掉用户的控制台代码页。"""
        self.assertNotIn(b"chcp", self.raw)

    def test_menu_and_actions_present(self):
        text = self.raw.decode("ascii")
        for token in ("[1]", "[2]", "[3]", "[4]",
                      ":start", ":stop", ":dev",
                      ":pick_pkg", ":ensure_python", ":menu"):
            self.assertIn(token, text, token)

    def test_package_manager_order(self):
        """顺序必须是 pnpm → corepack pnpm → npm（锁文件由 pnpm 11 生成）。"""
        text = self.raw.decode("ascii")
        pick = text.split(":pick_pkg", 1)[1]
        # 注意用带 `call ` 前缀的标记：`npm --version` 本身是 `pnpm --version` 的子串
        pnpm = pick.index("call pnpm --version")
        corepack = pick.index("call corepack pnpm --version")
        npm = pick.index("call npm --version")
        self.assertLess(pnpm, corepack)
        self.assertLess(corepack, npm)

    def test_frontend_staleness_checked_by_python(self):
        """不能只判断 dist 是否存在：git pull 后旧产物会被一直沿用（界面缺功能）。"""
        text = self.raw.decode("ascii")
        self.assertIn("server.build_check", text)
        self.assertNotIn('if exist "%ROOT%web\\dist\\index.html"', text)
        self.assertIn("older than web\\src", text)

    def test_default_port_matches_backend(self):
        """启动器默认端口要和 main.py 的默认端口一致。"""
        self.assertIn("8777", self.raw.decode("ascii"))
        with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
            self.assertIn("DEFAULT_PORT = 8777", f.read())


if __name__ == "__main__":
    unittest.main()

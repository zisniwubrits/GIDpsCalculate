# -*- coding: utf-8 -*-
"""启动器 launcher.bat 的约束测试。

**为什么必须锁住编码**：cmd.exe 按「读文件那一刻的控制台代码页」解析批处理。
中文 Windows 双击时控制台是 936(ANSI)，如果 launcher.bat 存成 UTF-8，
中文行会被当成 GBK 解析而产生字节错位 —— `echo ` 前缀被上一行吃掉，
菜单行被当作命令执行，表现为：

    '[4]' is not recognized as an internal or external command

实测矩阵（同一文件内容，只改编码 / 起始代码页）::

    起始代码页   UTF-8 版   GBK 版
    936          3/3 报错   0/3 ✓      ← 双击时的真实场景
    65001        0/3        0/3
    437          0/3        0/3

所以：**launcher.bat 必须保持 GBK 编码 + CRLF**。
修改它的正确姿势见 AGENTS.md「启动器编码」一节。

运行：``python -m pytest test_launcher.py -q``
"""

import os
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "launcher.bat")


class TestLauncherEncoding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(PATH):
            raise unittest.SkipTest("没有 launcher.bat")
        with open(PATH, "rb") as f:
            cls.raw = f.read()

    def test_is_gbk_encoded(self):
        """能按 GBK 解出中文，且含非 ASCII 时一定不是合法 UTF-8。"""
        text = self.raw.decode("gbk")
        self.assertIn("原神伤害计算器", text)

        if any(b > 0x7F for b in self.raw):
            strict = "utf-8"
            with self.assertRaises(UnicodeDecodeError, msg=(
                    "launcher.bat 被存成了 UTF-8！请按 AGENTS.md 重新编码为 GBK，"
                    "否则中文 Windows 下菜单会被解析错位")):
                self.raw.decode(strict)

    def test_crlf_line_endings(self):
        """不能有裸 LF（批处理在部分场景下对行尾敏感）。"""
        self.assertGreater(self.raw.count(b"\r\n"), 0)
        self.assertEqual(self.raw.count(b"\n"), self.raw.count(b"\r\n"))

    def test_switches_to_gbk_codepage(self):
        """文件自带 chcp 936，保证显示与解析的代码页一致。"""
        text = self.raw.decode("gbk")
        self.assertIn("chcp 936", text)
        self.assertNotIn("chcp 65001", text)

    def test_no_utf8_bom(self):
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"))

    def test_menu_and_actions_present(self):
        text = self.raw.decode("gbk")
        for token in ("[1]", "[2]", "[3]", "[4]",
                      ":start", ":stop", ":dev",
                      ":pick_pkg", ":ensure_python", ":menu"):
            self.assertIn(token, text, token)

    def test_default_port_matches_backend(self):
        """启动器默认端口要和 main.py 的默认端口一致。"""
        text = self.raw.decode("gbk")
        self.assertIn("8777", text)
        with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
            self.assertIn("DEFAULT_PORT = 8777", f.read())


if __name__ == "__main__":
    unittest.main()

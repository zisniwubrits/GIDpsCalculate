# -*- coding: utf-8 -*-
"""本机原生文件对话框（后端用**子进程**弹窗）。

为什么用子进程而不是直接 import tkinter：

* Tk 实例适合在主线程创建，而 FastAPI 的同步接口跑在线程池里，直接弹窗有崩溃风险；
* 子进程结束后资源自然回收，不会在服务进程里留下 Tk 状态；
* 弹窗期间只阻塞这一个请求，不影响其它接口。

无图形环境（纯命令行/CI）时返回 None，调用方按「用户取消」处理，不会让接口报错。
"""

from __future__ import annotations

import subprocess
import sys

__all__ = ["pick_open_file", "PROJECT_FILETYPES"]

PROJECT_FILETYPES = [("JSON 工程", "*.json"), ("所有文件", "*.*")]

# 子进程里跑的小脚本：把选中的路径打到 stdout（取消则空行）。
_OPEN_SCRIPT = r"""
import sys
try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    print("")
    raise SystemExit(0)

initial = sys.argv[1] if len(sys.argv) > 1 else ""
title = sys.argv[2] if len(sys.argv) > 2 else "打开"
root = tk.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)
except Exception:
    pass
try:
    path = filedialog.askopenfilename(
        title=title,
        initialdir=initial or None,
        filetypes=[("JSON 工程", "*.json"), ("所有文件", "*.*")],
    )
finally:
    root.destroy()
print(path or "")
"""


def pick_open_file(initial_dir=None, title: str = "打开工程 (JSON)") -> str | None:
    """弹原生「打开文件」对话框；返回绝对路径，用户取消或不可用则返回 None。"""
    args = [sys.executable, "-c", _OPEN_SCRIPT, str(initial_dir or ""), title]
    try:
        proc = subprocess.run(args, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    path = (proc.stdout or "").strip()
    return path or None

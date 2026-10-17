# -*- coding: utf-8 -*-
"""跨文件读拐力：把**另一个工程文件**里某个域声明过的 ``out::`` 读出来。

为什么单独一个模块：``nodes.py``（卡片定义）和 ``graph.py``（求值）都要用它，
而它自己需要在「读文件 → 构造 Graph → 求值」时才 import 求值器 —— 放这里就不会
形成循环导入。

口径（与文件内拐力保持一致，只是来源换成另一个文件）：
* 只读**显式声明过**的 ``out::名字 = 值``（面板里的普通项不给出去）；
* 取那个文件**求值之后**的 ``out::`` 值，所以那个文件**自己内部**的拐力已经算进去了；
* 只读不写：不动被引用的文件；
* 有环就停（A 引用 B、B 又引用 A 时返回空，不会卡死），并且按 mtime 缓存，
  敲键盘时不会反复读盘。
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar

__all__ = ["out_values", "clear_cache"]

# 正在解析的文件栈（防环）。用 ContextVar 而不是模块级 set：
# 后端是并发的，两个请求同时求值不能互相干扰。
_STACK: ContextVar[tuple] = ContextVar("genshin_external_stack", default=())

# 缓存：{(绝对路径, mtime, size): {角色: {名字: 值}}}
# 文件改了 mtime 就变，缓存自然失效；不设上限是因为条目数＝用户实际引用过的工程文件数。
_CACHE: dict = {}


def clear_cache() -> None:
    """清空缓存（测试用；正常使用靠 mtime 失效）。"""
    _CACHE.clear()


def out_values(path: str, role: str) -> dict:
    """读 ``path`` 这个工程文件里 ``role`` 声明过的 ``out::``，返回 ``{名字: 值}``。

    读不到（文件不存在 / 不是合法工程 / 那个域不存在 / 有环）一律返回空字典 ——
    调用方按"给了 0"处理，不会让整个求值失败。
    """
    role = str(role or "").strip()
    raw = str(path or "").strip()
    if not raw or not role:
        return {}
    try:
        full = os.path.abspath(os.path.expanduser(raw))
        stat = os.stat(full)
    except OSError:
        return {}
    key = (full, stat.st_mtime_ns, stat.st_size)
    per_role = _CACHE.get(key)
    if per_role is None:
        per_role = _read_file(full)
        _CACHE[key] = per_role
    return dict(per_role.get(role) or {})


def _read_file(full: str) -> dict:
    """把一个工程文件求值，抽出所有 ``角色::out::名字`` → ``{角色: {名字: 值}}``。"""
    if full in _STACK.get():
        return {}                       # 环：A 引用 B，B 又引用 A
    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    token = _STACK.set(_STACK.get() + (full,))
    try:
        # 延迟 import：graph 模块本身会 import 本模块（见模块文档）
        from .graph import Graph

        graph = Graph.from_dict(data)
        graph.evaluate()
        # 变量名在内部是 ``角色__out__名字`` 这种 mangled 形式，先 demangle 回
        # ``角色::out::名字`` 再切
        from .expr import demangle

        out: dict = {}
        for key in graph.variables:
            full = demangle(key)
            role, sep, rest = full.partition("::out::")
            if not sep:
                continue
            name = rest
            if "::" in name:
                continue                # 其它子命名空间（own::x 之类）不要
            value = graph.variables[key]
            try:
                num = float(value() if callable(value) else value)
            except (TypeError, ValueError):
                continue
            if not num:
                continue                # 0 等于"没给"，不进结果（面板宏会有一堆 0）
            out.setdefault(role, {})[name] = num
        return out
    finally:
        _STACK.reset(token)

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

路径怎么写（用户要求）：
* 绝对路径：直接用；
* 相对路径按「当前工程文件所在目录」等几个基准解析（见 :func:`_bases`），例如同目录下
  填 ``dds.json``、甚至只写 ``dds``（自动补 ``.json``）；子目录里的文件要把目录写出来
  （``data\\幻灭米提亚``）—— 不去子目录里猜同名文件，避免歧义；
* 找不到再退回后端进程的工作目录（就是仓库根），并支持 ``~/``；
* 域名字留空且那个文件里**只有一个域**时，直接用那个域（前端会把这一栏藏起来）。
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar

__all__ = ["out_values", "domains", "resolve", "clear_cache"]

# 正在解析的文件栈（防环）。用 ContextVar 而不是模块级 set：
# 后端是并发的，两个请求同时求值不能互相干扰。
_STACK: ContextVar[tuple] = ContextVar("genshin_external_stack", default=())

# 缓存：{(绝对路径, mtime, size): (域名字列表, {角色: {名字: 值}})}
# 文件改了 mtime 就变，缓存自然失效；条目数＝用户实际引用过的工程文件数。
_CACHE: dict = {}


def clear_cache() -> None:
    """清空缓存（测试用；正常使用靠 mtime 失效）。"""
    _CACHE.clear()


def _bases(base_dir: str | None = None, extra_bases=()) -> list:
    """解析相对路径时要试的基准目录（按优先级，去重）。"""
    out: list = []

    def push(value) -> None:
        if value is None:
            return
        value = str(value).strip()
        if not value:
            return
        full = os.path.abspath(os.path.expanduser(value))
        if full not in out:
            out.append(full)

    for base in (base_dir, *extra_bases):
        push(base)
    # 工程目录的**上一级**也试一下：工程在 xxx/data/ 里、卡片填 "data/xxx.json"
    # 或反过来（工程在 xxx/、文件在 xxx/data/xxx.json）时都能命中
    for base in list(out):
        parent = os.path.dirname(base)
        if parent and parent != base:
            push(parent)
    push("")                            # "" = 进程工作目录（仓库根）
    return out


def resolve(path: str, base_dir: str | None = None, extra_bases=()) -> str:
    """把用户填的路径解析成绝对路径；找不到就返回空串。

    顺序：绝对路径优先；否则在 :func:`_bases` 那几个目录里挨个试（自动补 ``.json``）。
    **不在子目录里搜同名文件** —— 那会出现歧义（两个子目录都有同名文件时该读哪个？），
    用户口径：要读子目录里的文件就把目录写出来，例如 ``data\\幻灭米提亚``。
    """
    raw = str(path or "").strip()
    if not raw:
        return ""
    expanded = os.path.expanduser(raw)
    names = [expanded]
    if not expanded.lower().endswith(".json"):
        names.append(expanded + ".json")

    if os.path.isabs(expanded):
        for name in names:
            if os.path.isfile(name):
                return os.path.abspath(name)
        return ""

    for name in names:
        for base in _bases(base_dir, extra_bases):
            full = os.path.abspath(os.path.join(base, name) if base else name)
            if os.path.isfile(full):
                return full
    return ""


def load(path: str, base_dir: str | None = None, extra_bases=()) -> tuple:
    """读并求值一个工程文件：``(域名字列表, {域: {out::名字: 值}})``。读不到就是空。"""
    full = resolve(path, base_dir, extra_bases)
    if not full:
        return ([], {})
    try:
        stat = os.stat(full)
    except OSError:
        return ([], {})
    key = (full, stat.st_mtime_ns, stat.st_size)
    hit = _CACHE.get(key)
    if hit is None:
        hit = _read_file(full)
        _CACHE[key] = hit
    return hit


def domains(path: str, base_dir: str | None = None, extra_bases=()) -> list:
    """那个文件里有哪些域（角色 / 武器名）。"""
    return list(load(path, base_dir, extra_bases)[0])


def out_values(path: str, role: str = "", base_dir: str | None = None,
               extra_bases=()) -> dict:
    """读 ``path`` 这个工程文件里 ``role`` 声明过的 ``out::``，返回 ``{名字: 值}``。

    ``role`` 留空且文件里只有一个域时，自动用那个域（用户要求：唯一就不用手填）。
    读不到（文件不存在 / 不是合法工程 / 域不存在 / 有环）一律返回空字典 ——
    调用方按"给了 0"处理，不会让整个求值失败。
    """
    names, per_role = load(path, base_dir, extra_bases)
    wanted = str(role or "").strip()
    if not wanted:
        if len(names) != 1:
            return {}
        wanted = names[0]
    return dict(per_role.get(wanted) or {})


def _read_file(full: str) -> tuple:
    """把一个工程文件求值，返回 ``(域列表, {域: {out::名字: 值}})``。"""
    if full in _STACK.get():
        return ([], {})                  # 环：A 引用 B，B 又引用 A
    try:
        with open(full, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ([], {})
    token = _STACK.set(_STACK.get() + (full,))
    try:
        # 延迟 import：graph 模块本身会 import 本模块（见模块文档）
        from .expr import demangle
        from .graph import Graph

        graph = Graph.from_dict(data)
        graph.evaluate()
        names: list = []
        out: dict = {}
        # 变量名在内部是 ``角色__out__名字`` 这种 mangled 形式，先 demangle 回
        # ``角色::out::名字`` 再切
        for key in graph.variables:
            full_name = demangle(key)
            role, sep, rest = full_name.partition("::")
            if not sep or not role:
                continue
            if role not in names:
                names.append(role)       # 这个文件里出现过的域（含只写了普通宏的）
            if not rest.startswith("out::"):
                continue
            name = rest[len("out::"):]
            if not name or "::" in name:
                continue                 # 其它子命名空间的键
            value = graph.variables[key]
            try:
                num = float(value() if callable(value) else value)
            except (TypeError, ValueError):
                continue
            if not num:
                continue                 # 0 等于"没给"，不进结果（面板宏会有一堆 0）
            out.setdefault(role, {})[name] = num
        return (names, out)
    finally:
        _STACK.reset(token)

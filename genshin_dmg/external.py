# -*- coding: utf-8 -*-
"""跨文件读拐力：把**另一个工程文件**里某个域声明过的 ``out::`` 读出来。

为什么单独一个模块：``nodes.py``（卡片定义）和 ``graph.py``（求值）都要用它，
而它自己需要在「读文件 → 构造 Graph → 求值」时才 import 求值器 —— 放这里就不会
形成循环导入。

口径（与文件内拐力保持一致，只是来源换成另一个文件）：
* 只读**显式声明过**的 ``out::名字 = 值``（面板里的普通项不给出去）；
* 取那个文件**求值之后**的 ``out::`` 值，所以那个文件**自己内部**的拐力已经算进去了；
* 只读不写：不动被引用的文件；
* 文件互相引用（A→B→A）时**只切断"再往下读"**：被重新进入的那个文件仍然照常求值
  自己的 ``out::``（跟环无关），所以不会因为环就变成 0，也不会卡死；被切断的那次
  结果不进缓存。按 mtime 缓存，
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

__all__ = ["out_values", "domains", "resolve", "clear_cache", "begin", "take_cycles",
           "parse_sources", "source_label", "suggest_paths", "suggest_domains"]


def parse_sources(text, legacy_file="", legacy_role="") -> list:
    """把「外部域」卡片的文本解析成 ``[(文件, 域), …]``。

    一行一个外部域，格式 ``文件::域``（**只认 ``::``**，用户定的）：
    * ``data/幻灭米提亚::dds`` —— 文件 + 域；
    * ``data/幻灭米提亚`` —— 只给文件，域留空（那个文件里只有一个域时自动用它）；
    * 空行与 ``#`` 开头的行跳过。

    老工程只有 ``ext_file`` / ``ext_role`` 两个字段（一张卡一个来源），
    这里在文本为空时退回读它们，旧项目不用改。
    """
    out: list = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path, sep, role = line.partition("::")
        path = path.strip()
        role = role.strip() if sep else ""
        if path:
            out.append((path, role))
    if not out:
        legacy = str(legacy_file or "").strip()
        if legacy:
            out.append((legacy, str(legacy_role or "").strip()))
    return out


def source_label(path: str, role: str = "") -> str:
    """拐力统计里用的来源名字：``文件名.域名``（用户要求，一眼看出是哪个文件的哪个域）。"""
    base = os.path.splitext(os.path.basename(str(path or "")))[0] or str(path or "")
    role = str(role or "").strip()
    return "%s.%s" % (base, role) if role else base


def _split_partial(partial: str) -> tuple:
    """把正在输入的一段路径拆成 ``(目录部分含分隔符, 名字前缀)``。"""
    raw = str(partial or "")
    cut = max(raw.rfind("/"), raw.rfind("\\"))
    if cut < 0:
        return ("", raw)
    return (raw[:cut + 1], raw[cut + 1:])


def suggest_paths(partial: str, base_dir: str | None = None, extra_bases=(),
                  limit: int = 200) -> list:
    """给「外部域」输入框用的路径补全：列出候选的目录 / .json 文件。

    * 已输入部分按「目录 + 名字前缀」拆开，目录优先按 ``base_dir`` 等基准找；
    * 目录补成 ``名字/``（可以继续往里输入）；
    * 文件**不带 .json 后缀**（用户要求：补全忽略 json —— 解析时会自动补后缀）；
    * 已经手打了 ``.json`` 也照样能匹配（匹配时忽略这个后缀）；
    * 前缀大小写不敏感；目录排前面；最多 ``limit`` 条。
    """
    dir_part, prefix = _split_partial(partial)
    # 用户可能已经把 .json 打进去了：匹配时忽略它，候选里也不显示
    if prefix.lower().endswith(".json"):
        prefix = prefix[: -len(".json")]
    want_dir = dir_part.strip().rstrip("/\\") or "."
    target = ""
    for base in _bases(base_dir, extra_bases):
        cand = os.path.abspath(os.path.join(base, want_dir) if base else want_dir)
        if os.path.isdir(cand):
            target = cand
            break
    if not target:
        return []                               # 目录不存在：没有候选，别乱猜
    low = prefix.lower()
    found_dirs: list = []
    found_files: list = []
    entries = _listdir(target)
    if not entries:
        return []
    for name in entries:
        if name.startswith("."):
            continue
        if low and not name.lower().startswith(low):
            continue
        full = os.path.join(target, name)
        shown = dir_part + name
        if os.path.isdir(full):
            found_dirs.append(shown + "/")
        elif name.lower().endswith(".json"):
            # 忽略后缀：候选给不带 .json 的名字（读写时后端会自动补回来）
            found_files.append(shown[: -len(".json")])
        if len(found_dirs) + len(found_files) >= limit:
            break
    return found_dirs + found_files


def suggest_domains(file_part: str, base_dir: str | None = None,
                    extra_bases=()) -> list:
    """给 ``文件::`` 后面那半截用的域名补全：那个文件里有哪些域。"""
    return domains(file_part, base_dir, extra_bases)

# 正在解析的文件栈（防环）。用 ContextVar 而不是模块级 set：
# 后端是并发的，两个请求同时求值不能互相干扰。
_STACK: ContextVar[tuple] = ContextVar("genshin_external_stack", default=())

# 本次求值里遇到的「文件互相引用」（环）记录：[(被重入的文件, 正在读它的文件)]
# 后端求值完取走，随 /api/evaluate 的 warnings 回给前端提示（用户要求：环上按 0 算，
# 但要在界面上说清楚）。
_CYCLES: ContextVar[object] = ContextVar("genshin_external_cycles", default=None)


def begin() -> None:
    """开始一次求值的环记录（后端在 evaluate 前调用）。"""
    _CYCLES.set([])


def take_cycles() -> list:
    """取走本次求值记录到的环，并清空。"""
    found = _CYCLES.get()
    _CYCLES.set(None)
    return list(found or [])


def _note_cycle(reentered: str, reader: str) -> None:
    found = _CYCLES.get()
    if found is None:
        _CYCLES.set([(reentered, reader)])
        return
    if (reentered, reader) not in found:
        found.append((reentered, reader))

# 缓存：{(绝对路径, mtime, size): (域名字列表, {角色: {名字: 值}})}
# 文件改了 mtime 就变，缓存自然失效；条目数＝用户实际引用过的工程文件数。
_CACHE: dict = {}


def clear_cache() -> None:
    """清空缓存（测试用；正常使用靠 mtime 失效）。"""
    _CACHE.clear()
    _DIR_CACHE.clear()


# 目录列表缓存：{(目录, mtime): [名字…]}。补全每敲一个字都要列一次目录，
# 目录没变就没必要反复 os.listdir（文件多的时候这一下就是几毫秒）。
_DIR_CACHE: dict = {}


def _listdir(target: str) -> list:
    """列目录（按 mtime 缓存；目录变了才会重新列）。"""
    try:
        stat = os.stat(target)
    except OSError:
        return []
    key = (target, stat.st_mtime_ns)
    hit = _DIR_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        entries = sorted(os.listdir(target))
    except OSError:
        return []
    if len(_DIR_CACHE) > 128:               # 别无限涨
        _DIR_CACHE.clear()
    _DIR_CACHE[key] = entries
    return entries


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
    """读并求值一个工程文件：``(域名字列表, {域: {out::名字: 值}})``。读不到就是空。

    文件之间**互相引用**（A→B→A）时，只切断"再往下读"这一步：被重入的那个文件
    仍然**照常求值自己的 out::**（它自己的面板 / 变量卡声明跟环没关系），
    所以不会因为环就变成 0。被切断的那次结果**不进缓存**，免得把 0 记死。
    """
    full = resolve(path, base_dir, extra_bases)
    if not full:
        return ([], {})
    try:
        stat = os.stat(full)
    except OSError:
        return ([], {})
    # 已经在解析栈里 → 这次不再往下跟外部域（否则死循环），但仍解析它自己
    follow = full not in _STACK.get()
    if not follow:
        stack = _STACK.get()
        _note_cycle(full, stack[-1] if stack else "")
    key = (full, stat.st_mtime_ns, stat.st_size)
    if follow:
        hit = _CACHE.get(key)
        if hit is not None:
            return hit
    hit = _read_file(full, follow)
    if follow:
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


def _read_file(full: str, follow: bool = True) -> tuple:
    """把一个工程文件求值，返回 ``(域列表, {域: {out::名字: 值}})``。

    ``follow=False``（说明这个文件已经在上层解析里出现过）时**不跟它的外部域**：
    只算它自己的声明，避免无限递归 —— 但自己的 ``out::`` 照样算出来。
    """
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
        graph.skip_external = not follow
        # 这个文件里的「外部域」再写相对路径时，基准是**它自己所在的目录**
        # （不然嵌套引用的相对路径会按外层工程或进程目录解析，链一多就断）
        graph.base_dir = os.path.dirname(full)
        graph.extra_bases = []
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

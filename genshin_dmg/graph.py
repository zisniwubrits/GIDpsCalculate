# -*- coding: utf-8 -*-
"""节点图模型与求值（纯逻辑，不依赖 UI）。

模型：

* 每张卡片是一个节点（``GraphNode``），左入右出；乘法类节点 1 个输入，
  加法节点输入个数可变（1~12）。
* 从输出端口拖到输入端口即连线（``Link``）；末端「★结果」节点只有 1 个输入，
  计算时从它反向溯源求值。
* 每个节点维护三元组 ``(未暴击, 暴击, 期望)``；暴击区节点负责暴击率/暴伤。
* 未接入「结果」的节点不参与最终结果，但同样会算出并返回自身输出，便于对照。
* 「变量」卡片定义全局变量（``名称 = 表达式``），「★结果」卡片可把三元组
  分别命名为变量，两者一起构成 :func:`Graph.evaluate` 返回的变量表。

工程 JSON 与 tkinter 版**完全兼容**（``version / app / zoom / name / nodes / links``）。
"""

from __future__ import annotations

import re

from genshin_dmg import external as _external
from genshin_dmg import nodes as _nodes
from genshin_dmg.expr import (
    NS_JOIN,
    NS_SEP,
    SUB_IN,
    SUB_OUT,
    SUB_OWN,
    demangle,
    env_key,
    fmt_num,
    is_sub_ns,
    parse_sub_ns,
    plain_num,
    qualify,
    to_bool,
    valid_var_name,
)
from genshin_dmg.nodes import (
    NODE_TYPES,
    RESULT_VAR_KEYS,
    field_specs,
    node_schema,
)

__all__ = ["GraphNode", "Link", "Graph", "infer_roles"]

# 卡片/域的默认尺寸（与前端 web/src/model.ts 的 EST_W/EST_H、ROLE_W/ROLE_H 对齐）
EST_W, EST_H = 300.0, 210.0
ROLE_W, ROLE_H = 560.0, 380.0


def infer_roles(nodes) -> dict:
    """按**几何位置**推断每张卡属于哪个域：``{节点 id: 角色名}``。

    为什么要它：工程 JSON 里原来不存 ``role``（前端每次按"卡片中心落在哪个域里、
    小区域优先"现算），所以后端单独读一个工程文件时（跨文件的「外部域」就是这样）
    根本不知道哪张卡属于谁 —— 域内变量卡里写的 ``out::x`` 会落到全局去，读不到。
    这里用同一套规则补上：卡片中心落在域框内，多个域命中时取面积最小的那个。
    """
    boxes = []
    for node in nodes:
        fields = getattr(node, "fields", {}) or {}
        if "role_name" not in fields:
            continue                     # 不是域容器
        name = str(fields.get("role_name") or "").strip()
        if not name:
            continue
        w, h = (node.size[0], node.size[1]) if getattr(node, "size", None) else (ROLE_W, ROLE_H)
        x, y = node.pos
        boxes.append((node.id, x, y, float(w), float(h), name))
    out: dict = {}
    for node in nodes:
        if "role_name" in (getattr(node, "fields", {}) or {}):
            continue                     # 容器自身不属于任何域
        w, h = (node.size[0], node.size[1]) if getattr(node, "size", None) else (EST_W, EST_H)
        cx = node.pos[0] + float(w) / 2
        cy = node.pos[1] + float(h) / 2
        best = None
        for bid, bx, by, bw, bh, name in boxes:
            if cx < bx or cx > bx + bw or cy < by or cy > by + bh:
                continue
            if best is None or bw * bh < best[0]:
                best = (bw * bh, name)
        if best:
            out[node.id] = best[1]
    return out


def _valid_role(role) -> str:
    """角色名规范化：非法（空 / 含 ``::`` / 含 ``__`` / 非标识符）时返回空串。

    空串表示「不属于任何角色」，等价于全局作用域。角色名必须是**单个**名字
    （``雷神``），不能再套一层命名空间。
    """
    t = str(role or "").strip()
    if not t or NS_JOIN in t or "::" in t:
        return ""
    return t if valid_var_name(t) == t else ""


def _self_referential(expr: str, name: str) -> bool:
    """这条定义是不是"自己掺自己"（预设写法 ``X = own::X + in::X``）。

    判定：右值里出现了 ``own::名字``，或者把**名字本身**当值用（裸 ``X`` / ``::X``）。
    这种定义的值是合成结果（自身 + 拐），**不能**当作自己的属性值 —— 否则
    ``own::X`` 会把自己算进去（用户报的 ``own::month_dmg`` 含拐就是这条）。

    注意 ``X = in::X``（只收别人给的、不掺自身）**不算**自指：那是"我的属性就等于
    收进来的这份"，自身值就是它；面板里这么写是常见用法（有测试锁着）。
    """
    e = str(expr or "")
    if not e:
        return False
    bare = re.escape(name)
    return bool(
        re.search(r"own\s*::\s*%s\b" % bare, e)
        or re.search(r"::\s*%s\b" % bare, e)
        or re.search(r"(?<![\w:])%s(?!\s*::)" % bare, e)
    )


def split_var_line(line: str):
    """把「变量」卡片里的一行拆成 ``(名称, 表达式)``；不是定义行则返回 None。

    认 ``=`` / ``：`` / ``:`` 三种分隔符，跳过空行与 ``#`` 注释。
    解析定义（``_parse_var_cards``）与显示「本卡定义了哪些变量」（``var_card_names``）
    共用这一份规则，免得两处口径漂移。
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    for sep in ("=", "：", ":"):
        if sep in line:
            name, _, expr = line.partition(sep)
            name = name.strip()
            if not name:
                return None
            return name, expr.strip()
    return None


class GraphError(ValueError):
    """图结构 / 求值错误（环路、无结果卡片、字段非法…）。"""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class GraphNode:
    """一张卡片。"""

    __slots__ = ("id", "type", "pos", "size", "font_size", "inputs", "fields",
                 "collapsed", "role")

    def __init__(self, id, type, pos=(40.0, 60.0), size=None, font_size=None,
                 inputs=None, fields=None, collapsed=False, role=""):
        if type not in NODE_TYPES:
            raise GraphError("未知卡片类型: %s" % type)
        self.id = str(id)
        self.type = type
        self.pos = [float(pos[0]), float(pos[1])]
        self.size = self._norm_size(size)
        self.font_size = float(font_size) if font_size else None
        self.inputs = self._norm_inputs(inputs)
        self.fields = self._coerce(fields)
        # 折叠只是界面状态（前端只显示卡片类型），但属于工程 JSON 的一部分：
        # 存在这里是为了 /api/evaluate 回传的规范化图不丢字段。
        self.collapsed = to_bool(collapsed)
        # 这张卡片属于哪个「角色」命名空间：由**前端按位置**判定后放进求值载荷
        # （工程 JSON 不存，位置随时能重算）。名字非法时按"不属于任何角色"处理。
        self.role = _valid_role(role)

    @staticmethod
    def _norm_size(size):
        """卡片自定义尺寸（拖拽放大）；非法值退化为自动尺寸。"""
        try:
            w, h = float(size[0]), float(size[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return None
        if w <= 0 or h <= 0:
            return None
        return [w, h]

    def _norm_inputs(self, value):
        """输入端口数：完全由卡片类型决定（不再支持运行时扩展）。

        旧工程文件里若写了别的端口数（历史上只有加法卡片能改，且实际扩不出可用端口），
        这里一律按类型定义归一化，避免出现连不上的多余端口。
        """
        del value
        return int(NODE_TYPES[self.type]["inputs"])

    def _coerce(self, fields):
        """按字段类型规范化取值：check→bool，text/textbox/combo→str，num/pct→str。"""
        src = fields if isinstance(fields, dict) else {}
        out = {}
        for f in field_specs(self.type):
            key, kind = f["key"], f["kind"]
            val = src.get(key, f["default"])
            if kind == "check":
                out[key] = to_bool(val)
            elif val is None:
                out[key] = ""
            elif kind in ("text", "textbox", "combo"):
                out[key] = str(val)
            elif isinstance(val, str):
                out[key] = val
            else:
                out[key] = str(val)
        return out

    # -- 便捷读取 ---------------------------------------------------------
    @property
    def schema(self) -> dict:
        return node_schema(self.type)

    @property
    def title(self) -> str:
        return NODE_TYPES[self.type]["title"]

    def getter(self):
        """compute / factor 用的取值器。

        字段**留空**时用「角色面板」兜底：把该字段对应的面板宏（atk / crit_rate /
        res_shred …，定义在本角色命名空间里）加起来当值 —— 这是"面板化"的核心规则；
        字段写了值就以卡片为准。当前变量表里已经含有角色命名空间与拐力叠加的结果。
        """
        def get(key):
            raw = self.fields.get(key)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                v = _nodes.panel_value(self.type, key)
                if v is not None:
                    return v
            return raw
        return get

    def result_var_names(self) -> list:
        """结果卡片的三个变量名（顺序：未暴击 / 暴击 / 期望）。"""
        return [valid_var_name(self.fields.get(k)) for k in RESULT_VAR_KEYS]

    def to_dict(self) -> dict:
        return dict(
            id=self.id, type=self.type,
            pos=[float(self.pos[0]), float(self.pos[1])],
            size=(list(self.size) if self.size else None),
            font_size=self.font_size,
            inputs=int(self.inputs),
            fields=dict(self.fields),
            collapsed=bool(self.collapsed),
            # 属于哪个域：前端本来就按几何位置算好并随求值载荷发过来，存进文件后
            # 后端单独读这个工程（跨文件的「外部域」）也能知道域内卡片归谁。
            # 老文件没有这个键 → 读的时候按几何位置补（见 infer_roles）。
            role=self.role or "",
        )


class Link:
    """一条连线：``src`` 的输出接到 ``dst`` 的第 ``port`` 个输入。"""

    __slots__ = ("src", "dst", "port")

    def __init__(self, src, dst, port=0):
        self.src = str(src)
        self.dst = str(dst)
        self.port = int(port)

    def to_dict(self) -> dict:
        return dict(src=self.src, dst=self.dst, port=int(self.port))

    def __repr__(self):                                    # pragma: no cover
        return "Link(%s -> %s.in%d)" % (self.src, self.dst, self.port)


# ---------------------------------------------------------------------------
# 图
# ---------------------------------------------------------------------------
class Graph:
    """一整张画布：节点 + 连线 + 变量求值。"""

    def __init__(self, nodes=None, links=None, zoom: float = 1.0, name: str = ""):
        self.nodes: dict = {}
        self.links: list = []
        self.zoom = self._norm_zoom(zoom)
        self.name = str(name or "")
        for nd in nodes or []:
            node = nd if isinstance(nd, GraphNode) else GraphNode(**nd)
            self.nodes[node.id] = node
        for l in links or []:
            link = l if isinstance(l, Link) else Link(**l)
            if link.src in self.nodes and link.dst in self.nodes:
                self.links.append(link)
        self.variables: dict = {}
        # 当前工程所在目录：解析「外部域」卡片的相对路径用（前端在载荷的 dir 里给）
        self.base_dir: str = ""
        # 额外要试的基准目录（服务端塞进来的"上次打开/保存的目录"等）
        self.extra_bases: list = []
        # 命名卡片的惰性取值表（每次求值重建）与环路栈
        self._cardvars: dict | None = None
        self._card_stack: set = set()
        # 拐力：{目标角色: {面板宏: 加总值}}（每次求值由 buff_sources 重算）
        self.buffs: dict = {}
        # 拐力生效后的面板值 {目标角色: {面板宏: 自身+拐力}}，用于**覆盖式**注入
        # （覆盖而不是相加，保证不管注入几次都不会重复计算）
        self._buff_totals: dict = {}
        # 拐力统计（给「角色面板」弹窗）：{角色: {"out": [...], "in": [...]}}
        self._buff_stats: dict = {}
        # 用户显式声明过 `out::X = ...` 的全名键（这些不做派生覆盖）
        self._user_sub_ns: set = set()
        # 「自身值」的权威记录：``角色__名字 -> 用户自己写的那个值``。
        #
        # 为什么单独存：面板里写 ``X = own::X + in::X``（预设写法）时，普通名 ``X``
        # 最终会变成"自身 + 拐"；``own::X`` 的兜底如果再读普通名，就会把拐力也算进
        # "自身"里（用户报的 own::month_dmg 累加了 in:: 就是这条）。这里记下定义
        # 那一刻算出来的值，``own::`` 只认它。
        self._own_values: dict = {}
        # 同一个域里同名 ``out::`` 的**逐条贡献**：``out 全名键 -> {owner: 值}``。
        #
        # 用户口径：一个角色域里有两张变量卡都写 ``out::atk = 5``，对面收到的
        # ``in::atk`` 应该是 10（求和），而不是"后写的覆盖前面的"。
        # ``owner`` 是"哪张卡的第几行"，所以同一张卡被解析两轮（变量卡本来就会解析
        # 两轮）时是**覆盖自己那份**，不会把一行算两次。
        self._out_contrib: dict = {}
        # 普通名里"只是 out:: 兜底来的"那些（同名 out:: 累加时要跟着刷新，见 _record_out）
        self._out_defaulted: set = set()
        # 当时算不出来、等拐力就绪后再补算的定义（引用了 in::/own:: 等）
        self._deferred: list = []

    # -- 基础 -------------------------------------------------------------
    @staticmethod
    def _norm_zoom(value) -> float:
        try:
            z = float(value)
        except (TypeError, ValueError):
            return 1.0
        return max(0.25, min(2.5, z))

    def add(self, node: GraphNode) -> GraphNode:
        self.nodes[node.id] = node
        return node

    def remove(self, nid: str) -> None:
        self.nodes.pop(nid, None)
        self.links = [l for l in self.links if l.src != nid and l.dst != nid]

    def connect(self, src: str, dst: str, port: int = 0) -> None:
        """连线（同一输入端口只保留最后一条，与画布行为一致）。"""
        if src == dst or src not in self.nodes or dst not in self.nodes:
            return
        self.disconnect(dst, port)
        self.links.append(Link(src, dst, port))

    def disconnect(self, dst: str, port: int) -> None:
        self.links = [l for l in self.links
                      if not (l.dst == dst and l.port == int(port))]

    def input_count(self, nid: str) -> int:
        node = self.nodes[nid]
        return int(node.inputs)

    def link_src(self, dst: str, port: int):
        for l in self.links:
            if l.dst == dst and l.port == int(port):
                src = self.nodes.get(l.src)
                if src is not None and self._is_ns(src):
                    continue        # 角色/武器之间的是「拐力箭头」，不是数据连线
                return l.src
        return None

    # -- 拐力（角色卡 → 角色卡 的面板叠加）----------------------------------
    def buff_sources(self, base_vars: dict) -> dict:
        """``{目标角色: {对外项名字: 加总值}}``：所有「角色/武器卡 → 角色卡」箭头带来的拐力。

        规则（用户确认）：多来源**相加**；**不传递**（源角色只拿它**自己声明过的
        ``out::``**，不把它收到的拐力再传下去）；**只有 ``out::`` 才给出去** ——
        面板里的普通项与卡片字段本身都不发拐力。

        源的两种形态：
        * 角色 / 武器卡：读它本工程的 ``out::`` 声明；
        * 「外部域」卡：读**另一个工程文件**里那个域声明过的 ``out::``（见
          :mod:`genshin_dmg.external`，只读、有环检测与 mtime 缓存）。
        """
        out: dict = {}
        for link in self.links:
            src = self.nodes.get(link.src)
            dst = self.nodes.get(link.dst)
            if src is None or dst is None:
                continue
            if not (self._is_ns(dst) and not self._is_weapon(dst)):
                continue                        # 目标只能是角色（武器不收拐）
            role_to = _valid_role(dst.fields.get("role_name"))
            if not role_to:
                continue
            if self._is_external(src):
                # 跨文件：名字与值都来自那个文件，不需要 role_from
                grants = out.setdefault(role_to, {})
                for macro, val in self._external_grants(src).items():
                    if val:
                        grants[macro] = grants.get(macro, 0.0) + float(val)
                continue
            if not self._is_ns(src):
                continue                        # 源＝角色 / 武器 / 外部域
            role_from = _valid_role(src.fields.get("role_name"))
            if not role_from or role_from == role_to:
                continue
            grants = out.setdefault(role_to, {})
            for macro in self._out_names(base_vars, role_from):
                val = self.role_out_value(base_vars, role_from, macro)
                if val:
                    grants[macro] = grants.get(macro, 0.0) + val
        return out

    # -- 外部域（跨文件读拐力）------------------------------------------------
    @staticmethod
    def _is_external(node) -> bool:
        """这张卡是不是「外部域」（按 schema 标记，别在求值里硬编码类型名）。"""
        return bool(NODE_TYPES.get(node.type, {}).get("external_domain"))

    def _external_grants(self, node) -> dict:
        """外部域卡读到的 ``{名字: 值}``（同一次求值里只读一次盘）。"""
        cache = getattr(self, "_ext_grants", None)
        if cache is None:
            cache = self._ext_grants = {}
        if node.id not in cache:
            cache[node.id] = _external.out_values(
                str(node.fields.get("ext_file") or ""),
                str(node.fields.get("ext_role") or ""),
                self.base_dir,
                self.extra_bases,
            )
        return cache[node.id]

    def _external_domains(self, node) -> list:
        """外部域卡指向的那个工程文件里有哪些域（前端据此藏「里面的域」那一栏）。"""
        return _external.domains(str(node.fields.get("ext_file") or ""),
                                 self.base_dir, self.extra_bases)

    @staticmethod
    def _out_names(base_vars: dict, role: str) -> list:
        """这个角色**显式声明过**的对外项名字（``out::名字`` 的那些）。

        拐力只看这些名字 —— 面板里的普通项（``atk`` / ``atk_pct`` …）是"自己用的
        属性表"，不写 ``out::`` 就不给出去（用户口径）。
        """
        prefix = role + NS_JOIN + SUB_OUT + NS_JOIN
        out: list = []
        for key in base_vars:
            if not key.startswith(prefix):
                continue
            nm = key[len(prefix):]
            if NS_JOIN in nm or nm in out:
                continue                    # 其它子命名空间的键 / 重复
            out.append(nm)
        return out

    def _pinned_own(self, env: dict, role: str, name: str) -> float:
        """取"自身值"的**唯一入口**（严格不含拐）。

        优先级：
          1. ``_own_values``：用户在面板 / 变量卡里给自己写的那个值（定义那一刻的）；
          2. ``角色::own::X``：显式写法的键；
          3. **否则 0**。

        第 3 条是刻意的（用户口径：``own::`` 不论如何都不计入 ``in::`` 的拐）：
        普通名 ``X`` 会被预设写法 ``X = own::X + in::X`` 合成成"自身 + 拐"，
        如果拿它当兜底，``own::X`` 就会自己把自己算进去 —— 这正是
        ``own::month_dmg`` 读出 30（含拐）的原因。
        """
        if not role:
            return 0.0
        pinned = self._own_values.get(env_key(qualify(name, role)))
        if pinned is not None:
            return float(pinned)
        # 只认本角色的 own:: 键：**不回退到普通名/全局名** —— 普通名会被预设写法
        # 合成成"自身 + 拐"，全局名还会串到别的角色去（用户口径：own 不论如何
        # 都不计入 in:: 的拐）。
        return self._first_value(env, (
            env_key(qualify("%s%s%s" % (SUB_OWN, NS_SEP, name), role)),
        ))

    def role_own_value(self, base_vars: dict, role: str, macro: str) -> float:
        """某角色**自身**的值（严格不含拐）——见 :meth:`_pinned_own` 的说明。

        用户口径：``own::`` 不论如何都不计入 ``in::`` 的拐。
        """
        return self._pinned_own(base_vars, role, macro)

    @staticmethod
    def role_out_value(base_vars: dict, role: str, macro: str) -> float:
        """某角色**对外提供**的值（拐力箭头用它）。

        口径（用户确认）：**只有显式声明的 ``out::名字`` 才给出去** ——
        角色面板里那些既没有 ``own::`` 也没有 ``out::`` 的普通项（以及卡片字段本身）
        **不会**自动变成拐力。以前是"没写 out:: 就默认等于自身值"，那会让每个角色
        只要写了面板属性就在偷偷给拐，跟"面板只是自己用的属性表"这个直觉冲突。
        """
        return Graph._first_value(base_vars, (
            env_key(qualify("%s%s%s" % (SUB_OUT, NS_SEP, macro), role)),
        ))

    @staticmethod
    def _first_value(vars_: dict, keys, default: float = 0.0) -> float:
        for key in keys:
            if key in vars_:
                val = vars_[key]
                return float(val() if callable(val) else val)
        return default

    @staticmethod
    def role_panel_value(base_vars: dict, role: str, macro: str) -> float:
        """（兼容旧调用）某角色面板里某个宏的自身值。"""
        return Graph.role_own_value(base_vars, role, macro)

    @staticmethod
    def _is_ns(node) -> bool:
        """是不是命名空间容器（角色 / 武器）。"""
        return bool(NODE_TYPES.get(node.type, {}).get("role_card"))

    @staticmethod
    def _is_weapon(node) -> bool:
        return bool(NODE_TYPES.get(node.type, {}).get("weapon_card"))

    def _apply_role_panels(self, env: dict) -> None:
        """把每张角色卡「面板」字段里的宏登记成该角色的变量（``角色::宏``）。

        优先级：**角色卡上的面板覆盖同名变量** —— 它是"面板"的正主（右键弹窗里编辑的
        就是它）。认固定词表里的宏名；另外允许 ``out::名字`` 这种**自定义对外项**
        （名字合法即可，用于"面板外拐"：本角色没有该属性，但对外提供这份拐力）。
        值支持算式（在本角色作用域里求值）。

        **武器没有面板**：它的 ``panel`` 字段一律忽略（只在变量卡里写 ``out::``）。
        """
        for node in self.nodes.values():
            if not self._is_ns(node):
                continue
            if self._is_weapon(node):
                continue                    # 武器只有 out::（写在变量卡里），没有面板
            role = _valid_role(node.fields.get("role_name"))
            if not role:
                continue
            token = _nodes.use_env(self.scoped_env(node, env, role=role))
            try:
                for index, line in enumerate((node.fields.get("panel") or "").splitlines()):
                    parsed = split_var_line(line)
                    if parsed is None:
                        continue
                    kind, _explicit, macro = parse_sub_ns(parsed[0].strip())
                    if kind == SUB_IN:
                        continue                    # in:: 派生，写它无意义
                    if macro not in _nodes.PANEL_MACRO_KEYS:
                        # 不在词表里：只有 ``out::名字`` 才收（自定义对外项），
                        # 光写一个陌生名字仍然忽略（避免面板变成"什么都能定义"的变量卡）
                        if kind != SUB_OUT or not _nodes.valid_panel_custom_name(macro):
                            continue
                    own_key = env_key(qualify(macro, role))
                    key = own_key
                    if kind == SUB_OUT:
                        key = env_key(qualify("%s%s%s" % (SUB_OUT, NS_SEP, macro), role))
                    try:
                        value = _nodes.eval_field(parsed[1])
                    except ValueError:
                        # 同变量卡片：可能是引用了 in::/own::（拐力算完才有）→ 等会儿补算
                        self._defer("panel", key, parsed[1], node, role=role, name=macro,
                                    out=(kind == SUB_OUT), owner="p%d:%d" % (id(node), index))
                        continue                    # 算不出来的行忽略
                    if kind == SUB_OUT:
                        # 同名 out:: 在一个域里可以写多行 / 多张卡：求和后输出
                        #（普通名若不是真定义，也一起刷新成总数）
                        value = self._record_out(
                            env, key, own_key, "p%d:%d" % (id(node), index), value
                        )
                    else:
                        env[key] = value
                    # 记下"用户自己写的那个值"：own:: 只认它、且**先写的为准**
                    # （`atk_pct = 10` 与 `out::atk_pct = 40` 并存时，自身值仍是 10）；
                    # 自指定义不算（见 `_self_referential`）。
                    own_key = env_key(qualify(macro, role))
                    if own_key not in self._own_values and not _self_referential(parsed[1], macro):
                        self._own_values[own_key] = value
                    if kind == SUB_OUT:
                        self._user_sub_ns.add(key)
                        if own_key not in env:
                            env[own_key] = value
                    # 同一张角色卡里的后续面板项要能引用刚定义的（如 atk_pct = atk * 0.1）
                    _nodes.use_env(self.scoped_env(node, env, role=role))
            finally:
                _nodes.reset_env(token)

    def _apply_sub_namespaces(self, own_vars: dict) -> None:
        """给每个角色补上 ``own`` / ``out`` / ``in`` 三个子命名空间（消除歧义）。

        * ``角色::名字``      = **生效值**（自己写的那个值）
        * ``角色::own::名字`` = **纯自身**（不含拐）
        * ``角色::out::名字`` = **对外提供的**：**只有显式写过 ``out::名字`` 才有值**，
          否则是 0（用户口径：面板里的普通项与卡片字段本身都不发拐力）
        * ``角色::in::名字``  = **收进来的拐**（多来源相加；没被拐就是 0）

        名字取"本角色自己定义过的变量" ∪ "固定词表的面板宏"，所以任意变量都支持子命名空间
        （没声明 ``out::`` 的变量 ``out`` / ``in`` 都是 0）。
        ``own_vars`` 是**拐力生效前**的变量表（自身值），由调用方在合适的时机拍快照。
        """
        roles = set()
        weapons = set()
        for node in self.nodes.values():
            if not self._is_ns(node):
                continue
            role = _valid_role(node.fields.get("role_name"))
            if not role:
                continue
            roles.add(role)
            if self._is_weapon(node):
                weapons.add(role)        # 武器：只给 own:: / out::，**不给 in::**
        for role in roles:
            prefix = role + NS_JOIN
            names = set(_nodes.PANEL_MACRO_KEYS)
            for key in own_vars:
                if not key.startswith(prefix):
                    continue
                rest = key[len(prefix):]
                if rest.startswith(SUB_OUT + NS_JOIN):
                    # 用户 out:: 声明的**自定义名字**同样算一个名字（任意名字都能拐）
                    rest = rest[len(SUB_OUT) + len(NS_JOIN):]
                elif NS_JOIN in rest:
                    continue                    # 其它子命名空间键（重复调用时跳过）
                names.add(rest)
            grants = self.buffs.get(role) or {}
            # 收到拐的名字（含自定义名字）也要有 in::/own::/out:: 三个键
            names.update(grants)
            for name in names:
                # 自身值只认"用户定义那一刻的值"（_pinned_own）：预设写法
                # `X = own::X + in::X` 会把普通名合成成"自身+拐"，这里再读普通名
                # 就会把拐力算进自身 —— 用户口径：own:: 不计入 in::。
                own = self._pinned_own(own_vars, role, name)
                inc = float(grants.get(name, 0.0) or 0.0)
                out_key = prefix + SUB_OUT + NS_JOIN + name
                # 只有显式写过 `out::名字 = ...` 才对外提供；否则 0（不发拐力）
                out_val = (
                    float(own_vars.get(out_key, 0.0) or 0.0)
                    if out_key in self._user_sub_ns
                    else 0.0
                )
                self.variables[prefix + SUB_OWN + NS_JOIN + name] = own
                self.variables[out_key] = out_val
                if role not in weapons:
                    # 武器不支持 in::（它只往外给）——写 in:: 会显示"未定义变量"
                    self.variables[prefix + SUB_IN + NS_JOIN + name] = inc

    # -- 延迟补算（引用了 in::/own:: 这类要等拐力才知道的名字）-----------------
    def _defer(self, kind: str, key: str, expr: str, node, role=None, name=None,
               out=False, owner=None) -> None:
        """记下一条"当时算不出来"的定义，等拐力/子命名空间就绪后补算。

        ``name`` 是这条定义的名字（不含角色前缀）：补算成功后要把结果记进
        "自身值"那张表（``_own_values``），``own::名字`` 才有正确的自身值。
        ``out`` / ``owner`` 给 ``out::`` 用：补算成功后仍按"逐条贡献"累加（见
        :meth:`_accumulate_out`），不能直接覆盖。
        """
        self._deferred.append(
            dict(kind=kind, key=key, expr=expr, nid=node.id, role=role, name=name,
                 out=out, owner=owner)
        )

    def _accumulate_out(self, env: dict, out_key: str, owner: str, value: float) -> float:
        """把一条 ``out::名字 = 值`` 记进贡献表，返回**该名字当前的总数**并写进 ``env``。

        用户口径：同一个域里多张卡各写一行 ``out::atk = 5``，对面应该收到 10。
        ``owner`` 标明"哪张卡的第几行"，所以同一张卡被重复解析（变量卡解析两轮、
        补算再来一遍）时只覆盖自己那条，不会重复累加。
        """
        terms = self._out_contrib.setdefault(out_key, {})
        terms[owner] = float(value)
        total = float(sum(terms.values()))
        env[out_key] = total
        return total

    def _record_out(self, env: dict, out_key: str, plain_key: str, owner: str,
                    value: float) -> float:
        """记一条 ``out::`` 并同步"普通名"。

        普通名的默认口径是"没单独定义自身值时，对外值同时就是自身值"。既然对外值
        现在会随同名多行**累加**，这个默认值也得跟着刷新 —— 否则两张卡各写
        ``out::atk = 5`` 时，``out::atk`` 是 10 而普通名 ``atk`` 还停在 5。
        只要普通名被**真正的定义**占着（不是靠 out:: 兜底来的），就不动它。
        """
        total = self._accumulate_out(env, out_key, owner, value)
        if not plain_key:
            return total
        if plain_key not in env:
            self._out_defaulted.add(plain_key)
        if plain_key in self._out_defaulted:
            env[plain_key] = total
        return total

    def _retry_deferred(self, env: dict, locked=()) -> None:
        """把延迟的定义再算一遍：能算出来的写进 env，仍算不出的继续留着。

        为什么需要：变量卡片与角色面板都在**拐力算完之前**解析，而 `in::` / `own::`
        这些名字要等拐力就绪才存在。早先的实现是直接跳过 —— 表现为"写了 `in::` 的定义
        莫名其妙没生效"（下游报「未定义变量」）。
        """
        left = []
        # 补算前把 own:: 的键存一份：这些键的语义是"用户自己写的自身值"，
        # 补算只该更新普通名，绝不能反过来把 own:: 改成合成值（见 _pinned_own）。
        own_keys = {k: v for k, v in env.items() if is_sub_ns(demangle(k)) and "__own__" in k}
        for item in self._deferred:
            node = self.nodes.get(item["nid"])
            if node is None or item["key"] in locked:
                continue
            role = item.get("role") or ""
            token = _nodes.use_env(self.scoped_env(node, env, role=item["role"]))
            try:
                value = _nodes.eval_field(item["expr"])
            except ValueError:
                left.append(item)               # 还是算不出来：保留，下次求值再试
                continue
            finally:
                _nodes.reset_env(token)
            # 只更新普通名：own:: 的键在 _apply_sub_namespaces 里按"定义时的自身值"写，
            # 这里不要碰它（原来把合成值写进去，会盖住 own:: 的语义）。
            # out:: 例外：同名多行要**累加**（见 _accumulate_out），不能直接覆盖。
            if item.get("out"):
                value = self._accumulate_out(
                    env, item["key"], item.get("owner") or ("d" + str(item["nid"])), value
                )
            else:
                env[item["key"]] = value
            # 定义拖到补算才成功时（如面板写 `X = in::X`），在这里补记"自身值"
            # （先写的为准、自指不算）；否则 own::X 会读成 0
            role = item.get("role") or ""
            name = item.get("name")
            if role and name and not _self_referential(item["expr"], name):
                pin = env_key(qualify(name, role))
                if pin not in self._own_values:
                    self._own_values[pin] = value
        # 还原 own:: 键（补算可能间接动到它们；语义上它们只由"定义那一刻的值"决定）
        env.update(own_keys)
        self._deferred = left

    def _finalize_buffs(self, own: dict) -> None:
        """按 ``own``（拐力生效前的自身值）重算：拐力、生效值、子命名空间。

        * 拐力来源值取 ``own``（保证"不传递"）
        * **面板属性一律不自动计算**（用户口径）：`角色::X` 只来自你自己写的定义
          （变量卡 / 面板）；拐力只以 `in::X` 的形式提供，要用就自己写
          ``X = own::X + in::X``（拖一张变量卡进角色区域时程序会自动填这段预设代码）
        * 顺带刷新 ``own`` / ``out`` / ``in`` 三个子命名空间
        """
        self.buffs = self.buff_sources(own)
        self._buff_stats = self.buff_stats(own)
        # 面板属性不写进变量表（不自动计算）：拐力只通过 in:: 暴露
        self._apply_sub_namespaces(own)

    def buff_stats(self, base_vars: dict) -> dict:
        """给「角色面板」弹窗用的拐力统计：``{角色: {"out": [...], "in": [...]}}``。

        每条含 ``macro / label / value / role``：OUT 里的 role 是**目标角色**，
        IN 里的 role 是**来源角色**。
        """
        labels = {k: label for k, label, _feed in _nodes.PANEL_MACROS}
        out: dict = {}
        for link in self.links:
            a = self.nodes.get(link.src)
            b = self.nodes.get(link.dst)
            if a is None or b is None:
                continue
            if not (self._is_ns(b) and not self._is_weapon(b)):
                continue
            rb = _valid_role(b.fields.get("role_name"))
            if not rb:
                continue
            if self._is_external(a):
                # 外部域：来源角色名就用它在那个文件里的域名字（统计里能看到是谁给的）
                ra = str(a.fields.get("ext_role") or "").strip() or "外部域"
                grants = list(self._external_grants(a).items())
            elif self._is_ns(a):
                ra = _valid_role(a.fields.get("role_name"))
                if not ra or ra == rb:
                    continue
                grants = [(macro, self.role_out_value(base_vars, ra, macro))
                          for macro in self._out_names(base_vars, ra)]
            else:
                continue
            for macro, val in grants:
                if not val:
                    continue
                row = dict(macro=macro, label=labels.get(macro, macro), value=float(val))
                out.setdefault(ra, {"out": [], "in": []})["out"].append(dict(row, role=rb))
                out.setdefault(rb, {"out": [], "in": []})["in"].append(dict(row, role=ra))
        return out

    def buff_edges(self) -> list:
        """拐力箭头列表 ``[(源角色名, 目标角色名)]``（给报告/自检用）。"""
        out = []
        for link in self.links:
            src = self.nodes.get(link.src)
            dst = self.nodes.get(link.dst)
            if src is None or dst is None or src.type != "role" or dst.type != "role":
                continue
            a = _valid_role(src.fields.get("role_name"))
            b = _valid_role(dst.fields.get("role_name"))
            if a and b and a != b:
                out.append((a, b))
        return out

    def result_node(self):
        """第一张「★结果」卡片（没有则 None）。"""
        for nid, node in self.nodes.items():
            if node.type == "result":
                return nid
        return None

    def warnings(self) -> list:
        out = []
        if self.result_node() is None:
            out.append("没有「结果」卡片：请加一张 ★结果 卡片并把链条接到它上面")
        elif "crit" not in self.chain_types():
            out.append("结果链上没有暴击区：当前显示的是未暴击数值")
        dup = self.duplicate_card_names()
        if dup:
            out.append("卡片名重复（只有第一张生效）：%s" % "、".join(dup))
        return out

    # -- 卡片命名（`卡片名::输出`）-----------------------------------------
    # 命名卡片的输出也能当变量用：裸名 = 期望值，`卡片名::暴击` / `::未暴击` 取分量。
    # 值必须**惰性**求（引用它的卡片可能在它上游），所以存 callable，
    # 由 eval_expr 解析到名字时回调；_card_stack 负责挡住间接环路。
    CARD_PARTS = ("未暴击", "暴击", "期望")

    def card_var_name(self, node) -> str:
        """卡片名（**全局扁平**，不套角色前缀）；没命名 / 名字非法 → 空串。

        卡片名是用户自己起的标签（「是谁的乘区」），本身就该是唯一的，
        再套一层角色前缀会变成 ``雷神::雷神基础`` 这种别扭写法。
        """
        return valid_var_name(node.fields.get("card_name"))

    def _card_getter(self, nid: str, idx: int):
        def get():
            if nid in self._card_stack:
                raise ValueError("卡片名引用成环：%s" % self.nodes[nid].title)
            self._card_stack.add(nid)
            try:
                v = self.node_output(nid)
            finally:
                self._card_stack.discard(nid)
            return float(v[idx])
        return get

    def _card_vars(self) -> dict:
        """``{内部键: 惰性取值}``：所有命名卡片（每次求值缓存一份）。

        卡片名重复时**第一张生效**（按画布上的节点顺序），并在 warnings 里提示。
        """
        if self._cardvars is not None:
            return self._cardvars
        out: dict = {}
        for nid, node in self.nodes.items():
            if node.type == "role":
                continue
            name = self.card_var_name(node)
            if not name:
                continue
            key = env_key(name)
            if key in out:
                continue                    # 重名：第一张生效
            out[key] = self._card_getter(nid, 2)                    # 裸名 = 期望
            for idx, part in enumerate(self.CARD_PARTS):
                out[env_key("%s%s%s" % (name, NS_SEP, part))] = self._card_getter(nid, idx)
        self._cardvars = out
        return out

    def duplicate_card_names(self) -> list:
        """重复的卡片名（第一张生效，其余被忽略）—— 用于给用户提示。"""
        seen, dup = set(), []
        for node in self.nodes.values():
            if node.type == "role":
                continue
            name = self.card_var_name(node)
            if not name:
                continue
            if name in seen and name not in dup:
                dup.append(name)
            seen.add(name)
        return dup

    # -- 求值 -------------------------------------------------------------
    def scoped_env(self, node, env=None, role=None) -> dict:
        """求值某节点的字段时用的变量表，优先级从高到低：

        1. 本角色自己的变量（裸名，覆盖同名全局变量）
        2. 全局变量 / 结果三元组 / 赋值变量（内部键与裸名都在）
        3. **别人拐给本角色的面板加成**（加到同名面板项上，多来源已在 buff_sources 里相加）
        4. 命名卡片的输出（``卡片名`` / ``卡片名::暴击``…，最低优先）
        """
        base = self.variables if env is None else env
        out = dict(base)
        # role 参数：解析**角色卡自己的面板**时用（角色卡自身没有 .role，
        # 但它显然该按"本角色"的作用域取值，否则面板项之间互相引用都看不见）
        role = getattr(node, "role", "") if role is None else role
        if role:
            prefix = role + NS_JOIN
            for key, val in base.items():
                if key.startswith(prefix):
                    out[key[len(prefix):]] = val        # 就近：本角色覆盖同名全局
            # 子命名空间（own / out / in）的就近别名：不管 base 是什么表都补上，
            # 否则"第二轮解析变量"时（base 是空表）变量定义里引用不到 in::/own::
            for key, val in self.variables.items():
                if key.startswith(prefix) and is_sub_ns(demangle(key)):
                    out[key[len(prefix):]] = val
            # 本角色的面板宏（**含没有收到拐的**）：第二轮解析时 base 是空表，
            # 这些宏也得看得到（收到拐的已被上面的 _buff_totals 覆盖成生效值）
            for macro in _nodes.PANEL_MACRO_KEYS:
                key = prefix + macro
                if key in self.variables and macro not in out:
                    out[macro] = self.variables[key]
        for key, getter in self._card_vars().items():
            out.setdefault(key, getter)
        return out

    def _compute(self, node, fn):
        """在该节点的作用域里执行 fn（读字段时才拿得到正确的变量表）。"""
        token = _nodes.use_env(self.scoped_env(node))
        try:
            return fn()
        finally:
            _nodes.reset_env(token)

    def node_output(self, nid: str, _stack=None):
        """计算某节点的 ``(未暴击, 暴击, 期望)`` 三元组（含上游）。"""
        if nid not in self.nodes:
            raise GraphError("节点不存在: %s" % nid)
        _stack = _stack or set()
        if nid in _stack:
            raise GraphError("检测到环路：%s" % self.nodes[nid].title)
        node = self.nodes[nid]
        spec = NODE_TYPES[node.type]
        ins = []
        for port in range(self.input_count(nid)):
            src = self.link_src(nid, port)
            if src is None:
                ins.append((0.0, 0.0, 0.0))
            else:
                ins.append(self.node_output(src, _stack | {nid}))
        # 每张卡都在**自己的作用域**里读字段（递归上来时也一样，谁读字段谁决定作用域）
        return self._compute(node, lambda: spec["compute"](node.getter(), ins))

    def factor_text(self, nid: str):
        """该卡片的「本卡系数」文案（无 factor 时返回 None）。"""
        node = self.nodes[nid]
        spec = NODE_TYPES[node.type]
        fac = spec.get("factor")
        if not fac:
            return None
        try:
            return str(self._compute(node, lambda: fac(node.getter(), [])))
        except Exception:                                   # pragma: no cover
            return None

    def chain_types(self) -> list:
        """结果链上（含结果卡片）所有节点类型，按上游优先顺序。"""
        res = self.result_node()
        seen, types = set(), []

        def walk(nid):
            if nid in seen or nid not in self.nodes:
                return
            seen.add(nid)
            for p in range(self.input_count(nid)):
                s = self.link_src(nid, p)
                if s:
                    walk(s)
            types.append(self.nodes[nid].type)

        if res:
            walk(res)
        return types

    def evaluate(self) -> dict:
        """整图求值：返回变量表、每个节点的输出与最终结果。

        变量求值的顺序（AGENTS.md §5 与此保持一致，改这里就要同步改那里）：

        1. 解析「变量」卡片的定义；
        2. 登记「★结果」卡片的三元组变量；
        3. 登记「赋值变量」卡片的变量（显式连线赋值，同名以它为准）；
        4. 「变量」卡片再解析一轮（可引用 2/3 登记的变量，如 ``秒伤 = 期望伤害/时间``；
           ``locked`` 保证它们不会被同名的变量卡定义覆盖）；
        5. 登记「角色 / 武器」卡片的面板宏（``角色::宏``，同名覆盖全局变量）；
        6. 拐力与生效值：算出 ``own:: / out:: / in::`` 子命名空间。拐力来源取「拐力生效前」
           的自身值快照（``own``），所以拐力不会顺着拐力继续传下去；
        7. 补算第 1/4 轮里引用了 ``in:: / own::`` 而当时算不出来的定义，并刷新子命名空间；
        8. 变量表就绪后逐个节点求值（没接进结果链的卡片也会算出自身输出）。

        同名优先级：赋值变量卡 > ★结果卡三元组 > 变量卡片；角色面板宏覆盖同名全局变量。
        带角色归属的结果卡 / 赋值卡登记进该角色的命名空间（``角色::名字``）。
        """
        env: dict = {}
        # 关键：表达式求值必须**始终对着 env 这个自建环境**（而不是会在中途被替换的
        # self.variables）。以前用 `use_env(self.scoped_env(...))` 时，self.variables
        # 会被换成 dict(env) 的**副本**，于是面板/变量卡里引用了 in::/own:: 的定义被
        # 补算后写进了副本，最终节点求值却还对着旧值 —— 表现是 `X = own::X + in::X`
        # 里的 X 停在"只有拐"的那一版。这里记录一次，随用随恢复。
        token = _nodes.use_env(env)
        self._cardvars = None           # 每次求值重建命名卡片的惰性表
        self._card_stack = set()
        self._deferred = []             # 本次求值里"当时算不出来"的定义（稍后补算）
        self._user_sub_ns = set()       # 本次求值里用户显式声明的 out:: 键
        self._own_values = {}           # 本次求值里各名字的"自身值"（own:: 只认它）
        self._out_contrib = {}          # 本次求值里同名 out:: 的逐条贡献（求和用）
        self._out_defaulted = set()     # 普通名里"只是 out:: 兜底来的"
        # 清掉上一次求值的运行时缓存：同一个 Graph 对象可能被反复求值
        # （测试里就是这样），残留的拐力值会串进新一轮的解析
        self.buffs = {}
        self._buff_totals = {}
        self._buff_stats = {}
        # 变量表也要清：否则 scoped_env 会读到上一次求值残留的子命名空间值，
        # 让 "X = own::X + in::X" 这类定义在第一轮"假成功"（拿到过期值）而不再补算
        self.variables = {}
        try:
            # 第一轮：只解析「变量」卡片的定义
            self._parse_var_cards(env)
            # 第二轮：登记结果卡片三元组变量
            rvars = self._result_vars()
            if rvars:
                env.update(rvars)
            # 第三轮：登记赋值变量卡片登记的变量
            svars = self._assigned_vars()
            if svars:
                env.update(svars)
            if rvars or svars:
                # 变量卡片可以引用结果 / 赋值变量，但不能覆盖它们（locked）
                self._parse_var_cards(env, locked=set(rvars) | set(svars))
                env.update(rvars)
                env.update(svars)               # 赋值卡优先级最高
            self.variables = dict(env)
            # 角色卡自带的面板宏（右键「角色面板…」里编辑的那些）
            self._apply_role_panels(env)
            # **拐力生效前**的快照 = 各变量的"自身值"（own 的来源）
            own = dict(env)
            self.variables = dict(env)
            # 拐力 + 生效值 + 子命名空间（own/out/in）——第二轮解析变量时就能引用它们。
            # 拐力值取 own（不含拐）以保证"不传递"。
            self._finalize_buffs(own)
            if self._deferred:
                # 还有引用了 in::/own:: 这类名字、当时没算出来的定义 → 现在补算一次
                # （子命名空间已就绪）。注意：**不**重算拐力 —— 拐力来源仍取"拐力前的
                # 自身值"快照，否则对外提供的值会跟着收到的拐走，等于变相传递。
                locked = set(rvars) | set(svars)
                self._retry_deferred(env, locked)
                self.variables = dict(env)
                # 用**补算后**的值刷新子命名空间（own:: 要反映你定义的那个值）；
                # 拐力来源不重算（仍是拐力前的快照），所以不会变相传递
                self._apply_sub_namespaces(self.variables)
            # 变量表已就绪，逐个节点求值
            first = self.result_node()
            out = dict(
                ok=False, error=None, result=None,
                # 与「变量表」卡片同源（self.variables），否则拐力写回的值只在表格里看得到；
                # own / out / in 子命名空间不列出（同 variable_rows 的理由）
                variables=[dict(name=demangle(k), value=float(v), text=plain_num(v))
                           for k, v in self.variables.items()
                           if not is_sub_ns(demangle(k))],
                nodes={}, chainTypes=self.chain_types(), warnings=self.warnings(),
                buffStats=self._buff_stats,
            )
            for nid in list(self.nodes):
                out["nodes"][nid] = self._node_result(nid)
            if first is None:
                out["error"] = "没有「结果」卡片"
            else:
                r = out["nodes"][first]
                if r.get("error"):
                    out["error"] = r["error"]
                else:
                    out["ok"] = True
                    out["result"] = dict(
                        nodeId=first,
                        values=r["values"],
                        display=r["display"],
                        boundNames=r.get("boundNames") or [],
                    )
            return out
        finally:
            _nodes.reset_env(token)

    # -- 内部 -------------------------------------------------------------
    def panel_fields(self, node) -> list:
        """本卡**由角色面板兜底**填上的字段标签（给卡片做可见标注）。

        判定与 ``getter()`` 完全一致：字段为空且该字段对应的面板宏有值。
        """
        out = []
        for f in field_specs(node.type):
            field_key = f["key"]
            raw = node.fields.get(field_key)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                if _nodes.panel_value(node.type, field_key) is not None:
                    out.append(f["label"])
        return out

    def _node_result(self, nid: str) -> dict:
        """单个节点的输出描述（前端据此渲染卡片底部）。"""
        node = self.nodes[nid]
        spec = NODE_TYPES[node.type]
        info = dict(type=node.type, title=node.title, factor=None, values=None,
                    isTriple=False, display="", error=None, rows=None,
                    varsText=None, boundNames=[], plain="", plainTriple=[],
                    panelFields=[], buffed=False)
        if node.type == "vartable":
            info["rows"] = self.variable_rows()
            return info
        if spec.get("vars_card"):
            # 只列**本卡片定义**的变量（原来这里打印全局总览，用户要求改掉）；
            # 值取当前生效值 —— 同名可能被结果卡三元组 / 赋值变量卡覆盖，
            # 显示的数值与其它卡片实际用到的保持一致。全局总览看「变量表」卡片。
            # 名字是展示名（角色内的带 角色:: 前缀），查表时换成内部键。
            parts = []
            for name in self.var_card_names(nid):
                value = self.variables.get(env_key(name))
                parts.append("%s=%s" % (name, plain_num(value)) if value is not None
                             else "%s=未解析" % name)
            info["varsText"] = "变量: " + (", ".join(parts) if parts else "(无)")
            return info
        if spec.get("external_domain"):
            # 外部域：值 = 从那个文件读到的 out:: 合计；顺带把"那个文件里有哪些域"
            # 告诉前端（只有一个时前端就把「里面的域」这一栏藏掉，自动用它）。
            grants = self._external_grants(node)
            names = self._external_domains(node)
            info["extDomains"] = names
            total = float(sum(grants.values()))
            info["values"] = dict(noncrit=total, crit=total, expected=total)
            info["plain"] = plain_num(total)
            info["plainTriple"] = [plain_num(total)] * 3
            label = str(node.fields.get("ext_role") or "").strip()
            if not label and len(names) == 1:
                label = names[0]
            parts = ["输出 %s" % fmt_num(total)]
            if not grants:
                parts.append("没读到 out::" if names or label else "没读到文件")
            elif label:
                parts.append(label)
            info["display"] = " ｜ ".join(parts)
            return info
        if spec.get("no_output"):
            return info
        try:
            v = self.node_output(nid)
        except Exception as e:
            info["error"] = str(e)
            info["display"] = "输出: 错误(%s)" % e
            return info
        values = dict(noncrit=float(v[0]), crit=float(v[1]), expected=float(v[2]))
        info["values"] = values
        # 纯数字字符串：便于前端「复制输出」后直接粘贴到其它输入框
        info["plain"] = plain_num(v[0])
        info["plainTriple"] = [plain_num(v[0]), plain_num(v[1]), plain_num(v[2])]
        info["isTriple"] = (abs(v[1] - v[0]) > 1e-9 or abs(v[2] - v[0]) > 1e-9)
        info["factor"] = self.factor_text(nid)
        parts = []
        if info["factor"]:
            parts.append(info["factor"])
        if node.type == "setvar":
            # 赋值变量卡：底部显示「赋值 变量名 = 当前值」，并回传绑定的变量名
            # （展示名带角色前缀：卡片在 雷神 容器里就登记成 雷神::名字）
            raw = valid_var_name(node.fields.get("var_name"))
            name = qualify(raw, node.role) if raw else ""
            info["boundNames"] = [name] if name else []
            if name:
                parts.append("赋值 %s = %s"
                             % (name, fmt_num(v[self.setvar_pick(node)])))
            else:
                parts.append("未指定变量名")
        elif info["isTriple"]:
            parts.append("未暴击 %s ｜ 暴击 %s ｜ 期望 %s"
                         % (fmt_num(v[0]), fmt_num(v[1]), fmt_num(v[2])))
        else:
            if node.type == "result":
                names = [qualify(t, node.role)
                         for t in node.result_var_names() if t]
                info["boundNames"] = names
                if names:
                    parts.append("结果 %s ｜ 变量 %s" % (fmt_num(v[0]), " / ".join(names)))
                else:
                    parts.append("结果 %s" % fmt_num(v[0]))
            else:
                parts.append("输出 %s" % fmt_num(v[0]))
        info["display"] = " ｜ ".join(parts)
        # 可见标注：哪些字段是"留空→吃角色面板"的、本角色是否收了拐
        # （用户反馈"没看到吃拐"，这两个标记就是让人一眼看出来的）
        if not spec.get("no_output") and not spec.get("vars_card"):
            info["panelFields"] = self._compute(node, lambda: self.panel_fields(node))
            info["buffed"] = bool(self.buffs.get(node.role))
        return info

    def variable_rows(self) -> list:
        """变量表的正文行：名称 / 数值（无变量时给一行占位提示）。

        名称是**展示名**（内部键 ``雷神__攻击力`` 还原成 ``雷神::攻击力``）。
        ``own`` / ``out`` / ``in`` 子命名空间不在这里列（否则每个变量会多出三行），
        它们只在表达式里可用；明细看角色的「角色面板…」弹窗。
        """
        rows = [[demangle(name), plain_num(val)]
                for name, val in self.variables.items()
                if not is_sub_ns(demangle(name))]
        return rows or [["（暂无变量）", ""]]

    def var_card_names(self, nid: str) -> list:
        """该「变量」卡片定义了哪些变量（**展示名**：角色内的自动带 ``角色::`` 前缀）。"""
        node = self.nodes.get(nid)
        if node is None or node.type != "var":
            return []
        names: list = []
        for line in (node.fields.get("defs") or "").splitlines():
            parsed = split_var_line(line)
            if not parsed:
                continue
            name = valid_var_name(parsed[0])
            if not name:
                continue
            display = qualify(name, node.role)
            if display not in names:
                names.append(display)
        return names

    def _parse_var_cards(self, env: dict, locked=()) -> dict:
        """把「变量」卡片里的 ``名称 = 表达式`` 逐行解析进 env（就地更新并返回）。

        * 卡片在某个角色容器里时，定义的变量自动带前缀（``雷神__攻击力``）；
          行里**显式**写 ``胡桃::攻击力`` 则按显式的前缀走。
        * ``locked`` 中的名字（来自结果卡片的三元组变量）不会被变量卡片覆盖。
        """
        for node in self.nodes.values():
            if node.type != "var":
                continue
            token = _nodes.use_env(self.scoped_env(node, env))
            try:
                for index, line in enumerate((node.fields.get("defs") or "").splitlines()):
                    parsed = split_var_line(line)
                    if parsed is None:
                        continue
                    name = valid_var_name(parsed[0])
                    if not name:
                        continue                # 名字非法（含 __ 等）→ 不定义
                    kind, explicit_role, base = parse_sub_ns(name)
                    role_here = explicit_role or node.role
                    if kind == SUB_IN:
                        # in:: 是"收进来的"，由拐力派生出来；用户写它没有意义 → 忽略
                        continue
                    if kind:
                        name = base
                    display = qualify(name, role_here)
                    key = env_key(display)
                    if kind == SUB_OUT:
                        # 显式声明"对外提供的值"：用独立的全名键存（拐力箭头读它）
                        key = env_key(qualify("%s%s%s" % (SUB_OUT, NS_SEP, base), role_here))
                    if key in locked:
                        continue
                    try:
                        value = _nodes.eval_field(parsed[1])
                    except ValueError:
                        # 引用 `in::`/`own::` 这类要等拐力算完才知道的名字时，
                        # 这里必然算不出来 —— 记下来等拐力就绪后补算（见 _retry_deferred）
                        self._defer("var", key, parsed[1], node, role=role_here, name=base,
                                    out=(kind == SUB_OUT), owner="v%d:%d" % (id(node), index))
                        continue
                    if kind == SUB_OUT:
                        # 同一域里多张卡/多行 out:: 同名 → 求和（用户口径）
                        value = self._record_out(
                            env, key, env_key(display), "v%d:%d" % (id(node), index), value
                        )
                    else:
                        env[key] = value
                    # 记下"用户自己写的那个值"：own:: 只认它、先写的为准、自指不算
                    own_key = env_key(qualify(base, role_here))
                    if (kind != SUB_OUT and own_key not in self._own_values
                            and not _self_referential(parsed[1], base)):
                        self._own_values[own_key] = value
                    if kind == SUB_OUT:
                        self._user_sub_ns.add(key)
                    # 同一张卡的后续行要能引用刚定义的变量：重建一次作用域
                    _nodes.use_env(self.scoped_env(node, env))
            finally:
                _nodes.reset_env(token)
        return env

    def _result_vars(self) -> dict:
        """把「★结果」卡片的三元组登记为变量，返回 ``{变量名: 数值}``。"""
        out: dict = {}
        for nid, node in self.nodes.items():
            if node.type != "result":
                continue
            names = node.result_var_names()
            if not any(names):
                continue
            try:
                v = self.node_output(nid)
            except Exception:
                continue                        # 结果链尚未接好：本次不登记
            for name, val in zip(names, v):
                if name:
                    out[env_key(qualify(name, node.role))] = float(val)
        return out

    @staticmethod
    def setvar_pick(node) -> int:
        """赋值变量卡「取值」下拉对应的分量下标（未暴击 0 / 暴击 1 / 期望 2）。"""
        try:
            return _nodes.SETVAR_PICKS.index(node.fields.get("pick") or "期望")
        except ValueError:                      # 旧存档 / 脏值 → 按默认「期望」
            return 2

    def _assigned_vars(self) -> dict:
        """把「赋值变量」卡片登记的变量，返回 ``{变量名: 数值}``。

        卡片是纯汇点（无输出端口），按图形顺序求值：后面的卡片可以引用前面刚登记的变量。
        变量名为空 / 非法，或上游还没接好（比如引用了未定义变量）时，本次不登记。
        """
        out: dict = {}
        for nid, node in self.nodes.items():
            if node.type != "setvar":
                continue
            name = valid_var_name(node.fields.get("var_name"))
            if not name:
                continue
            try:
                v = self.node_output(nid)
            except Exception:
                continue
            out[env_key(qualify(name, node.role))] = float(v[self.setvar_pick(node)])
        return out

    # -- 工程存档 ---------------------------------------------------------
    def to_dict(self) -> dict:
        """导出整张画布（节点类型/位置/尺寸/参数 + 连线）为可序列化字典。"""
        return dict(
            version=1,
            app="GenshinDamageCalc",
            zoom=self.zoom,
            name=self.name,
            nodes=[self.nodes[nid].to_dict() for nid in self.nodes],
            links=[l.to_dict() for l in self.links],
        )

    @classmethod
    def from_dict(cls, data) -> "Graph":
        """从字典恢复画布；非法/未知内容会被安全跳过（兼容旧工程文件）。"""
        if not isinstance(data, dict):
            raise GraphError("工程数据格式不正确")
        g = cls(zoom=data.get("zoom", 1.0), name=data.get("name") or "")
        # 当前工程所在目录（前端在求值载荷里给）：解析「外部域」的相对路径用
        g.base_dir = str(data.get("dir") or "")
        idmap: dict = {}
        for i, nd in enumerate(data.get("nodes") or []):
            if not isinstance(nd, dict):
                continue
            old = nd.get("id")
            t = nd.get("type")
            if t not in NODE_TYPES:
                continue
            pos = nd.get("pos") or [40, 60]
            try:
                pos = (float(pos[0]), float(pos[1]))
            except (TypeError, ValueError, IndexError):
                pos = (40.0, 60.0)
            nid = str(old) if old else "n%d" % (i + 1)
            node = GraphNode(
                id=nid, type=t, pos=pos, size=nd.get("size"),
                font_size=nd.get("font_size"), inputs=nd.get("inputs"),
                fields=nd.get("fields"), collapsed=nd.get("collapsed"),
                role=nd.get("role"),
            )
            g.add(node)
            if old is not None:
                idmap[str(old)] = nid
        # 老工程文件没存 role：按几何位置补一遍（域内卡片才知道自己归谁，
        # 否则域里变量卡写的 out:: 会落到全局，跨文件读拐力就什么都读不到）
        if any(not (n.role or "") for n in g.nodes.values()):
            for nid, role in infer_roles(list(g.nodes.values())).items():
                node = g.nodes.get(nid)
                if node is not None and not (node.role or ""):
                    node.role = role
        for l in data.get("links") or []:
            if not isinstance(l, dict):
                continue
            s = idmap.get(str(l.get("src")), str(l.get("src")))
            d = idmap.get(str(l.get("dst")), str(l.get("dst")))
            if s in g.nodes and d in g.nodes:
                try:
                    port = int(l.get("port", 0))
                except (TypeError, ValueError):
                    port = 0
                g.links.append(Link(s, d, port))
        return g

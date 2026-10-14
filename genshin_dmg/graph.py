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

__all__ = ["GraphNode", "Link", "Graph"]


def _valid_role(role) -> str:
    """角色名规范化：非法（空 / 含 ``::`` / 含 ``__`` / 非标识符）时返回空串。

    空串表示「不属于任何角色」，等价于全局作用域。角色名必须是**单个**名字
    （``雷神``），不能再套一层命名空间。
    """
    t = str(role or "").strip()
    if not t or NS_JOIN in t or "::" in t:
        return ""
    return t if valid_var_name(t) == t else ""


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
                if src is not None and src.type == "role":
                    continue        # 角色卡之间的是「拐力箭头」，不是数据连线
                return l.src
        return None

    # -- 拐力（角色卡 → 角色卡 的面板叠加）----------------------------------
    def buff_sources(self, base_vars: dict) -> dict:
        """``{目标角色: {面板宏: 加总值}}``：所有「角色卡 → 角色卡」箭头带来的拐力。

        规则（用户确认）：多来源**相加**；**不传递** —— 源角色的值只取它自己的面板
        （本角色命名空间优先，其次全局），不把它收到的拐力再传下去。
        """
        out: dict = {}
        for link in self.links:
            src = self.nodes.get(link.src)
            dst = self.nodes.get(link.dst)
            if src is None or dst is None:
                continue
            if src.type != "role" or dst.type != "role":
                continue                        # 只认角色卡之间的箭头
            role_from = _valid_role(src.fields.get("role_name"))
            role_to = _valid_role(dst.fields.get("role_name"))
            if not role_from or not role_to or role_from == role_to:
                continue
            grants = out.setdefault(role_to, {})
            names = list(_nodes.PANEL_MACRO_KEYS)
            out_prefix = role_from + NS_JOIN + SUB_OUT + NS_JOIN
            for key in base_vars:
                if key.startswith(out_prefix):
                    nm = key[len(out_prefix):]
                    if NS_JOIN not in nm and nm not in names:
                        names.append(nm)        # out:: 里写的自定义名字
            for macro in names:
                val = self.role_out_value(base_vars, role_from, macro)
                if val:
                    grants[macro] = grants.get(macro, 0.0) + val
        return out

    @staticmethod
    def role_own_value(base_vars: dict, role: str, macro: str) -> float:
        """某角色**自身**的面板值（own:: 优先，其次基础名，最后全局；没有则 0）。

        用于"生效值 = 自身 + 收进来的"，所以**不**读 out::（对外值可能被单独声明）。
        """
        return Graph._first_value(base_vars, (
            env_key(qualify("%s%s%s" % (SUB_OWN, NS_SEP, macro), role)),
            env_key(qualify(macro, role)),
            env_key(macro),
        ))

    @staticmethod
    def role_out_value(base_vars: dict, role: str, macro: str) -> float:
        """某角色**对外提供**的值（拐力箭头用它）：显式声明的 out:: 优先，否则就是自身。"""
        out = Graph._first_value(base_vars, (
            env_key(qualify("%s%s%s" % (SUB_OUT, NS_SEP, macro), role)),
        ), default=None)
        if out is not None:
            return out
        return Graph.role_own_value(base_vars, role, macro)

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

    def _apply_role_panels(self, env: dict) -> None:
        """把每张角色卡「面板」字段里的宏登记成该角色的变量（``角色::宏``）。

        优先级：**角色卡上的面板覆盖同名变量** —— 它是"面板"的正主（右键弹窗里编辑的
        就是它）。只认固定词表里的宏名，值支持算式（在本角色作用域里求值）。
        """
        for node in self.nodes.values():
            if node.type != "role":
                continue
            role = _valid_role(node.fields.get("role_name"))
            if not role:
                continue
            token = _nodes.use_env(self.scoped_env(node, env, role=role))
            try:
                for line in (node.fields.get("panel") or "").splitlines():
                    parsed = split_var_line(line)
                    if parsed is None:
                        continue
                    kind, _explicit, macro = parse_sub_ns(parsed[0].strip())
                    if macro not in _nodes.PANEL_MACRO_KEYS:
                        continue                    # 只认固定词表
                    if kind == SUB_IN:
                        continue                    # in:: 派生，写它无意义
                    own_key = env_key(qualify(macro, role))
                    key = own_key
                    if kind == SUB_OUT:
                        key = env_key(qualify("%s%s%s" % (SUB_OUT, NS_SEP, macro), role))
                    try:
                        value = _nodes.eval_field(parsed[1])
                    except ValueError:
                        # 同变量卡片：可能是引用了 in::/own::（拐力算完才有）→ 等会儿补算
                        self._defer("panel", key, parsed[1], node, role=role)
                        continue                    # 算不出来的行忽略
                    env[key] = value
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

        * ``角色::名字``      = **生效值**（自身 + 收进来的拐，保持原有行为）
        * ``角色::own::名字`` = **纯自身**（不含拐）
        * ``角色::out::名字`` = **对外提供的**（= 自身，"宏就是对外值"）
        * ``角色::in::名字``  = **收进来的拐**（多来源相加；没被拐就是 0）

        名字取"本角色自己定义过的变量" ∪ "固定词表的面板宏"，所以任意变量都支持子命名空间
        （只有面板宏会被箭头拐到，其余变量的 ``in`` 就是 0）。
        ``own_vars`` 是**拐力生效前**的变量表（自身值），由调用方在合适的时机拍快照。
        """
        roles = set()
        for node in self.nodes.values():
            if node.type == "role":
                role = _valid_role(node.fields.get("role_name"))
                if role:
                    roles.add(role)
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
                own = float(own_vars.get(prefix + name, 0.0) or 0.0)
                inc = float(grants.get(name, 0.0) or 0.0)
                out_key = prefix + SUB_OUT + NS_JOIN + name
                if out_key in self._user_sub_ns and out_key in own_vars:
                    # 用户显式声明过 `out::X = ...`（"我对外提供这么多"）→ 以他写的为准
                    out_val = float(own_vars.get(out_key, 0.0) or 0.0)
                else:
                    out_val = own                   # 默认：宏就是对外值
                self.variables[prefix + SUB_OWN + NS_JOIN + name] = own
                self.variables[out_key] = out_val
                self.variables[prefix + SUB_IN + NS_JOIN + name] = inc

    # -- 延迟补算（引用了 in::/own:: 这类要等拐力才知道的名字）-----------------
    def _defer(self, kind: str, key: str, expr: str, node, role=None) -> None:
        """记下一条"当时算不出来"的定义，等拐力/子命名空间就绪后补算。"""
        self._deferred.append(dict(kind=kind, key=key, expr=expr, nid=node.id, role=role))

    def _retry_deferred(self, env: dict, locked=()) -> None:
        """把延迟的定义再算一遍：能算出来的写进 env，仍算不出的继续留着。

        为什么需要：变量卡片与角色面板都在**拐力算完之前**解析，而 `in::` / `own::`
        这些名字要等拐力就绪才存在。早先的实现是直接跳过 —— 表现为"写了 `in::` 的定义
        莫名其妙没生效"（下游报「未定义变量」）。
        """
        left = []
        for item in self._deferred:
            node = self.nodes.get(item["nid"])
            if node is None or item["key"] in locked:
                continue
            token = _nodes.use_env(self.scoped_env(node, env, role=item["role"]))
            try:
                value = _nodes.eval_field(item["expr"])
            except ValueError:
                left.append(item)               # 还是算不出来：保留，下次求值再试
                continue
            finally:
                _nodes.reset_env(token)
            env[item["key"]] = value
        self._deferred = left

    def _finalize_buffs(self, own: dict) -> None:
        """按 ``own``（拐力生效前的自身值）重算：拐力、生效值、子命名空间。

        * 拐力来源值取 ``own``（保证"不传递"）
        * **不再自动相加**：自身写了的以自身为准；只有没写自身时才把拐力（in）写进去。
          想要"自身 + 拐"就自己写 ``X = own::X + in::X``
        * 顺带刷新 ``own`` / ``out`` / ``in`` 三个子命名空间
        """
        self.buffs = self.buff_sources(own)
        self._buff_stats = self.buff_stats(own)
        self._buff_totals = {}
        for role, grants in self.buffs.items():
            self._buff_totals[role] = {
                macro: self.role_own_value(own, role, macro) + extra
                for macro, extra in grants.items()
            }
        for role, totals in self._buff_totals.items():
            for macro, total in totals.items():
                # 只写全名键（角色::宏名），不往全局塞裸名，免得拐力漏给别的角色；
                # **自身已定义就跳过**（不再自动相加），totals 此时就等于 in
                key = env_key(qualify(macro, role))
                if key not in self.variables:
                    self.variables[key] = total
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
            if a is None or b is None or a.type != "role" or b.type != "role":
                continue
            ra = _valid_role(a.fields.get("role_name"))
            rb = _valid_role(b.fields.get("role_name"))
            if not ra or not rb or ra == rb:
                continue
            names = list(_nodes.PANEL_MACRO_KEYS)
            out_prefix = ra + NS_JOIN + SUB_OUT + NS_JOIN
            for key in base_vars:
                if key.startswith(out_prefix):
                    nm = key[len(out_prefix):]
                    if NS_JOIN not in nm and nm not in names:
                        names.append(nm)
            for macro in names:
                val = self.role_out_value(base_vars, ra, macro)
                if not val:
                    continue
                row = dict(macro=macro, label=labels.get(macro, macro), value=val)
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
            for macro, extra in (self._buff_totals.get(role) or {}).items():
                if macro in out:
                    continue        # 自身已定义 → 以自身为准（要"自身+拐"自己写 own:: + in::）
                out[macro] = extra  # 自身没写 → 吃拐（此时 extra 就等于 in）
                out[prefix + macro] = extra
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

        变量求值分三轮（前两轮与 tkinter 版一致）：

        1. 先解析「变量」卡片的定义；
        2. 把「★结果」卡片的三元组登记为变量；
        3. 把「赋值变量」卡片的变量登记进来（显式连线赋值，同名以它为准）；
           然后让「变量」卡片再解析一轮（可引用这些变量，如 ``秒伤 = 期望伤害/时间``）。

        同名优先级：赋值变量卡 > ★结果卡三元组 > 变量卡片。
        """
        env: dict = {}
        token = _nodes.use_env(env)
        self._cardvars = None           # 每次求值重建命名卡片的惰性表
        self._card_stack = set()
        self._deferred = []             # 本次求值里"当时算不出来"的定义（稍后补算）
        self._user_sub_ns = set()       # 本次求值里用户显式声明的 out:: 键
        # 清掉上一次求值的运行时缓存：同一个 Graph 对象可能被反复求值
        # （测试里就是这样），残留的拐力值会串进新一轮的解析
        self.buffs = {}
        self._buff_totals = {}
        self._buff_stats = {}
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
            if self.buffs:
                # 有拐力：带着拐力（与子命名空间）重跑一轮变量登记，
                # 让目标角色里以面板项写的算式也能看到"含拐"的值
                env = {}
                self._parse_var_cards(env)
                rvars = self._result_vars()
                if rvars:
                    env.update(rvars)
                svars = self._assigned_vars()
                if svars:
                    env.update(svars)
                if rvars or svars:
                    self._parse_var_cards(env, locked=set(rvars) | set(svars))
                    env.update(rvars)
                    env.update(svars)
                self._apply_role_panels(env)
                own = dict(env)                 # 第二轮解析出来的自身值
                self.variables = dict(env)
                self._finalize_buffs(own)
            if self._deferred:
                # 还有引用了 in::/own:: 这类名字、当时没算出来的定义 → 现在补算，
                # 再按新的自身值刷新一次拐力（只刷新这一次，不再迭代）
                locked = set(rvars) | set(svars)
                self._retry_deferred(env, locked)
                own = dict(env)
                self.variables = dict(env)
                self._finalize_buffs(own)
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
                for line in (node.fields.get("defs") or "").splitlines():
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
                        self._defer("var", key, parsed[1], node)
                        continue
                    env[key] = value
                    if kind == SUB_OUT:
                        self._user_sub_ns.add(key)
                        # 没另外定义自身值时，对外值同时就是自身值（"宏就是对外值"的默认）
                        base_key = env_key(display)
                        if base_key not in env:
                            env[base_key] = value
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

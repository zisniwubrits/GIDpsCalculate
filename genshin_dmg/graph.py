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
    demangle,
    env_key,
    fmt_num,
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
                return l.src
        return None

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
    def scoped_env(self, node, env=None) -> dict:
        """求值某节点的字段时用的变量表，优先级从高到低：

        1. 本角色自己的变量（裸名，覆盖同名全局变量）
        2. 全局变量 / 结果三元组 / 赋值变量（内部键与裸名都在）
        3. 命名卡片的输出（``卡片名`` / ``卡片名::暴击``…，最低优先）
        """
        base = self.variables if env is None else env
        out = dict(base)
        role = getattr(node, "role", "")
        if role:
            prefix = role + NS_JOIN
            for key, val in base.items():
                if key.startswith(prefix):
                    out[key[len(prefix):]] = val        # 就近：本角色覆盖同名全局
        for key, getter in self._card_vars().items():
            out.setdefault(key, getter)                 # 卡片名优先级最低
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
        try:
            # 第一轮：只解析「变量」卡片的定义
            self._parse_var_cards(env)
            # 第二轮：登记结果卡片三元组变量
            rvars = self._result_vars()
            if rvars:
                env.update(rvars)
            # 第三轮：登记赋值变量卡片的变量
            svars = self._assigned_vars()
            if svars:
                env.update(svars)
            if rvars or svars:
                # 变量卡片可以引用结果 / 赋值变量，但不能覆盖它们（locked）
                self._parse_var_cards(env, locked=set(rvars) | set(svars))
                env.update(rvars)
                env.update(svars)               # 赋值卡优先级最高
            self.variables = dict(env)
            # 变量表已就绪，逐个节点求值
            first = self.result_node()
            out = dict(
                ok=False, error=None, result=None,
                variables=[dict(name=demangle(k), value=float(v), text=plain_num(v))
                           for k, v in env.items()],
                nodes={}, chainTypes=self.chain_types(), warnings=self.warnings(),
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
    def _node_result(self, nid: str) -> dict:
        """单个节点的输出描述（前端据此渲染卡片底部）。"""
        node = self.nodes[nid]
        spec = NODE_TYPES[node.type]
        info = dict(type=node.type, title=node.title, factor=None, values=None,
                    isTriple=False, display="", error=None, rows=None,
                    varsText=None, boundNames=[], plain="", plainTriple=[])
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
        return info

    def variable_rows(self) -> list:
        """变量表的正文行：名称 / 数值（无变量时给一行占位提示）。

        名称是**展示名**（内部键 ``雷神__攻击力`` 还原成 ``雷神::攻击力``）。
        """
        rows = [[demangle(name), plain_num(val)] for name, val in self.variables.items()]
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
                    display = qualify(name, node.role)
                    key = env_key(display)
                    if key in locked:
                        continue
                    try:
                        value = _nodes.eval_field(parsed[1])
                    except ValueError:
                        continue                # 定义失败则忽略该行
                    env[key] = value
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

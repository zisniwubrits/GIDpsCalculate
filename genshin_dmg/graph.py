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
from genshin_dmg.expr import fmt_num, plain_num, to_bool, valid_var_name
from genshin_dmg.nodes import (
    NODE_TYPES,
    RESULT_VAR_KEYS,
    field_specs,
    node_schema,
)

__all__ = ["GraphNode", "Link", "Graph", "MAX_INPUTS"]

MAX_INPUTS = 12
MIN_INPUTS = 1


class GraphError(ValueError):
    """图结构 / 求值错误（环路、无结果卡片、字段非法…）。"""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class GraphNode:
    """一张卡片。"""

    __slots__ = ("id", "type", "pos", "size", "font_size", "inputs", "fields")

    def __init__(self, id, type, pos=(40.0, 60.0), size=None, font_size=None,
                 inputs=None, fields=None):
        if type not in NODE_TYPES:
            raise GraphError("未知卡片类型: %s" % type)
        self.id = str(id)
        self.type = type
        self.pos = [float(pos[0]), float(pos[1])]
        self.size = self._norm_size(size)
        self.font_size = float(font_size) if font_size else None
        self.inputs = self._norm_inputs(inputs)
        self.fields = self._coerce(fields)

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
        spec = NODE_TYPES[self.type]
        if not spec.get("variadic"):
            return int(spec["inputs"])
        if value is None:
            return int(spec["inputs"])
        try:
            n = int(value)
        except (TypeError, ValueError):
            return int(spec["inputs"])
        return max(MIN_INPUTS, min(MAX_INPUTS, n))

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
        """compute / factor 用的取值器。"""
        return lambda key: self.fields.get(key)

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
        return out

    # -- 求值 -------------------------------------------------------------
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
        return spec["compute"](node.getter(), ins)

    def factor_text(self, nid: str):
        """该卡片的「本卡系数」文案（无 factor 时返回 None）。"""
        spec = NODE_TYPES[self.nodes[nid].type]
        fac = spec.get("factor")
        if not fac:
            return None
        try:
            return str(fac(self.nodes[nid].getter(), []))
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

        变量求值分两轮（与 tkinter 版一致）：

        1. 先解析「变量」卡片的定义；
        2. 把「★结果」卡片的三元组登记为变量（同名以结果卡片为准），
           再让「变量」卡片可以引用这些结果变量（如 ``秒伤 = 期望伤害/时间``）。
        """
        env: dict = {}
        token = _nodes.use_env(env)
        try:
            # 第一轮：只解析「变量」卡片的定义
            self._parse_var_cards(env)
            # 第二轮：登记结果卡片三元组变量，并让变量卡片可以引用它们
            rvars = self._result_vars()
            if rvars:
                env.update(rvars)
                self._parse_var_cards(env, locked=set(rvars))
                env.update(rvars)               # 同名以结果卡片为准
            self.variables = dict(env)
            # 变量表已就绪，逐个节点求值
            first = self.result_node()
            out = dict(
                ok=False, error=None, result=None,
                variables=[dict(name=k, value=float(v), text=plain_num(v))
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
                    varsText=None, boundNames=[])
        if node.type == "vartable":
            info["rows"] = self.variable_rows()
            return info
        if spec.get("vars_card"):
            # 变量卡片只显示当前变量总览（内容由 refresh_variables 决定）
            summary = ", ".join("%s=%s" % (k, plain_num(x))
                                for k, x in self.variables.items())
            info["varsText"] = "变量: " + (summary if summary else "(无)")
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
        info["isTriple"] = (abs(v[1] - v[0]) > 1e-9 or abs(v[2] - v[0]) > 1e-9)
        info["factor"] = self.factor_text(nid)
        parts = []
        if info["factor"]:
            parts.append(info["factor"])
        if info["isTriple"]:
            parts.append("未暴击 %s ｜ 暴击 %s ｜ 期望 %s"
                         % (fmt_num(v[0]), fmt_num(v[1]), fmt_num(v[2])))
        else:
            if node.type == "result":
                names = [t for t in node.result_var_names() if t]
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
        """变量表的正文行：名称 / 数值（无变量时给一行占位提示）。"""
        rows = [[name, plain_num(val)] for name, val in self.variables.items()]
        return rows or [["（暂无变量）", ""]]

    def _parse_var_cards(self, env: dict, locked=()) -> dict:
        """把「变量」卡片里的 ``名称 = 表达式`` 逐行解析进 env（就地更新并返回）。

        ``locked`` 中的名字（来自结果卡片的三元组变量）不会被变量卡片覆盖。
        """
        for node in self.nodes.values():
            if node.type != "var":
                continue
            lines = (node.fields.get("defs") or "").splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name, expr = None, None
                for sep in ("=", "：", ":"):
                    if sep in line:
                        name, _, expr = line.partition(sep)
                        break
                if name is None:
                    continue
                name = name.strip()
                if not name or name in locked:
                    continue
                try:
                    value = _nodes.eval_field(expr.strip())
                except ValueError:
                    continue                    # 定义失败则忽略该行
                env[name] = value
                _nodes.use_env(env)             # 后续行可引用前面刚定义的变量
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
                    out[name] = float(val)
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
                fields=nd.get("fields"),
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

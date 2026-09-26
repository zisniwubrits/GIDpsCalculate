# -*- coding: utf-8 -*-
"""
乘区节点编辑器（画布）。

模型：
  * 每张卡片是一个节点，左入右出；乘法类节点 1 个输入，加法节点 2 个输入。
  * 从输出端口拖到输入端口即可连线；点击连线可删除。
  * 末端「结果」节点只有 1 个输入，计算时从它反向溯源求值。
  * 每个节点维护三元组 (未暴击, 暴击, 期望)；暴击区节点负责暴击率/暴伤。
  * 未接入「结果」的节点不参与最终伤害，仅展示自身输出。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from genshin_dmg import damage

BG = "#e9eef3"
ACCENT = "#2f6fa7"
NODE_BG = "#ffffff"
FIELD_BG = "#f7f9fb"


# ---------------------------------------------------------------------------
# 字段解析
# ---------------------------------------------------------------------------
def _num(s: str, d: float = 0.0) -> float:
    """解析数值；支持算式（如 70+30、352+674、200*3），非法则返回 d。"""
    t = (s or "").strip()
    if not t:
        return d
    try:
        return float(t)
    except ValueError:
        pass
    try:
        return _eval_expr(t)      # 复用安全算术求值（支持全角/括号/幂等）
    except ValueError:
        return d


def _pct(s: str, d: float = 0.0) -> float:
    return _num(s, d) / 100.0


def _fmt(x: float) -> str:
    """固定小数位格式化，避免出现科学计数法（如 1.2e+05）。"""
    if abs(x) >= 10000:
        return "{:,.1f}".format(x)
    if abs(x) >= 100:
        return "{:.2f}".format(x)
    if abs(x) >= 1:
        return "{:.3f}".format(x)
    return "{:.4f}".format(x)


def _plain(x: float) -> str:
    """纯数字字符串（无千分位、无科学计数法），便于复制后直接粘贴。"""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    s = "{:.6f}".format(x).rstrip("0").rstrip(".")
    return s if s else "0"


# --- 计算卡用的安全算术求值（不使用 eval）---
_FULLWIDTH = {"，": ",", "×": "*", "÷": "/", "＋": "+", "－": "-", "（）": "()"}


def _eval_expr(text: str) -> float:
    """安全求值算术表达式（支持 + - * / // % ** 与括号）。失败抛 ValueError。"""
    import ast as _ast
    import operator as _op

    t = (text or "").strip()
    for k, v in _FULLWIDTH.items():
        t = t.replace(k, v)
    t = t.replace("（", "(").replace("）", ")")
    t = t.replace(",", "").replace("，", "")
    t = "".join(t.split())          # 去掉空格与换行，便于多行编辑
    if not t:
        raise ValueError("表达式为空")
    ops = {
        _ast.Add: _op.add, _ast.Sub: _op.sub, _ast.Mult: _op.mul,
        _ast.Div: _op.truediv, _ast.FloorDiv: _op.floordiv,
        _ast.Mod: _op.mod, _ast.Pow: _op.pow,
        _ast.USub: _op.neg, _ast.UAdd: _op.pos,
    }
    try:
        tree = _ast.parse(t, mode="eval")
    except SyntaxError:
        raise ValueError("表达式语法错误")

    def ev(node):
        if isinstance(node, _ast.Expression):
            return ev(node.body)
        if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, _ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, _ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.operand))
        raise ValueError("不支持的运算")

    try:
        return float(ev(tree))
    except (ZeroDivisionError, OverflowError) as e:
        raise ValueError(str(e))


# ---------------------------------------------------------------------------
# 节点类型定义
#   inputs : 输入端口数
#   fields : [(key, label, default, kind, extra?)]
#            kind ∈ num / pct / combo / check
#   compute(get, ins) -> (nc, cr, ex)
# ---------------------------------------------------------------------------
def _mul(v, coeff):
    return (v[0] * coeff, v[1] * coeff, v[2] * coeff)


def _t_base(get, ins):
    v = damage.effective_stat(
        _num(get("stat_base"), 1000), _pct(get("stat_big")), _num(get("stat_flat"))
    ) * _pct(get("multiplier"), 2.0)
    return (v, v, v)


def _t_add(get, ins):
    a = ins[0] if len(ins) > 0 else (0, 0, 0)
    b = ins[1] if len(ins) > 1 else (0, 0, 0)
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _t_dmg(get, ins):
    return _mul(ins[0], 1 + _pct(get("dmg_net")))


def _t_res(get, ins):
    return _mul(ins[0], damage.resistance_coefficient(_pct(get("resistance"), 10.0)))


def _t_def(get, ins):
    coeff = damage.defense_coefficient(
        _num(get("char_level"), 90), _num(get("enemy_level"), 90),
        def_reduction=_pct(get("def_reduction")), ignore_def=_pct(get("ignore_def")),
    )
    return _mul(ins[0], coeff)


def _t_crit(get, ins):
    cr = _pct(get("crit_rate"), 50.0)
    cd = _pct(get("crit_damage"), 100.0)
    cr_eff = min(max(cr, 0.0), 1.0)
    nc, _, _ = ins[0]
    return (nc, nc * (1 + cd), nc * (1 + cr_eff * cd))


def _t_amp(get, ins):
    name = _amp_key(get("formula"))
    if name == "无" or get("shield"):
        coeff = 1.0
    else:
        coeff = damage.amplify_for_reaction(
            name, _num(get("em")), _pct(get("amp_bonus")))
    return _mul(ins[0], coeff)


def _t_boost(get, ins):
    return _mul(ins[0], 1 + _pct(get("boost")))


def _root(v):
    return (v, v, v)


def _t_aggravate(get, ins):
    v = damage.aggravate_value(
        get("kind") or "超激化", _num(get("em")),
        enhance_bonus=_pct(get("bonus")), level=int(_num(get("level"), 90)))
    return _root(v)


def _t_transform(get, ins):
    v = damage.transformative_damage(
        get("reaction") or "超载", _num(get("em")),
        level=int(_num(get("level"), 90)), reaction_bonus=_pct(get("bonus")),
        resistance=0.0)
    return _root(v)


def _t_crystal(get, ins):
    return _root(damage.crystallize_shield(
        _num(get("em")), shield_strength=_pct(get("shield_strength"))))


def _attr(get):
    return damage.effective_stat(
        _num(get("stat_base"), 1000), _pct(get("stat_big")), _num(get("stat_flat")))


def _t_month_direct(get, ins):
    v = damage.month_direct(
        get("kind") or "月感电", _attr(get), _pct(get("multiplier"), 2.0),
        elemental_mastery=_num(get("em")), base_boost=_pct(get("base_boost")),
        reaction_bonus=_pct(get("bonus")), resistance=0.0,
        crit=False, boost_multi=1.0)
    return _root(v)


def _t_month_reaction(get, ins):
    v = damage.month_reaction(
        get("kind") or "月感电", elemental_mastery=_num(get("em")),
        base_boost=_pct(get("base_boost")), reaction_bonus=_pct(get("bonus")),
        resistance=0.0, crit=False, boost_multi=1.0, level=int(_num(get("level"), 90)))
    return _root(v)


def _t_star_super(get, ins):
    v = damage.star_superconduct_direct(
        int(_num(get("hits"), 0)), _attr(get), _pct(get("multiplier"), 2.0),
        elemental_mastery=_num(get("em")), base_boost=_pct(get("base_boost")),
        reaction_bonus=_pct(get("bonus")), resistance=0.0,
        crit=False, boost_multi=1.0)
    return _root(v)


def _t_star_swirl(get, ins):
    v = damage.star_swirl_reaction(
        get("subtype") or "风", vortex_count=int(_num(get("vortex"), 1)),
        elemental_mastery=_num(get("em")), base_boost=_pct(get("base_boost")),
        reaction_bonus=_pct(get("bonus")), resistance=0.0,
        crit=False, boost_multi=1.0, level=int(_num(get("level"), 90)))
    return _root(v)


def _t_star_direct(get, ins):
    v = damage.star_swirl_direct(
        _attr(get), _pct(get("multiplier"), 2.0), elemental_mastery=_num(get("em")),
        base_boost=_pct(get("base_boost")), reaction_bonus=_pct(get("bonus")),
        resistance=0.0, crit=False, boost_multi=1.0)
    return _root(v)


def _t_result(get, ins):
    return ins[0] if ins else (0, 0, 0)


def _t_calc(get, ins):
    """计算卡：求输入表达式的数值（无输入端口）。"""
    v = _eval_expr(get("expr"))
    return (v, v, v)


def _t_text(get, ins):
    """纯文本卡片：只用于标注，不参与计算。"""
    return (0.0, 0.0, 0.0)


# --- 拆分开的乘区部件（星/月/剧变 源都可由此组合）---
def _t_attr(get, ins):
    """属性源 = 白值×(1+大增益%)+小增益。"""
    return _root(_attr(get))


def _t_react_base(get, ins):
    """反应基准值源 = 1446.85（95/100 级有修正）。"""
    return _root(damage.react_base(int(_num(get("level"), 90))))


def _t_coeff(get, ins):
    """× 系数（如直伤系数 3 / 反应倍率 1.8 / 0.75）。"""
    return _mul(ins[0], _num(get("coeff"), 1.0))


def _t_mult(get, ins):
    """× 倍率%。"""
    return _mul(ins[0], _pct(get("multiplier"), 200.0))


def _t_base_boost(get, ins):
    """× (1 + 基础提升%)。"""
    return _mul(ins[0], 1 + _pct(get("base_boost")))


def _t_em_gain(get, ins):
    """× (1 + k×EM/(EM+分母) + 增伤%)   —— k=6/分母2000 为星月；16/2000 剧变；5/1200 激化。"""
    em = _num(get("em"))
    k = _num(get("k"), 6.0)
    den = _num(get("denom"), 2000.0)
    bonus = _pct(get("bonus"))
    term = 0.0 if (em + den) == 0 else k * em / (em + den)
    return _mul(ins[0], 1 + term + bonus)



_AMP_OPTS = ["无"]
_AMP_LABEL_TO_KEY: dict = {}
for _k, _v in damage.AMPLIFY_BASE_FACTOR.items():
    # 用“打”字明确方向，并直接显示倍率；如 蒸发·水→火 ×2.0 → “蒸发·水打火 ×2.0”
    _label = "%s ×%.1f" % (_k.replace("→", "打"), _v)
    _AMP_OPTS.append(_label)
    _AMP_LABEL_TO_KEY[_label] = _k


def _amp_key(value):
    """把（含倍率标注的）配方文本还原为 damage 里的键；兼容旧工程文件。"""
    v = (value or "").strip()
    if not v or v == "无":
        return "无"
    if v in damage.AMPLIFY_BASE_FACTOR:
        return v
    if v in _AMP_LABEL_TO_KEY:
        return _AMP_LABEL_TO_KEY[v]
    for k in damage.AMPLIFY_BASE_FACTOR:      # 前缀/旧写法兜底
        if v.startswith(k):
            return k
    return v
_AUX_STAT = [
    ("stat_base", "白值", "1000", "num"),
    ("stat_big", "大增益%", "0", "pct"),
    ("stat_flat", "小增益", "0", "num"),
    ("multiplier", "倍率%", "200", "pct"),
]

NODE_TYPES = {
    "base": dict(title="① 基础值(属性×倍率)", inputs=0, compute=_t_base, fields=[
        ("stat_base", "白值", "1000", "num"),
        ("stat_big", "大增益%", "0", "pct"),
        ("stat_flat", "小增益", "0", "num"),
        ("multiplier", "倍率%", "200", "pct"),
    ]),
    "dmg": dict(title="② 增伤区 ×", inputs=1, compute=_t_dmg, fields=[
        ("dmg_net", "增伤区净%", "46.6", "pct"),
    ]),
    "res": dict(title="③ 抗性区 ×", inputs=1, compute=_t_res, fields=[
        ("resistance", "敌人抗性%", "10", "pct"),
    ]),
    "def": dict(title="④ 防御区 ×", inputs=1, compute=_t_def, fields=[
        ("char_level", "角色等级", "90", "num"),
        ("enemy_level", "敌人等级", "90", "num"),
        ("def_reduction", "减防%", "0", "pct"),
        ("ignore_def", "无视防御%", "0", "pct"),
    ]),
    "crit": dict(title="⑤ 暴击区 (暴击率/暴伤)", inputs=1, compute=_t_crit, fields=[
        ("crit_rate", "暴击率%", "50", "pct"),
        ("crit_damage", "暴击伤害%", "100", "pct"),
    ]),
    "amp": dict(title="⑥ 增幅反应 ×", inputs=1, compute=_t_amp, fields=[
        ("formula", "配方", "无", "combo", _AMP_OPTS),
        ("em", "元素精通", "0", "num"),
        ("amp_bonus", "反应增伤%", "0", "pct"),
        ("shield", "命中护盾(不计)", False, "check"),
    ]),
    "boost": dict(title="⑦ 擢升 ×", inputs=1, compute=_t_boost, fields=[
        ("boost", "擢升%", "0", "pct"),
    ]),
    "add": dict(title="⑧ ＋加法合并", inputs=2, compute=_t_add, fields=[]),
    "aggravate": dict(title="㊀ 激化值(源)", inputs=0, compute=_t_aggravate, fields=[
        ("kind", "类型", "超激化", "combo", ["超激化", "蔓激化"]),
        ("em", "元素精通", "0", "num"),
        ("bonus", "激化提高%", "0", "pct"),
        ("level", "等级", "90", "num"),
    ]),
    "transform": dict(title="㊁ 剧变反应(源)", inputs=0, compute=_t_transform, fields=[
        ("reaction", "反应", "超载", "combo", list(damage.TRANSFORM_RATE.keys())),
        ("em", "元素精通", "0", "num"),
        ("bonus", "反应增伤%", "0", "pct"),
        ("level", "等级", "90", "num"),
    ]),
    "crystal": dict(title="㊂ 结晶护盾(源)", inputs=0, compute=_t_crystal, fields=[
        ("em", "元素精通", "0", "num"),
        ("shield_strength", "护盾强效%", "0", "pct"),
    ]),
    # ---- 拆分开的乘区部件：星/月/剧变等源由这些自由组合 ----
    "attr": dict(title="◈ 属性源(白×(1+大)+小)", inputs=0, compute=_t_attr, fields=[
        ("stat_base", "白值", "1000", "num"),
        ("stat_big", "大增益%", "0", "pct"),
        ("stat_flat", "小增益", "0", "num"),
    ]),
    "react_base": dict(title="◈ 基准值源(1446.85)", inputs=0, compute=_t_react_base,
                       fields=[("level", "等级", "90", "num")]),
    "coeff": dict(title="× 系数", inputs=1, compute=_t_coeff, fields=[
        ("coeff", "系数", "1", "num"),
    ]),
    "mult": dict(title="× 倍率%", inputs=1, compute=_t_mult, fields=[
        ("multiplier", "倍率%", "200", "pct"),
    ]),
    "base_boost": dict(title="× (1+基础提升%)", inputs=1, compute=_t_base_boost,
                       fields=[("base_boost", "基础提升%", "0", "pct")]),
    "em_gain": dict(title="× 精通增益(1+k·EM/(EM+den)+增伤%)", inputs=1,
                    compute=_t_em_gain, fields=[
        ("em", "元素精通", "0", "num"),
        ("k", "精通系数k", "6", "num"),
        ("denom", "分母", "2000", "num"),
        ("bonus", "增伤%", "0", "pct"),
    ]),
    # 计算卡：无端口、可自定义标题、可拖动放大，计算表达式数值并可复制输出
    "calc": dict(title="计算卡", inputs=0, compute=_t_calc, isolated=True,
                 copyable=True, resizable=True, wide_fields=True, fields=[
        ("title", "标题", "计算卡", "text"),
        ("expr", "表达式", "1+1", "textbox"),
    ]),
    # 纯文本卡片：无端口、可拖动、右键可调字号；仅作标注，不参与计算
    "text": dict(title="文本", inputs=0, compute=_t_text, isolated=True,
                 no_output=True, resizable=True, wide_fields=True,
                 font_menu=True, fields=[
        ("content", "内容", "在此输入文本", "textbox"),
    ]),
    "result": dict(title="★ 结果", inputs=1, compute=_t_result, fields=[]),
}


class NodeBoard(ttk.Frame):
    """画布式乘区节点编辑器。"""

    PALETTE = [
        ("base", "基础值"), ("dmg", "增伤区"), ("res", "抗性区"),
        ("def", "防御区"), ("crit", "暴击区"), ("amp", "增幅反应"),
        ("boost", "擢升"), ("add", "＋加法"),
        ("aggravate", "激化值"), ("transform", "剧变反应"), ("crystal", "结晶护盾"),
        ("attr", "属性源"), ("react_base", "基准值源"),
        ("coeff", "×系数"), ("mult", "×倍率"),
        ("base_boost", "×基础提升"), ("em_gain", "×精通增益"),
        ("calc", "计算卡"),
        ("text", "文本"),
        ("result", "★结果"),
    ]

    # 一键预设：用拆分开的乘区部件搭好星/月等链条
    PRESETS = {
        "普通直伤": [
            ("base", {}), ("dmg", {}), ("res", {}), ("def", {}),
            ("crit", {}), ("amp", {}), ("result", {}),
        ],
        "月·直伤": [
            ("attr", {}), ("coeff", {"coeff": "3"}), ("mult", {"multiplier": "200"}),
            ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
            ("res", {}), ("crit", {}), ("boost", {}), ("result", {}),
        ],
        "月·反应": [
            ("react_base", {}), ("coeff", {"coeff": "1.8"}),
            ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
            ("res", {}), ("crit", {}), ("boost", {}), ("result", {}),
        ],
        "星·超导": [
            ("attr", {}), ("coeff", {"coeff": "1.45"}), ("mult", {"multiplier": "200"}),
            ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
            ("res", {}), ("crit", {}), ("boost", {}), ("result", {}),
        ],
        "星·扩散": [
            ("react_base", {}), ("coeff", {"coeff": "0.75"}),
            ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
            ("res", {}), ("crit", {}), ("boost", {}), ("result", {}),
        ],
        "星·扩散直伤": [
            ("attr", {}), ("coeff", {"coeff": "1"}), ("mult", {"multiplier": "200"}),
            ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
            ("res", {}), ("crit", {}), ("boost", {}), ("result", {}),
        ],
        "剧变反应": [
            ("react_base", {}), ("coeff", {"coeff": "2.75"}),
            ("em_gain", {"k": "16", "denom": "2000"}),
            ("res", {}), ("result", {}),
        ],
        "激化值": [
            ("react_base", {}), ("coeff", {"coeff": "1.15"}),
            ("em_gain", {"k": "5", "denom": "1200", "bonus": "0"}),
            ("result", {}),
        ],
    }

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change
        self.nodes: dict[str, dict] = {}
        self.links: list[dict] = []      # {src, dst, port}
        self._seq = 0
        self._drag_node = None
        self._drag_off = (0, 0)
        self._wire_from = None           # 连线起点 node id
        self._wire_line = None
        self._spawn = [40, 60]
        self._hover = None
        self._clear_job = None
        self._resize_node = None
        self._resize_start = None
        self._loading = False
        self.zoom = 1.0

        self._build_palette()
        self._build_canvas()
        self._build_default_graph()

    # ------------------------------------------------------------------
    def _build_palette(self) -> None:
        box = ttk.Frame(self)
        box.pack(side="top", fill="x", padx=6, pady=(4, 0))
        ttk.Label(box, text="添加卡片：", foreground="#556").grid(
            row=0, column=0, sticky="w")
        for i, (key, label) in enumerate(self.PALETTE):
            ttk.Button(box, text=label, width=11,
                       command=lambda k=key: self.add_node(k)).grid(
                row=i // 6, column=1 + i % 6, padx=1, pady=1, sticky="ew")

        box2 = ttk.Frame(self)
        box2.pack(side="top", fill="x", padx=6, pady=(2, 4))
        ttk.Label(box2, text="一键预设：", foreground="#556").grid(
            row=0, column=0, sticky="w")
        for i, name in enumerate(self.PRESETS):
            ttk.Button(box2, text=name, width=11,
                       command=lambda n=name: self.build_preset(n)).grid(
                row=i // 5, column=1 + i % 5, padx=1, pady=1, sticky="ew")
        # “清空”放在预设按钮下方独占一行，避免与按钮重叠
        clear_row = (len(self.PRESETS) - 1) // 5 + 1
        ttk.Button(box2, text="清空画布", width=10,
                   command=self.clear_board).grid(
            row=clear_row, column=1, columnspan=2, padx=1, pady=(4, 1),
            sticky="ew")

        # 画布缩放
        box3 = ttk.Frame(self)
        box3.pack(side="top", fill="x", padx=6, pady=(0, 4))
        ttk.Label(box3, text="画布缩放：", foreground="#556").pack(side="left")
        ttk.Button(box3, text="－", width=3,
                   command=lambda: self.zoom_by(1 / 1.15)).pack(side="left", padx=1)
        self.zoom_var = tk.StringVar(value="100%")
        ttk.Label(box3, textvariable=self.zoom_var, width=6,
                  anchor="center").pack(side="left", padx=2)
        ttk.Button(box3, text="＋", width=3,
                   command=lambda: self.zoom_by(1.15)).pack(side="left", padx=1)
        ttk.Button(box3, text="100%", width=6,
                   command=lambda: self.set_zoom(1.0)).pack(side="left", padx=4)
        ttk.Label(box3, text="（也可 Ctrl+滚轮）", foreground="#999").pack(
            side="left", padx=4)

    def _build_canvas(self) -> None:
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.canvas.configure(scrollregion=(0, 0, 2400, 1600))
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        # Ctrl+滚轮 缩放
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        self.bind_all("<Control-MouseWheel>", self._on_ctrl_wheel, add="+")

    # ------------------------------------------------------------------
    # 节点创建 / 删除
    # ------------------------------------------------------------------
    def add_node(self, type_key: str, x: float | None = None,
                 y: float | None = None) -> str:
        spec = NODE_TYPES[type_key]
        self._seq += 1
        nid = "n%d" % self._seq
        frame = ttk.Frame(self.canvas)
        if type_key == "text":
            # 纯文本卡片：窄边框（1px 细线），内容区留白小
            lf = tk.Frame(frame, highlightthickness=1,
                          highlightbackground="#c3ccd6",
                          highlightcolor="#c3ccd6", bd=0, bg="#ffffff")
        else:
            lf = ttk.LabelFrame(frame, padding=8)
        lf.pack(fill="both", expand=True)
        head = ttk.Frame(lf)
        head.pack(fill="x")
        ttl = ttk.Label(head, text=spec["title"], foreground=ACCENT,
                        font=("Microsoft YaHei", 10, "bold"),
                        cursor="fleur")
        ttl.pack(side="left")
        ttk.Button(head, text="✕", width=2,
                   command=lambda: self.remove_node(nid)).pack(side="right")
        grip = ttk.Label(head, text="⣿", cursor="fleur", foreground=ACCENT)
        grip.pack(side="right", padx=(0, 4))
        body = ttk.Frame(lf)
        wide = spec.get("wide_fields")
        body.pack(fill="both", expand=True)
        vars_: dict[str, tk.StringVar] = {}
        texts_: dict[str, tk.Text] = {}
        for f in spec["fields"]:
            key, label, default, kind = f[0], f[1], f[2], f[3]
            if wide:
                # 宽表布局：标签在上、输入框占满整行（便于拖动放大后编辑长算式）
                plain = (type_key == "text")   # 纯文本卡片：不显示字段标签
                if not plain:
                    ttk.Label(body, text=label, anchor="w").pack(fill="x")
                if kind == "textbox":
                    var = tk.StringVar(value=str(default))
                    kw = dict(height=3, width=22, wrap="word")
                    if plain:   # 窄边框：文本框本身无边框，只留内边距
                        kw.update(borderwidth=0, highlightthickness=0,
                                  padx=6, pady=4, bg="#ffffff")
                    txt = tk.Text(body, **kw)
                    txt.insert("1.0", str(default))
                    txt.pack(fill="both", expand=True)
                    texts_[key] = txt

                    def _sync(e, v=var, w=txt):
                        v.set(w.get("1.0", "end").strip())
                        self._notify()

                    txt.bind("<KeyRelease>", _sync)
                    txt.bind("<FocusOut>", _sync)
                else:
                    var = tk.StringVar(value=str(default))
                    ttk.Entry(body, textvariable=var).pack(fill="x")
                    var.trace_add("write", lambda *a: self._notify())
                vars_[key] = var
                continue
            r = ttk.Frame(body)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=label, width=11, anchor="w").pack(side="left")
            if kind == "check":
                var = tk.BooleanVar(value=bool(default))
                ttk.Checkbutton(r, variable=var).pack(side="left")
                var.trace_add("write", lambda *a: self._notify())
                var = _BoolVar(var)
            elif kind == "combo":
                var = tk.StringVar(value=str(default))
                ttk.Combobox(r, textvariable=var, values=f[4],
                             state="readonly", width=14).pack(
                    side="left", fill="x", expand=True)
                var.trace_add("write", lambda *a: self._notify())
            else:
                var = tk.StringVar(value=str(default))
                ttk.Entry(r, textvariable=var, width=16).pack(
                    side="left", fill="x", expand=True)
                var.trace_add("write", lambda *a: self._notify())
            vars_[key] = var
        info = ttk.Frame(lf)
        info.pack(fill="x", pady=(4, 0))
        out_var = tk.StringVar(value="输出: -")
        if not spec.get("no_output"):
            ttk.Label(info, textvariable=out_var,
                      foreground="#333").pack(side="left")
        # 可自定义标题：标题栏跟随 “标题” 字段
        if "title" in vars_:
            ttl.configure(textvariable=vars_["title"])
        # 计算卡：复制输出数值
        if spec.get("copyable"):
            ttk.Button(info, text="复制", width=4,
                       command=lambda: self._copy_output(nid)).pack(side="right")
        # 可拖动放大：右下角缩放手柄（所有卡片均支持）
        rsz = ttk.Label(lf, text="◢", cursor="sizing", foreground="#888")
        rsz.pack(side="bottom", anchor="e")
        rsz.bind("<ButtonPress-1>",
                 lambda e, k=nid: self._start_resize(k, e))
        rsz.bind("<B1-Motion>", self._resize_motion)
        rsz.bind("<ButtonRelease-1>", self._end_resize)

        win = self.canvas.create_window(0, 0, window=frame, anchor="nw",
                                        tags=(nid,))
        node = dict(id=nid, type=type_key, frame=frame, vars=vars_,
                    texts=texts_, out=out_var, win=win, pos=[0, 0], ports={},
                    size=None, font_size=None)
        self.nodes[nid] = node
        if x is None:
            x, y = self._free_slot()
        self.move_node(nid, x, y)
        # 标题 / 把手拖动
        for w in (head, ttl, grip):
            w.bind("<ButtonPress-1>", lambda e, k=nid: self._start_node_drag(k, e))
            w.bind("<B1-Motion>", self._node_drag_motion)
            w.bind("<ButtonRelease-1>", self._end_node_drag)
        self._bind_hover(frame, nid)
        if spec.get("font_menu"):
            self._bind_context(frame, nid)      # 右键调字号
        # 记录“基准尺寸”（缩放前），供缩放与命中判定使用
        self._apply_fonts(nid, scale=1.0)
        self.update_idletasks()
        node["base"] = [max(frame.winfo_reqwidth(), 1),
                        max(frame.winfo_reqheight(), 1)]
        if self.zoom != 1.0:
            self._apply_fonts(nid)
        self.draw_all()
        self._notify()
        self._scroll_to(nid)
        return nid

    def _free_slot(self):
        """新卡片落位：从左上开始找第一个不重叠的网格位置。"""
        cols, cw, ch = 4, 280, 250
        for i in range(400):
            x = 40 + (i % cols) * cw
            y = 60 + (i // cols) * ch
            if not self._overlaps_any(x, y):
                return x, y
        return 40, 60

    def _overlaps_any(self, x: float, y: float) -> bool:
        for nid in self.nodes:
            nx, ny = self.nodes[nid]["pos"]
            w, h = self._base_size(nid)      # 用未缩放尺寸判断重叠
            if x < nx + w + 20 and nx < x + 300 and y < ny + h + 20 and ny < y + 240:
                return True
        return False

    def _update_scrollregion(self) -> None:
        """滚动区随卡片自动扩展，保证所有卡片都能滚动到。"""
        mx, my = 1200, 900
        for nid in self.nodes:
            x, y = self._screen_pos(nid)
            w, h = self._card_size(nid)
            mx = max(mx, x + w + 80)
            my = max(my, y + h + 80)
        self.canvas.configure(scrollregion=(0, 0, mx, my))

    def _scroll_to(self, nid: str) -> None:
        """若新卡片不在可视区域内，滚动使其可见。"""
        if nid not in self.nodes:
            return
        self.update_idletasks()
        x, y = self._screen_pos(nid)
        _, h = self._card_size(nid)
        vh = self.canvas.winfo_height()
        top = self.canvas.canvasy(0)
        if y < top or (y + h) > top + vh:
            total = max(self.canvas.bbox("all")[3] if self.canvas.bbox("all") else 900, 1)
            self.canvas.yview_moveto(max(0.0, (y - 30) / total))

    def remove_node(self, nid: str) -> None:
        if nid not in self.nodes:
            return
        self.links = [l for l in self.links
                      if l["src"] != nid and l["dst"] != nid]
        self.canvas.delete(nid)
        self.nodes[nid]["frame"].destroy()
        del self.nodes[nid]
        self.draw_all()
        self._notify()

    def _build_default_graph(self) -> None:
        self.build_preset("普通直伤")

    def clear_board(self) -> None:
        """清空画布上的所有卡片与连线。"""
        for nid in list(self.nodes):
            self.canvas.delete(nid)
            self.nodes[nid]["frame"].destroy()
            del self.nodes[nid]
        self.links = []
        self.draw_all()
        self._notify()

    def build_preset(self, name: str) -> None:
        """按预设用拆分开的乘区部件搭好一条链。"""
        spec = self.PRESETS.get(name)
        if spec is None:
            return
        self.clear_board()
        prev = None
        x, y = 40, 120
        for type_key, overrides in spec:
            nid = self.add_node(type_key, x, y)
            for k, v in overrides.items():
                if k in self.nodes[nid]["vars"]:
                    self.nodes[nid]["vars"][k].set(str(v))
            if prev is not None:
                self.links.append(dict(src=prev, dst=nid, port=0))
            prev = nid
            x += 250
        self.draw_all()
        self._notify()

    # ------------------------------------------------------------------
    # 读值
    # ------------------------------------------------------------------
    def _getter(self, node):
        def g(key):
            v = node["vars"].get(key)
            if v is None:
                return None
            return v.get()
        return g

    def node_output(self, nid: str, _stack=None):
        """计算某节点的 (nc, cr, ex) 三元组（含上游）。"""
        _stack = _stack or set()
        if nid in _stack:
            raise ValueError("检测到环路：%s" % self.nodes[nid]["type"])
        node = self.nodes[nid]
        spec = NODE_TYPES[node["type"]]
        ins = []
        for port in range(spec["inputs"]):
            src = self._link_src(nid, port)
            if src is None:
                ins.append((0.0, 0.0, 0.0))
            else:
                ins.append(self.node_output(src, _stack | {nid}))
        return spec["compute"](self._getter(node), ins)

    def _link_src(self, dst: str, port: int):
        for l in self.links:
            if l["dst"] == dst and l["port"] == port:
                return l["src"]
        return None

    def evaluate(self):
        """从结果节点反向溯源求值，返回 (nc, cr, ex) 或抛错。"""
        result = next((k for k, n in self.nodes.items()
                       if n["type"] == "result"), None)
        if result is None:
            raise ValueError("没有「结果」卡片")
        return self.node_output(result)

    def refresh_outputs(self) -> None:
        for nid, n in self.nodes.items():
            if NODE_TYPES[n["type"]].get("no_output"):
                continue
            try:
                v = self.node_output(nid)
                # 结果卡片始终显示三条路；其它卡片在三条路不同时（如经过暴击区）也显示三条
                if (n["type"] == "result"
                        or abs(v[1] - v[0]) > 1e-9 or abs(v[2] - v[0]) > 1e-9):
                    n["out"].set("未暴击 %s ｜ 暴击 %s ｜ 期望 %s" % (
                        _fmt(v[0]), _fmt(v[1]), _fmt(v[2])))
                else:
                    n["out"].set("输出: %s" % _fmt(v[0]))
            except Exception as e:
                n["out"].set("输出: 错误(%s)" % e)

    def chain_types(self) -> list:
        """返回结果链上（含结果卡片）所有节点类型。"""
        res = next((k for k, n in self.nodes.items()
                    if n["type"] == "result"), None)
        seen, types = set(), []

        def walk(nid):
            if nid in seen:
                return
            seen.add(nid)
            spec = NODE_TYPES[self.nodes[nid]["type"]]
            for p in range(spec["inputs"]):
                s = self._link_src(nid, p)
                if s:
                    walk(s)
            types.append(self.nodes[nid]["type"])

        if res:
            walk(res)
        return types

    def _copy_output(self, nid: str) -> None:
        """把该卡片的输出数值复制到剪贴板（纯数字，便于粘贴到输入框）。"""
        try:
            v = self.node_output(nid)
            text = _plain(v[0])
        except Exception:
            text = ""
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self.nodes[nid]["out"].set("已复制: %s" % text)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def _base_size(self, nid):
        """卡片的“基准尺寸”（缩放前，模型坐标）：用户拖动过则用该尺寸，否则用自然尺寸。"""
        n = self.nodes[nid]
        if n.get("size"):
            return float(n["size"][0]), float(n["size"][1])
        if self.zoom == 1.0:            # 未缩放时以当前自然尺寸为准（输出文字会变长）
            f = n["frame"]
            return float(f.winfo_reqwidth() or 1), float(f.winfo_reqheight() or 1)
        if n.get("base"):
            return float(n["base"][0]), float(n["base"][1])
        f = n["frame"]
        return float(f.winfo_reqwidth() or 1), float(f.winfo_reqheight() or 1)

    def _screen_pos(self, nid):
        x, y = self.nodes[nid]["pos"]
        return x * self.zoom, y * self.zoom

    def _card_size(self, nid):
        bw, bh = self._base_size(nid)
        return bw * self.zoom, bh * self.zoom

    def move_node(self, nid, x, y):
        """x/y 为模型坐标（未缩放），内部按 zoom 换算到画布坐标。"""
        self.nodes[nid]["pos"] = [x, y]
        self.canvas.coords(self.nodes[nid]["win"], x * self.zoom, y * self.zoom)

    def _apply_card_geometry(self, nid) -> None:
        """按当前缩放设置卡片窗口尺寸。"""
        n = self.nodes[nid]
        bw, bh = self._base_size(nid)
        if self.zoom == 1.0 and not n.get("size"):
            n["frame"].pack_propagate(True)
            return
        n["frame"].configure(width=max(1, int(bw * self.zoom)),
                             height=max(1, int(bh * self.zoom)))
        n["frame"].pack_propagate(False)

    def draw_all(self) -> None:
        self.canvas.delete("port")
        self.canvas.delete("link")
        self.canvas.delete("portlabel")
        # 1) 先确定各卡片几何，并刷新“基准尺寸”缓存
        for nid in self.nodes:
            self._apply_card_geometry(nid)
        self.update_idletasks()
        if self.zoom == 1.0:
            for nid, n in self.nodes.items():
                if not n.get("size"):
                    f = n["frame"]
                    n["base"] = [max(f.winfo_reqwidth(), 1),
                                 max(f.winfo_reqheight(), 1)]
        # 2) 定位窗口 + 画端口/连线
        for nid, n in self.nodes.items():
            spec = NODE_TYPES[n["type"]]
            x, y = self._screen_pos(nid)
            self.canvas.coords(n["win"], x, y)   # 缩放后同步窗口坐标
            w, h = self._card_size(nid)
            n["ports"] = {}
            if spec["inputs"] > 0:
                step = h / (spec["inputs"] + 1)
                for p in range(spec["inputs"]):
                    py = y + step * (p + 1)
                    item = self.canvas.create_oval(
                        x - 7, py - 7, x + 7, py + 7, fill="#3a7", outline="#185",
                        tags=("port", "in:%s:%d" % (nid, p)))
                    n["ports"]["in%d" % p] = (x, py, item)
            oy = y + h / 2
            if not spec.get("isolated"):
                item = self.canvas.create_oval(
                    x + w - 7, oy - 7, x + w + 7, oy + 7, fill=ACCENT,
                    outline="#1b4", tags=("port", "out:%s" % nid))
                n["ports"]["out"] = (x + w, oy, item)
        for l in self.links:
            self._draw_link(l)
        self._apply_link_styles()
        self._update_scrollregion()

    # ------------------------------------------------------------------
    # 画布缩放
    # ------------------------------------------------------------------
    def _font_family(self) -> str:
        try:
            import tkinter.font as tkfont
            return tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:
            return "Microsoft YaHei"

    def _apply_fonts(self, nid: str, scale: float | None = None) -> None:
        """按缩放比例调整该卡片内所有控件的字号（支持每张卡片单独设字号）。"""
        z = self.zoom if scale is None else scale
        fam = self._font_family()
        base = float(self.nodes[nid].get("font_size") or 9)
        size = max(6, int(round(base * z)))

        def walk(w):
            try:
                w.configure(font=(fam, size))
            except tk.TclError:
                pass
            for c in w.winfo_children():
                walk(c)

        if nid in self.nodes:
            walk(self.nodes[nid]["frame"])

    def _measure_base(self, nid: str) -> None:
        """在“未缩放字号”下重新测量卡片基准尺寸并缓存。"""
        n = self.nodes[nid]
        if n.get("size"):
            return
        self._apply_fonts(nid, scale=1.0)
        self.update_idletasks()
        f = n["frame"]
        n["base"] = [max(f.winfo_reqwidth(), 1), max(f.winfo_reqheight(), 1)]
        self._apply_fonts(nid)

    def set_node_font(self, nid: str, size: float) -> None:
        """设置某张卡片的字号（相对 100% 缩放）。"""
        if nid not in self.nodes:
            return
        self.nodes[nid]["font_size"] = max(6, min(72, float(size)))
        # 自定义过尺寸的卡片同样要应用字号（只是不再重测基准尺寸）
        if not self.nodes[nid].get("size"):
            self._measure_base(nid)
        else:
            self._apply_fonts(nid)
        self.draw_all()

    def bump_node_font(self, nid: str, delta: float = 2) -> None:
        cur = float(self.nodes[nid].get("font_size") or 9)
        self.set_node_font(nid, cur + delta)

    def _bind_context(self, widget, nid: str) -> None:
        widget.bind("<Button-3>",
                    lambda e, k=nid: self._show_font_menu(k, e), add="+")
        for c in widget.winfo_children():
            self._bind_context(c, nid)

    def _show_font_menu(self, nid: str, event) -> None:
        cur = float(self.nodes[nid].get("font_size") or 9)
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="字体 ＋ (当前 %g)" % cur,
                      command=lambda: self.bump_node_font(nid, 2))
        m.add_command(label="字体 －",
                      command=lambda: self.bump_node_font(nid, -2))
        m.add_separator()
        for s in (9, 12, 16, 20, 28, 40):
            m.add_command(label="字号 %d" % s,
                          command=lambda s=s: self.set_node_font(nid, s))
        m.add_separator()
        m.add_command(label="重置为默认(9)",
                      command=lambda: self.set_node_font(nid, 9))
        m.add_command(label="复制文本",
                      command=lambda: self._copy_node_text(nid))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _copy_node_text(self, nid: str) -> None:
        txt = ""
        for v in self.nodes[nid]["vars"].values():
            try:
                txt = v.get()
                break
            except Exception:
                continue
        if txt:
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.update_idletasks()

    def _reapply_zoom(self) -> None:
        for nid in self.nodes:
            self._apply_fonts(nid)
        self.draw_all()

    def set_zoom(self, z: float) -> None:
        z = max(0.4, min(2.5, float(z)))
        self.zoom = z
        if hasattr(self, "zoom_var"):
            self.zoom_var.set("%d%%" % round(z * 100))
        self._reapply_zoom()

    def zoom_by(self, factor: float) -> None:
        self.set_zoom(self.zoom * factor)

    def _on_ctrl_wheel(self, event):
        self.zoom_by(1.1 if getattr(event, "delta", 0) > 0 else 1 / 1.1)
        return "break"

    def _bezier(self, p1, p2, steps: int = 28):
        x1, y1 = p1
        x2, y2 = p2
        dx = max(60.0, min(240.0, abs(x2 - x1) * 0.5))
        c1x, c1y = x1 + dx, y1
        c2x, c2y = x2 - dx, y2
        pts = []
        for i in range(steps + 1):
            t = i / steps
            mt = 1 - t
            x = (mt ** 3) * x1 + 3 * mt * mt * t * c1x + 3 * mt * t * t * c2x + (t ** 3) * x2
            y = (mt ** 3) * y1 + 3 * mt * mt * t * c1y + 3 * mt * t * t * c2y + (t ** 3) * y2
            pts.extend((x, y))
        return pts

    def _op_symbol(self, dst_id: str) -> str:
        t = self.nodes[dst_id]["type"]
        if t == "add":
            return "＋"
        if t == "result":
            return "★"
        return "×"

    def _draw_link(self, l) -> None:
        sp = self.nodes[l["src"]]["ports"].get("out")
        dp = self.nodes[l["dst"]]["ports"].get("in%d" % l["port"])
        if not sp or not dp:
            return
        pts = self._bezier((sp[0], sp[1]), (dp[0], dp[1]))
        line = self.canvas.create_line(
            *pts, width=max(1, 2 * self.zoom), fill=ACCENT, tags=("link",),
            arrow="last", arrowshape=(12, 14, 5), capstyle="round",
            joinstyle="round")
        # 目标端操作符（× / ＋ / ★），紧贴输入端口便于辨认
        sym = self.canvas.create_text(
            dp[0] - 13, dp[1], text=self._op_symbol(l["dst"]),
            fill=ACCENT, tags="link",
            font=("Microsoft YaHei", max(7, int(11 * self.zoom)), "bold"))
        l["items"] = (line, sym)

    # ------------------------------------------------------------------
    # 悬停高亮：突出与当前卡片相关的连线，弱化其余
    # ------------------------------------------------------------------
    def _bind_hover(self, widget, nid: str) -> None:
        widget.bind("<Enter>", lambda e, k=nid: self._set_hover(k), add="+")
        widget.bind("<Leave>", lambda e: self._schedule_hover_clear(), add="+")
        for c in widget.winfo_children():
            self._bind_hover(c, nid)

    def _set_hover(self, nid: str) -> None:
        if self._clear_job:
            self.after_cancel(self._clear_job)
            self._clear_job = None
        if self._hover != nid:
            self._hover = nid
            self._apply_link_styles()

    def _schedule_hover_clear(self) -> None:
        if self._clear_job:
            self.after_cancel(self._clear_job)
        self._clear_job = self.after(120, self._clear_hover)

    def _clear_hover(self) -> None:
        self._clear_job = None
        self._hover = None
        self._apply_link_styles()

    def _apply_link_styles(self) -> None:
        for l in self.links:
            items = l.get("items")
            if not items:
                continue
            hot = self._hover is not None and (
                l["src"] == self._hover or l["dst"] == self._hover)
            if hot:
                color, width = "#e8590c", max(2, 3.5 * self.zoom)
            elif self._hover is not None:
                color, width = "#b9c6d2", max(1, 2 * self.zoom)
            else:
                color, width = ACCENT, max(1, 2 * self.zoom)
            self.canvas.itemconfigure(items[0], fill=color, width=width)
            self.canvas.itemconfigure(items[1], fill=color)

    def _hit_port(self, x, y):
        for item in self.canvas.find_overlapping(x - 3, y - 3, x + 3, y + 3):
            for tag in self.canvas.gettags(item):
                if tag.startswith("out:"):
                    return ("out", tag[4:])
                if tag.startswith("in:"):
                    _, nid, p = tag.split(":")
                    return ("in", nid, int(p))
        return None

    def _hit_link(self, x, y):
        for item in self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2):
            if "link" in self.canvas.gettags(item):
                return item
        return None

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def _cx(self, event):
        return self.canvas.canvasx(event.x_root - self.canvas.winfo_rootx())

    def _cy(self, event):
        return self.canvas.canvasy(event.y_root - self.canvas.winfo_rooty())

    def _on_press(self, event):
        x, y = self._cx(event), self._cy(event)
        hit = self._hit_port(x, y)
        if hit and hit[0] == "out":
            self._wire_from = hit[1]
            self._wire_line = self.canvas.create_line(
                x, y, x, y, width=2, fill="#c60", dash=(4, 3), tags="wire")
            return
        link_item = self._hit_link(x, y)
        if link_item is not None:
            self._delete_link_item(link_item)
            return

    def _delete_link_item(self, item):
        # 找到该线对应的 link（按端点匹配）
        coords = self.canvas.coords(item)
        for l in list(self.links):
            sp = self.nodes[l["src"]]["ports"].get("out")
            dp = self.nodes[l["dst"]]["ports"].get("in%d" % l["port"])
            if not sp or not dp:
                continue
            if abs(coords[-2] - dp[0]) < 3 and abs(coords[-1] - dp[1]) < 3:
                self.links.remove(l)
                break
        self.draw_all()
        self._notify()

    def _on_motion(self, event):
        x, y = self._cx(event), self._cy(event)
        if self._wire_from is not None and self._wire_line is not None:
            sp = self.nodes[self._wire_from]["ports"].get("out")
            self.canvas.coords(self._wire_line, sp[0], sp[1], x, y)

    def _on_release(self, event):
        x, y = self._cx(event), self._cy(event)
        if self._wire_from is not None:
            hit = self._hit_port(x, y)
            if hit and hit[0] == "in":
                _, dst, port = hit
                if dst != self._wire_from:
                    # 一个输入端口只保留一条连线
                    self.links = [l for l in self.links
                                  if not (l["dst"] == dst and l["port"] == port)]
                    self.links.append(dict(src=self._wire_from, dst=dst, port=port))
            if self._wire_line is not None:
                self.canvas.delete(self._wire_line)
            self._wire_line = None
            self._wire_from = None
            self.draw_all()
            self._notify()

    def _start_node_drag(self, nid, event):
        self._drag_node = nid
        sx, sy = self._screen_pos(nid)
        self._drag_off = (self._cx(event) - sx, self._cy(event) - sy)
        self.canvas.tag_raise(self.nodes[nid]["win"])

    def _node_drag_motion(self, event):
        if not self._drag_node:
            return
        sx = self._cx(event) - self._drag_off[0]
        sy = self._cy(event) - self._drag_off[1]
        # 画布坐标 → 模型坐标
        self.move_node(self._drag_node, sx / self.zoom, sy / self.zoom)
        self.draw_all()

    def _end_node_drag(self, event):
        self._drag_node = None

    # ------------------------------------------------------------------
    # 拖动放大（右下角手柄）
    # ------------------------------------------------------------------
    def _start_resize(self, nid: str, event) -> None:
        w, h = self._card_size(nid)          # 屏幕尺寸
        self._resize_node = nid
        self._resize_start = (self._cx(event), self._cy(event), w, h)

    def _resize_motion(self, event) -> None:
        if not self._resize_node:
            return
        x0, y0, w0, h0 = self._resize_start
        sw = max(200 * self.zoom, w0 + (self._cx(event) - x0))
        sh = max(110 * self.zoom, h0 + (self._cy(event) - y0))
        n = self.nodes[self._resize_node]
        n["size"] = [sw / self.zoom, sh / self.zoom]   # 存模型（未缩放）尺寸
        self.draw_all()

    def _end_resize(self, event) -> None:
        if self._resize_node:
            self._resize_node = None
            self._notify()

    def _notify(self):
        if self._loading:
            return
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------
    # JSON 工程存档
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """导出整张画布（节点类型/位置/尺寸/参数 + 连线）为可序列化字典。"""
        nodes = []
        for nid, n in self.nodes.items():
            fields = {k: v.get() for k, v in n["vars"].items()}
            nodes.append(dict(
                id=nid, type=n["type"],
                pos=[float(n["pos"][0]), float(n["pos"][1])],
                size=(list(n["size"]) if n.get("size") else None),
                font_size=n.get("font_size"),
                fields=fields,
            ))
        links = [dict(src=l["src"], dst=l["dst"], port=int(l["port"]))
                 for l in self.links]
        return dict(version=1, app="GenshinDamageCalc", zoom=self.zoom,
                    nodes=nodes, links=links)

    def from_dict(self, data: dict) -> None:
        """从字典恢复画布（旧 id 会重映射到新 id）。"""
        self._loading = True
        try:
            self.clear_board()
            try:
                self.zoom = max(0.4, min(2.5, float(data.get("zoom", 1.0))))
            except (TypeError, ValueError):
                self.zoom = 1.0
            if hasattr(self, "zoom_var"):
                self.zoom_var.set("%d%%" % round(self.zoom * 100))
            idmap: dict[str, str] = {}
            for nd in data.get("nodes", []):
                t = nd.get("type")
                if t not in NODE_TYPES:
                    continue
                pos = nd.get("pos") or [40, 60]
                new = self.add_node(t, float(pos[0]), float(pos[1]))
                idmap[nd.get("id")] = new
                n = self.nodes[new]
                for k, v in (nd.get("fields") or {}).items():
                    if k in n["vars"]:
                        n["vars"][k].set("" if v is None else str(v))
                        if k in n.get("texts", {}):
                            txt = n["texts"][k]
                            txt.delete("1.0", "end")
                            txt.insert("1.0", "" if v is None else str(v))
                sz = nd.get("size")
                if sz and len(sz) == 2:
                    n["size"] = [float(sz[0]), float(sz[1])]
                fs = nd.get("font_size")
                if fs:
                    n["font_size"] = float(fs)
                    self._measure_base(new)
            for l in data.get("links", []):
                s = idmap.get(l.get("src"))
                d = idmap.get(l.get("dst"))
                if s and d:
                    self.links.append(
                        dict(src=s, dst=d, port=int(l.get("port", 0))))
        finally:
            self._loading = False
        self.draw_all()
        self._notify()

    def snapshot(self):
        rows = []
        for nid, n in self.nodes.items():
            spec = NODE_TYPES[n["type"]]
            vals = []
            for f in spec["fields"]:
                v = n["vars"][f[0]].get()
                vals.append("%s=%s" % (f[1], v))
            rows.append("%s [%s] @%s %s" % (
                nid, spec["title"],
                "(%d,%d)" % (n["pos"][0], n["pos"][1]), " ".join(vals)))
        links = []
        for l in self.links:
            links.append("%s -> %s.in%d" % (l["src"], l["dst"], l["port"]))
        return rows, links

    def describe(self):
        """从结果节点反向溯源的节点求值顺序（缩进表示上游）。"""
        result = next((k for k, n in self.nodes.items()
                       if n["type"] == "result"), None)
        if result is None:
            return ["（无结果卡片）"]
        lines = []
        seen = set()

        def walk(nid, depth):
            if nid in seen:
                return
            seen.add(nid)
            spec = NODE_TYPES[self.nodes[nid]["type"]]
            for p in range(spec["inputs"]):
                s = self._link_src(nid, p)
                if s:
                    walk(s, depth + 1)
            try:
                v = self.node_output(nid)
                txt = "未暴击 %s / 暴击 %s / 期望 %s" % (
                    _fmt(v[0]), _fmt(v[1]), _fmt(v[2]))
            except Exception as e:
                txt = "(错误: %s)" % e
            lines.append("%s%s  →  %s" % ("    " * depth, spec["title"], txt))

        walk(result, 0)
        return lines


class _BoolVar:
    """把 BooleanVar 适配成有 .get()/.set() 的对象（供 getter 与加载使用）。"""

    def __init__(self, var):
        self._var = var

    def get(self):
        return self._var.get()

    def set(self, value):
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "是", "on")
        self._var.set(bool(value))

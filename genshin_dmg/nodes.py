# -*- coding: utf-8 -*-
"""节点（卡片）类型注册表 —— 纯逻辑，不依赖任何 UI。

每张卡片 = 一个节点：

* ``inputs``：输入端口数（加法卡片 ``variadic``，端口数可 1~12）。
* ``fields``：参数定义 ``{key, label, default, kind, options?}``，
  ``kind`` ∈ ``num / pct / combo / check / text / textbox``。
* ``compute(get, ins) -> (未暴击, 暴击, 期望)``，``get`` 取原始字段值，``ins`` 是上游三元组列表。
* ``factor``：可选，返回卡片底部展示的「本卡系数」文案。

本模块同时是前端的**单一数据源**：后端 ``/api/schema`` 把它序列化给前端，
前端据此渲染卡片、字段控件与左侧菜单，保证两端行为一致。
"""

from __future__ import annotations

import contextvars

from genshin_dmg import damage
from genshin_dmg.expr import eval_expr, fmt_num, parse_num, parse_pct

__all__ = [
    "NODE_TYPES",
    "GROUPS",
    "PRESETS",
    "RELIC_ROWS",
    "RELIC_HEADER",
    "VAR_TABLE_HEADER",
    "RESULT_VAR_FIELDS",
    "RESULT_VAR_KEYS",
    "AMP_OPTIONS",
    "amp_options",
    "amp_key",
    "star_rate",
    "field_specs",
    "defaults_of",
    "node_schema",
    "schema",
    "current_env",
    "use_env",
    "reset_env",
    "eval_field",
]

# ---------------------------------------------------------------------------
# 变量环境（contextvar）：求值前由 Graph 注入，使所有字段都能引用变量
#   num / pct 字段 → _num() / _pct()
#   表达式字段    → _expr()
# 用 contextvar 而非模块全局，保证并发请求之间不互相污染。
# ---------------------------------------------------------------------------
_ENV: contextvars.ContextVar = contextvars.ContextVar("genshin_var_env", default=None)


def current_env() -> dict:
    """当前求值上下文里的变量表（未注入时返回空表）。"""
    return _ENV.get() or {}


def use_env(env: dict):
    """注入变量表，返回 token（配合 :func:`reset_env` 还原）。"""
    return _ENV.set(env)


def reset_env(token) -> None:
    _ENV.reset(token)


def _num(s, d: float = 0.0) -> float:
    """字段 → 数值（支持算式与变量）。"""
    return parse_num(s, d, current_env())


def _pct(s, d: float = 0.0) -> float:
    """字段 → 比例（``50`` → ``0.5``，支持算式与变量）。"""
    return parse_pct(s, d, current_env())


def _expr(text) -> float:
    """表达式字段求值（支持变量）。"""
    return eval_expr(text, current_env())


def eval_field(text) -> float:
    """供 :mod:`genshin_dmg.graph` 复用：表达式字段求值（支持变量）。"""
    return _expr(text)


def _F(key, label, default, kind="num", options=None) -> dict:
    """构造一个字段定义。"""
    f = dict(key=key, label=label, default=default, kind=kind)
    if options is not None:
        f["options"] = list(options)
    return f


# ---------------------------------------------------------------------------
# 三元组运算辅助
# ---------------------------------------------------------------------------
def _mul(v, coeff):
    return (v[0] * coeff, v[1] * coeff, v[2] * coeff)


def _root(v):
    return (v, v, v)


def _attr(get):
    return damage.effective_stat(
        _num(get("stat_base"), 1000), _pct(get("stat_big")), _num(get("stat_flat")))


# ---------------------------------------------------------------------------
# 计算函数
# ---------------------------------------------------------------------------
def _t_base(get, ins):
    v = _attr(get) * _pct(get("multiplier"), 2.0)
    return (v, v, v)


def _t_add(get, ins):
    """加法合并：把所有输入逐分量相加（输入个数可变）。"""
    vals = list(ins) or [(0.0, 0.0, 0.0)]
    return tuple(sum(v[i] for v in vals) for i in range(3))


def _t_dmg(get, ins):
    return _mul(ins[0], 1 + _pct(get("dmg_net")))


def _t_res(get, ins):
    return _mul(ins[0], damage.resistance_coefficient(_pct(get("resistance"), 10.0)))


def _t_def(get, ins):
    coeff = damage.defense_coefficient(
        _num(get("char_level"), 90), _num(get("enemy_level"), 90),
        def_reduction=_pct(get("def_reduction")),
        ignore_def=_pct(get("ignore_def")),
    )
    return _mul(ins[0], coeff)


def _t_crit(get, ins):
    cr = _pct(get("crit_rate"), 50.0)
    cd = _pct(get("crit_damage"), 100.0)
    cr_eff = min(max(cr, 0.0), 1.0)          # 有效暴击率封顶 100%
    nc = ins[0][0]
    return (nc, nc * (1 + cd), nc * (1 + cr_eff * cd))


def _t_amp(get, ins):
    name = amp_key(get("formula"))
    if name == "无" or get("shield"):
        coeff = 1.0
    else:
        coeff = damage.amplify_for_reaction(
            name, _num(get("em")), _pct(get("amp_bonus")))
    return _mul(ins[0], coeff)


def _t_boost(get, ins):
    return _mul(ins[0], 1 + _pct(get("boost")))


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


def _t_result(get, ins):
    return ins[0] if ins else (0, 0, 0)


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
    return _mul(ins[0], _pct(get("multiplier"), 2.0))


def _t_base_boost(get, ins):
    """× (1 + 基础提升%)。"""
    return _mul(ins[0], 1 + _pct(get("base_boost")))


def _em_term(get) -> float:
    """k×EM/(EM+分母) 项。"""
    em = _num(get("em"))
    k = _num(get("k"), 6.0)
    den = _num(get("denom"), 2000.0)
    return 0.0 if (em + den) == 0 else k * em / (em + den)


def _t_em_gain(get, ins):
    """× (1 + k×EM/(EM+分母) + 增伤%)   —— k=6/分母2000 为星月；16/2000 剧变；5/1200 激化。"""
    return _mul(ins[0], 1 + _em_term(get) + _pct(get("bonus")))


def star_rate(get) -> float:
    """星超导系数：按附着层数（hit 0~12）查表，0→1.0 … 12→2.0。"""
    hits = int(max(0, min(12, _num(get("hits"), 0))))
    return damage.STAR_SUPERCOND_RATE[hits]


def _t_star_coeff(get, ins):
    return _mul(ins[0], star_rate(get))


def _t_calc(get, ins):
    """计算卡：求输入表达式的数值（无输入端口）。"""
    v = _expr(get("expr"))
    return (v, v, v)


def _t_text(get, ins):
    """纯文本 / 变量 / 表格卡片：只用于标注，不参与计算。"""
    return (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# 「本卡系数」显示文案
# ---------------------------------------------------------------------------
def _f_dmg(get, ins):
    return "增伤区 ×%s" % fmt_num(1 + _pct(get("dmg_net")))


def _f_res(get, ins):
    return "抗性系数 ×%s" % fmt_num(
        damage.resistance_coefficient(_pct(get("resistance"), 10.0)))


def _f_def(get, ins):
    return "防御系数 ×%s" % fmt_num(damage.defense_coefficient(
        _num(get("char_level"), 90), _num(get("enemy_level"), 90),
        def_reduction=_pct(get("def_reduction")),
        ignore_def=_pct(get("ignore_def"))))


def _f_crit(get, ins):
    cd = _pct(get("crit_damage"), 100.0)
    cr = min(max(_pct(get("crit_rate"), 50.0), 0.0), 1.0)
    return "暴击系数 ×%s ｜ 期望系数 ×%s" % (fmt_num(1 + cd), fmt_num(1 + cr * cd))


def _f_amp(get, ins):
    name = amp_key(get("formula"))
    if name == "无" or get("shield"):
        c = 1.0
    else:
        c = damage.amplify_for_reaction(
            name, _num(get("em")), _pct(get("amp_bonus")))
    return "蒸发融化系数 ×%s" % fmt_num(c)


def _f_boost(get, ins):
    return "擢升 ×%s" % fmt_num(1 + _pct(get("boost")))


def _f_coeff(get, ins):
    return "系数 ×%s" % fmt_num(_num(get("coeff"), 1.0))


def _f_mult(get, ins):
    return "倍率 ×%s" % fmt_num(_pct(get("multiplier"), 200.0))


def _f_base_boost(get, ins):
    return "基础提升 ×%s" % fmt_num(1 + _pct(get("base_boost")))


def _f_em_gain(get, ins):
    return "精通增益 ×%s" % fmt_num(1 + _em_term(get) + _pct(get("bonus")))

def _f_star_coeff(get, ins):
    return "星超导系数 ×%s" % fmt_num(star_rate(get))


# ---------------------------------------------------------------------------
# 增幅反应配方（标签含倍率与方向，如「蒸发·水打火 ×2.0」）
# ---------------------------------------------------------------------------
def _build_amp_options():
    opts = ["无"]
    mapping = {}
    for k, v in damage.AMPLIFY_BASE_FACTOR.items():
        label = "%s ×%.1f" % (k.replace("→", "打"), v)
        opts.append(label)
        mapping[label] = k
    return opts, mapping


AMP_OPTIONS, AMP_LABEL_TO_KEY = _build_amp_options()


def amp_options() -> list:
    return list(AMP_OPTIONS)


def amp_key(value) -> str:
    """把（含倍率标注的）配方文本还原为 damage 里的键；兼容旧工程文件。"""
    v = (value or "").strip()
    if not v or v == "无":
        return "无"
    if v in damage.AMPLIFY_BASE_FACTOR:
        return v
    if v in AMP_LABEL_TO_KEY:
        return AMP_LABEL_TO_KEY[v]
    for k in damage.AMPLIFY_BASE_FACTOR:      # 前缀 / 旧写法兜底
        if v.startswith(k):
            return k
    return v


# ---------------------------------------------------------------------------
# ★结果 卡片的隐藏变量字段
# ---------------------------------------------------------------------------
RESULT_VAR_FIELDS = (
    ("var_nc", "未暴击变量"),
    ("var_cr", "暴击变量"),
    ("var_ex", "期望变量"),
)
RESULT_VAR_KEYS = tuple(k for k, _ in RESULT_VAR_FIELDS)


# ---------------------------------------------------------------------------
# 只读参考表
# ---------------------------------------------------------------------------
RELIC_HEADER = ("属性", "强化区间", "最高区间", "平均值")
RELIC_ROWS = [
    ("暴击率（%）", "2.72/3.11/3.50/3.89", "16.32~23.34", "3.305"),
    ("暴击伤害（%）", "5.44/6.22/6.99/7.77", "32.64~46.62", "6.605"),
    ("固定攻击力", "13.62/15.56/17.51/19.45", "81.72~116.70", "16.535"),
    ("百分比攻击力（%）", "4.08/4.66/5.25/5.83", "24.48~34.98", "4.955"),
    ("固定生命值", "209.13/239.00/268.88/298.75", "1254.78~1792.50", "253.94"),
    ("百分比生命值（%）", "4.08/4.66/5.25/5.83", "24.48~34.98", "4.955"),
    ("固定防御力", "16.20/18.52/20.83/23.15", "97.20~138.90", "19.675"),
    ("百分比防御力（%）", "5.10/5.83/6.56/7.29", "30.60~43.74", "6.195"),
    ("元素精通", "16.32/18.65/20.98/23.31", "97.92~139.86", "19.815"),
    ("元素充能效率（%）", "4.53/5.18/5.83/6.48", "27.18~38.88", "5.505"),
]
VAR_TABLE_HEADER = ("变量", "值")


# ---------------------------------------------------------------------------
# 节点类型注册表
# ---------------------------------------------------------------------------
NODE_TYPES: dict = {
    # ---- 直伤乘区 ----
    "base": dict(title="基础值 (属性×倍率)", label="基础值", group="直伤乘区",
                 inputs=0, compute=_t_base, fields=[
        _F("stat_base", "白值", "1000"),
        _F("stat_big", "大增益%", "0", "pct"),
        _F("stat_flat", "小增益", "0"),
        _F("multiplier", "倍率%", "200", "pct"),
    ]),
    "dmg": dict(title="增伤区 ×", label="增伤区", group="直伤乘区",
                inputs=1, compute=_t_dmg, factor=_f_dmg, fields=[
        _F("dmg_net", "增伤区净%", "46.6", "pct"),
    ]),
    "res": dict(title="抗性区 ×", label="抗性区", group="直伤乘区",
                inputs=1, compute=_t_res, factor=_f_res, fields=[
        _F("resistance", "敌人抗性%", "10", "pct"),
    ]),
    "def": dict(title="防御区 ×", label="防御区", group="直伤乘区",
                inputs=1, compute=_t_def, factor=_f_def, fields=[
        _F("char_level", "角色等级", "90"),
        _F("enemy_level", "敌人等级", "90"),
        _F("def_reduction", "减防%", "0", "pct"),
        _F("ignore_def", "无视防御%", "0", "pct"),
    ]),
    "crit": dict(title="暴击区 (暴击率/暴伤)", label="暴击区", group="直伤乘区",
                 inputs=1, compute=_t_crit, factor=_f_crit, fields=[
        _F("crit_rate", "暴击率%", "50", "pct"),
        _F("crit_damage", "暴击伤害%", "100", "pct"),
    ]),
    "amp": dict(title="增幅反应 ×", label="增幅反应", group="直伤乘区",
                inputs=1, compute=_t_amp, factor=_f_amp, fields=[
        _F("formula", "配方", "无", "combo", AMP_OPTIONS),
        _F("em", "元素精通", "0"),
        _F("amp_bonus", "反应增伤%", "0", "pct"),
        _F("shield", "命中护盾(不计)", False, "check"),
    ]),
    "boost": dict(title="擢升 ×", label="擢升", group="直伤乘区",
                  inputs=1, compute=_t_boost, factor=_f_boost, fields=[
        _F("boost", "擢升%", "0", "pct"),
    ]),
    "add": dict(title="＋加法合并", label="＋加法", group="直伤乘区",
                inputs=2, compute=_t_add, variadic=True, fields=[]),
    # ---- 反应源 ----
    "aggravate": dict(title="激化值(源)", label="激化值", group="反应源",
                      inputs=0, compute=_t_aggravate, fields=[
        _F("kind", "类型", "超激化", "combo", ["超激化", "蔓激化"]),
        _F("em", "元素精通", "0"),
        _F("bonus", "激化提高%", "0", "pct"),
        _F("level", "等级", "90"),
    ]),
    "transform": dict(title="剧变反应(源)", label="剧变反应", group="反应源",
                      inputs=0, compute=_t_transform, fields=[
        _F("reaction", "反应", "超载", "combo", list(damage.TRANSFORM_RATE.keys())),
        _F("em", "元素精通", "0"),
        _F("bonus", "反应增伤%", "0", "pct"),
        _F("level", "等级", "90"),
    ]),
    "crystal": dict(title="结晶护盾(源)", label="结晶护盾", group="反应源",
                    inputs=0, compute=_t_crystal, fields=[
        _F("em", "元素精通", "0"),
        _F("shield_strength", "护盾强效%", "0", "pct"),
    ]),
    # ---- 星/月部件（源由这些自由组合）----
    "attr": dict(title="◈ 属性源(白×(1+大)+小)", label="属性源", group="星月部件",
                 inputs=0, compute=_t_attr, fields=[
        _F("stat_base", "白值", "1000"),
        _F("stat_big", "大增益%", "0", "pct"),
        _F("stat_flat", "小增益", "0"),
    ]),
    "react_base": dict(title="◈ 基准值源(1446.85)", label="基准值源", group="星月部件",
                       inputs=0, compute=_t_react_base, fields=[
        _F("level", "等级", "90"),
    ]),
    "coeff": dict(title="× 系数", label="×系数", group="星月部件",
                  inputs=1, compute=_t_coeff, factor=_f_coeff, fields=[
        _F("coeff", "系数", "1"),
    ]),
    "mult": dict(title="× 倍率%", label="×倍率", group="星月部件",
                 inputs=1, compute=_t_mult, factor=_f_mult, fields=[
        _F("multiplier", "倍率%", "200", "pct"),
    ]),
    "base_boost": dict(title="× (1+基础提升%)", label="×基础提升", group="星月部件",
                       inputs=1, compute=_t_base_boost, factor=_f_base_boost, fields=[
        _F("base_boost", "基础提升%", "0", "pct"),
    ]),
    "em_gain": dict(title="× 精通增益(1+k·EM/(EM+den)+增伤%)", label="×精通增益",
                    group="星月部件", inputs=1, compute=_t_em_gain,
                    factor=_f_em_gain, fields=[
        _F("em", "元素精通", "0"),
        _F("k", "精通系数k（星月6/剧变16/激化5）", "6"),
        _F("denom", "分母（星月·剧变2000/激化1200）", "2000"),
        _F("bonus", "增伤%", "0", "pct"),
    ]),
    "star_coeff": dict(title="星超导系数 ×", label="星超导系数", group="星月部件",
                       inputs=1, compute=_t_star_coeff, factor=_f_star_coeff, fields=[
        _F("hits", "层数", "0"),
    ]),
    # ---- 工具卡片 ----
    "calc": dict(title="计算卡", label="计算卡", group="工具", inputs=0,
                 compute=_t_calc, isolated=True, copyable=True, resizable=True,
                 wide_fields=True, fields=[
        _F("title", "标题", "计算卡", "text"),
        _F("expr", "表达式", "1+1", "textbox"),
    ]),
    # 纯文本卡片：无端口、可拖动、右键可调字号；仅作标注，不参与计算
    # bare=True：这张卡「就是一块便签」，前端不画字段标签、不给输入框加边框与内边距，
    #            文字直接铺满卡片内区（只作用于界面，不影响计算）
    "text": dict(title="文本", label="文本", group="工具", inputs=0, compute=_t_text,
                 isolated=True, no_output=True, resizable=True, wide_fields=True,
                 font_menu=True, bare=True, fields=[
        _F("content", "内容", "在此输入文本", "textbox"),
    ]),
    "var": dict(title="变量", label="变量", group="工具", inputs=0, compute=_t_text,
                isolated=True, vars_card=True, resizable=True, wide_fields=True,
                fields=[
        _F("defs", "定义",
           "攻击力 = 1000\n倍率 = 200\n基础伤害 = 攻击力 * 倍率", "textbox"),
    ]),
    "const": dict(title="理想圣遗物词条", label="理想圣遗物", group="工具", inputs=0,
                  compute=_t_text, isolated=True, no_output=True, resizable=True,
                  wide_fields=True, plain=True, table="relic", fields=[
        _F("content", "内容", "", "textbox"),
    ]),
    "vartable": dict(title="变量表", label="变量表", group="工具", inputs=0,
                     compute=_t_text, isolated=True, no_output=True, resizable=True,
                     table="vars", fields=[]),
    "result": dict(title="★ 结果", label="★结果", group="工具", inputs=1,
                   compute=_t_result, ctx_menu=True, hidden_fields=[
        _F(k, label, "") for k, label in RESULT_VAR_FIELDS
    ], fields=[]),
}


# 左侧菜单分组（按注册顺序去重，组内顺序即注册顺序）
GROUPS = []
for _key, _spec in NODE_TYPES.items():
    if _spec["group"] not in [g["name"] for g in GROUPS]:
        GROUPS.append(dict(name=_spec["group"], items=[]))
    next(g for g in GROUPS if g["name"] == _spec["group"])["items"].append(
        dict(type=_key, label=_spec["label"]))


# 一键预设：用拆分开的乘区部件搭好星/月等链条（**不含结果卡片**）
PRESETS = {
    "普通直伤": [
        ("base", {}), ("dmg", {}), ("res", {}), ("def", {}),
        ("crit", {}), ("amp", {}),
    ],
    "月·直伤": [
        ("attr", {}), ("coeff", {"coeff": "3"}), ("mult", {"multiplier": "200"}),
        ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
        ("res", {}), ("crit", {}), ("boost", {}),
    ],
    "月·反应": [
        ("react_base", {}), ("coeff", {"coeff": "1.8"}),
        ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
        ("res", {}), ("crit", {}), ("boost", {}),
    ],
    "星·超导": [
        ("attr", {}), ("star_coeff", {"hits": "0"}), ("mult", {"multiplier": "200"}),
        ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
        ("res", {}), ("crit", {}), ("boost", {}),
    ],
    "星·扩散": [
        ("react_base", {}), ("coeff", {"coeff": "0.75"}),
        ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
        ("res", {}), ("crit", {}), ("boost", {}),
    ],
    "星·扩散直伤": [
        ("attr", {}), ("coeff", {"coeff": "1"}), ("mult", {"multiplier": "200"}),
        ("base_boost", {}), ("em_gain", {"k": "6", "denom": "2000"}),
        ("res", {}), ("crit", {}), ("boost", {}),
    ],
    "剧变反应": [
        ("react_base", {}), ("coeff", {"coeff": "2.75"}),
        ("em_gain", {"k": "16", "denom": "2000"}), ("res", {}),
    ],
    "激化值": [
        ("react_base", {}), ("coeff", {"coeff": "1.15"}),
        ("em_gain", {"k": "5", "denom": "1200", "bonus": "0"}),
    ],
}


# ---------------------------------------------------------------------------
# 供前端使用的描述
# ---------------------------------------------------------------------------
def field_specs(type_key: str) -> list:
    """某类型可见字段 + 隐藏字段（结果卡片的三个变量名）。"""
    spec = NODE_TYPES[type_key]
    return list(spec.get("fields", [])) + list(spec.get("hidden_fields", []))


def defaults_of(type_key: str) -> dict:
    """某类型的字段默认值。"""
    return {f["key"]: f["default"] for f in field_specs(type_key)}


def node_schema(type_key: str) -> dict:
    """把某个节点类型序列化成前端可用的描述（去掉 compute / factor 等不可序列化项）。"""
    spec = NODE_TYPES[type_key]
    return dict(
        type=type_key,
        title=spec["title"],
        label=spec["label"],
        group=spec["group"],
        inputs=int(spec["inputs"]),
        fields=field_specs(type_key),
        defaults=defaults_of(type_key),
        variadic=bool(spec.get("variadic")),
        isolated=bool(spec.get("isolated")),
        no_output=bool(spec.get("no_output")),
        resizable=bool(spec.get("resizable")),
        wide_fields=bool(spec.get("wide_fields")),
        bare=bool(spec.get("bare")),
        plain=bool(spec.get("plain")),
        copyable=bool(spec.get("copyable")),
        font_menu=bool(spec.get("font_menu")),
        vars_card=bool(spec.get("vars_card")),
        ctx_menu=bool(spec.get("ctx_menu")),
        has_factor=bool(spec.get("factor")),
        table=spec.get("table"),
        hidden_fields=[f["key"] for f in spec.get("hidden_fields", [])],
    )


def schema() -> dict:
    """完整前端描述：卡片类型 + 菜单分组 + 预设 + 参考表 + 缩放与历史范围。"""
    return dict(
        version=1,
        app="GenshinDamageCalc",
        groups=GROUPS,
        nodeTypes={k: node_schema(k) for k in NODE_TYPES},
        presets={name: [dict(type=t, fields=f) for t, f in items]
                 for name, items in PRESETS.items()},
        tables={
            "relic": dict(header=list(RELIC_HEADER),
                          rows=[list(r) for r in RELIC_ROWS]),
            "vars": dict(header=list(VAR_TABLE_HEADER)),
        },
        resultVarFields=[dict(key=k, label=label) for k, label in RESULT_VAR_FIELDS],
        zoom=dict(min=0.25, max=2.5, step=1.15),
        history=dict(max=80),
    )

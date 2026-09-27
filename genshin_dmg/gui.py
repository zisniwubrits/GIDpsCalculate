# -*- coding: utf-8 -*-
"""
原神伤害计算 - tkinter 图形界面。

左侧为参数输入表单（可滚动），右侧为计算结果与明细。

运行入口见仓库根目录 main.py：
    python main.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog as _fd
import re
import ast
import operator as _op
import datetime

from genshin_dmg import damage
from genshin_dmg.nodeboard import NodeBoard

# 窗口配色
BG = "#f4f6f8"
SECTION_BG = "#ffffff"
ACCENT = "#2f6fa7"
RESULT_BG = "#eef5fb"

# 安全算术求值（白名单运算符，不使用 eval）
_ARITH_OPS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.FloorDiv: _op.floordiv,
    ast.Mod: _op.mod,
    ast.Pow: _op.pow,
    ast.USub: _op.neg,
    ast.UAdd: _op.pos,
}
_MATHY = {"，": ".", ",": ".", "×": "*", "÷": "/", "＋": "+", "－": "-", "％": ""}


def _eval_arith(text: str):
    """安全求值形如 '352+674'、'(100+50)*2.5' 的表达式；解析失败返回 None。"""
    t = text.strip()
    for k, v in _MATHY.items():
        t = t.replace(k, v)
    if not t:
        return None
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        return None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp):
            fn = _ARITH_OPS.get(type(node.op))
            if fn is None:
                raise TypeError("unsupported op")
            return fn(ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp):
            fn = _ARITH_OPS.get(type(node.op))
            if fn is None:
                raise TypeError("unsupported op")
            return fn(ev(node.operand))
        raise TypeError("unsupported node")

    try:
        return float(ev(tree))
    except (TypeError, ZeroDivisionError, OverflowError):
        return None


def to_float(text: str, default: float = 0.0) -> float:
    """把输入框文本解析为 float；支持算式如 '352+674'；空/非法返回 default。"""
    t = text.strip()
    if not t:
        return default
    # 若是单个数字（含小数点/正负号），直接 float 快速返回
    if re.fullmatch(r"[+-]?\d*\.?\d+", t):
        try:
            return float(t)
        except ValueError:
            return default
    r = _eval_arith(t)
    return default if r is None else r


def to_percent(text: str, default: float = 0.0) -> float:
    """把百分数（如 46.6 或算式）解析为小数（0.466）。"""
    return to_float(text, default) / 100.0


class DamageApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("原神伤害计算器")
        self.configure(bg=BG)
        # 主窗口默认尺寸并居中
        _center_window(self, 1040, 720)

        # 主布局：画布占满窗口（不再有右侧结果栏）
        self.left = tk.Frame(self, bg=BG)
        self.left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self._report_lines: list = []

        self._build_input_panel()
        self._build_result_panel()

        self._build_bottom_bar()
        self.bind_all("<F1>", lambda e: self.show_help())
        # 撤销 / 重做
        self.bind_all("<Control-z>", lambda e: (self.board.undo(), "break")[1])
        self.bind_all("<Control-Z>", lambda e: (self.board.redo(), "break")[1])
        self.bind_all("<Control-y>", lambda e: (self.board.redo(), "break")[1])

        self._set_project_name("")          # 标题显示工程名（未命名）
        self.calculate()

    # ------------------------------------------------------------------
    # 底部工具栏：左侧工程信息 / 右侧「文件操作 | 帮助 | 主操作」
    # ------------------------------------------------------------------
    def _build_bottom_bar(self) -> None:
        right = ttk.Frame(self.bottom)
        right.pack(side="right", padx=6, pady=6)

        self.help_button = ttk.Button(right, text="教程 (F1)",
                                      command=self.show_help)
        self.help_button.pack(side="right", padx=3)
        ttk.Separator(right, orient="vertical").pack(
            side="right", fill="y", padx=8, pady=2)
        # 文件操作（从左到右：保存工程 / 打开工程 / 导出结果）
        self.save_button = ttk.Button(right, text="导出结果…",
                                      command=self.save_report)
        self.save_button.pack(side="right", padx=3)
        self.load_json_button = ttk.Button(right, text="打开工程…",
                                           command=self.load_project)
        self.load_json_button.pack(side="right", padx=3)
        self.save_json_button = ttk.Button(right, text="保存工程…",
                                           command=self.save_project)
        self.save_json_button.pack(side="right", padx=3)

    def _on_board_change(self) -> None:
        if hasattr(self, "board"):
            self.calculate()

    def save_project(self) -> None:
        """把整张画布（节点+连线+参数）以 JSON 保存为一个工程文件。"""
        # 默认文件名使用当前工程名（导入时得到的名称）
        base = self.board.project_name or _timestamp_name("伤害工程").replace(".txt", "")
        path = _fd.asksaveasfilename(
            title="保存工程(JSON)",
            initialfile="%s.json" % base,
            defaultextension=".json",
            filetypes=[("JSON 工程", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        import json
        import os
        name = os.path.splitext(os.path.basename(path))[0]
        self.board.project_name = name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.board.to_dict(), f, ensure_ascii=False, indent=2)
        self._set_project_name(name)
        self.title("原神伤害计算器 · %s" % name)

    def load_project(self) -> None:
        """读取 JSON 工程并恢复到画布。"""
        path = _fd.askopenfilename(
            title="打开工程(JSON)",
            filetypes=[("JSON 工程", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        import json
        import os
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._set_result(["【打开失败】%s" % e])
            return
        self.board.from_dict(data)
        # 优先用存档里的名称，没有就用文件名
        name = self.board.project_name or os.path.splitext(
            os.path.basename(path))[0]
        self.board.project_name = name
        self._set_project_name(name)
        self.title("原神伤害计算器 · %s" % name)
        self.calculate()

    def _set_project_name(self, name: str) -> None:
        """工程名显示在窗口标题上。"""
        self.title("原神伤害计算器 · %s" % (name or "未命名"))

    def open_month_star(self) -> None:
        """打开月/星反应的独立弹窗。"""
        if getattr(self, "_ms_dialog", None) is not None:
            try:
                self._ms_dialog.lift()
                return
            except tk.TclError:
                self._ms_dialog = None
        self._ms_dialog = MoonStarDialog(self)

    def _snapshot(self):
        """采集节点画布快照 -> [(分组, [(标签, 值)])]。"""
        rows, links = self.board.snapshot()
        return [
            ("节点卡片", [(r.split(" [")[0], r.split(" [", 1)[1]) for r in rows]),
            ("连线", [("link%d" % i, s) for i, s in enumerate(links)]),
        ]

    def show_help(self) -> None:
        """按 F1 打开使用教程。"""
        dlg = getattr(self, "_help_dialog", None)
        if dlg is not None:
            try:
                dlg.lift()
                return
            except tk.TclError:
                self._help_dialog = None
        self._help_dialog = HelpWindow(self)

    def save_report(self) -> None:
        """把当前直伤计算的输入与结果保存为一个文件。"""
        default = _timestamp_name("直伤伤害")
        path = _save_as_file(default, "保存直伤计算")
        if not path:
            return
        body = "\n".join(getattr(self, "_report_lines", []))
        content = _compose_report(
            "原神 · 直伤伤害计算", self._snapshot(), body)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.title("原神伤害计算器 · 已保存")

    # ------------------------------------------------------------------
    # 输入面板
    # ------------------------------------------------------------------
    def _build_input_panel(self) -> None:
        self.bottom = tk.Frame(self.left, bg=BG)
        self.bottom.pack(side="bottom", fill="x", pady=4)
        # 画布式乘区节点编辑器
        self.board = NodeBoard(self.left, on_change=self._on_board_change)
        self.board.pack(fill="both", expand=True)


    # ------------------------------------------------------------------
    # 计算结果（不再有右侧结果栏；结果只记录用于保存，并显示在画布卡片上）
    # ------------------------------------------------------------------
    def _build_result_panel(self) -> None:
        pass

    def _set_result(self, lines: list[str]) -> None:
        self._report_lines = list(lines)

    # ------------------------------------------------------------------
    # 计算
    # ------------------------------------------------------------------
    def calculate(self) -> None:
        board = getattr(self, "board", None)
        if board is None:
            return
        try:
            nc, cr, ex = board.evaluate()
            board.refresh_outputs()
            lines = [
                "【结果】",
                "未暴击伤害 : %s" % fmt(nc),
                "暴击伤害   : %s" % fmt(cr),
                "期望伤害   : %s   (有效暴击封顶100%%)" % fmt(ex),
            ]
            if "crit" not in board.chain_types():
                lines.append("提示：结果链中没有「暴击区」卡片，"
                             "暴击/期望与未暴击相同。")
                res = next((k for k, n in board.nodes.items()
                            if n["type"] == "result"), None)
                if res:
                    board.nodes[res]["out"].set(
                        board.nodes[res]["out"].get() + "   ← 无暴击区")
            lines += [
                "-" * 22,
                "【节点求值过程（从结果反向溯源）】",
            ]
            lines.extend(board.describe())
        except Exception as e:
            board.refresh_outputs()
            if "结果" in str(e):
                lines = ["【提示】画布中还没有「★结果」卡片：",
                         "各卡片仍会显示自身系数与输出；把链尾连到 ★结果 即可汇总伤害。"]
            else:
                lines = ["【无法计算】%s" % e]
        self._set_result(lines)



def fmt(x: float) -> str:
    """固定小数位格式化，避免出现科学计数法。"""
    if abs(x) >= 10000:
        return f"{x:,.1f}"
    if abs(x) >= 100:
        return f"{x:.2f}"
    if abs(x) >= 1:
        return f"{x:.3f}"
    return f"{x:.4f}"


def _center_window(win: tk.Misc, width: int, height: int) -> None:
    """把窗口(主窗/弹窗)放到屏幕正中央。"""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max((sw - width) // 2, 0)
    y = max((sh - height) // 2, 0)
    win.geometry(f"{width}x{height}+{x}+{y}")


def _save_as_file(default_name: str, title: str) -> str | None:
    """弹出保存对话框，返回用户选择的路径；取消返回 None。"""
    return _fd.asksaveasfilename(
        title=title,
        initialfile=default_name,
        defaultextension=".txt",
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
    )


def _compose_report(app_title: str, sections, body: str) -> str:
    """把输入快照与结果拼成可读的报告文本。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "=" * 48
    rows = [line, "  " + app_title, "  保存时间：" + now, line]
    for gname, items in sections:
        rows.append("【%s】" % gname)
        for label, value in items:
            rows.append("  %-16s : %s" % (label, value))
        rows.append("")
    rows.append(line)
    rows.append("【计算结果与完整过程】")
    rows.append(body.rstrip("\n"))
    rows.append(line)
    return "\n".join(rows)


def _timestamp_name(prefix: str) -> str:
    return "%s_%s.txt" % (
        prefix, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))


class MoonStarDialog(tk.Toplevel):
    """月 / 星 反应独立弹窗。"""

    MS_TYPES = [
        "直伤月感电", "直伤月结晶", "直伤月绽放",
        "反应月感电", "反应月结晶",
        "星超导", "反应星扩散·风", "反应星扩散·冰", "星扩散直伤",
    ]

    FIELDS = [
        ("白值(基础)", "attr_base", "1000", "值", "直伤类用"),
        ("大增益%", "attr_big", "0", "", "如大攻击%"),
        ("小增益", "attr_flat", "0", "值", "如小攻击数值"),
        ("倍率", "mult", "200", "%", "直伤类用"),
        ("hit/风涡", "count", "1", "数", "星超导hit/星扩散风涡"),
        ("等级", "level", "90", "级", "95/100有修正"),
        ("元素精通", "em", "0", "", ""),
        ("基础提升%", "base_boost", "0", "", "天赋提升"),
        ("反应增伤%", "bonus", "0", "", ""),
        ("额外提升", "extra", "0", "值", "直伤类"),
        ("擢升%", "boost", "0", "", ""),
        ("抗性%", "res", "10", "", ""),
        ("暴击率%", "cr", "50", "", ""),
        ("暴击伤害%", "cd", "100", "", ""),
        ("角色伤害分摊", "dist", "", "值", "逗号分隔"),
    ]

    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("月 / 星 反应计算")
        self.configure(bg=BG)
        self.transient(master)
        _center_window(self, 900, 620)

        self.vars: dict[str, tk.StringVar] = {}

        # 左：输入表单
        left = ttk.Frame(self, padding=8)
        left.pack(side="left", fill="both", expand=True)
        f = ttk.LabelFrame(left, text="参数（支持算式）", padding=8)
        f.pack(fill="x")

        ttk.Label(f, text="类型", foreground="#888").pack(anchor="w")
        self.type_var = tk.StringVar(value=self.MS_TYPES[0])
        combo = ttk.Combobox(
            f, textvariable=self.type_var,
            values=self.MS_TYPES, state="readonly",
        )
        combo.pack(fill="x", pady=(2, 6))

        for label, key, default, unit, hint in self.FIELDS:
            var = tk.StringVar(value=default)
            self.vars[key] = var
            r = ttk.Frame(f)
            r.pack(fill="x", pady=1)
            ttk.Label(r, text=label, width=14, anchor="w").pack(side="left")
            if unit:
                ttk.Label(r, text=unit, width=4, anchor="w").pack(side="left")
            ttk.Entry(r, textvariable=var, width=18).pack(side="left", padx=(0, 6))
            if hint:
                ttk.Label(r, text=hint, foreground="#999", width=18,
                          anchor="w").pack(side="left")

        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x", pady=4, padx=8)
        ttk.Button(bar, text="计算", command=self.calculate).pack(
            side="right", padx=4)
        ttk.Button(bar, text="保存结果…", command=self.save_report).pack(
            side="right", padx=4)
        ttk.Button(bar, text="关闭", command=self.destroy).pack(
            side="right", padx=4)

        # 右：结果
        right = tk.Frame(self, bg=RESULT_BG, width=260)
        right.pack(side="right", fill="y", padx=(0, 6), pady=8)
        right.pack_propagate(False)
        tk.Label(right, text="计算结果", bg=RESULT_BG, fg=ACCENT,
                 font=("Microsoft YaHei", 12, "bold")).pack(pady=(8, 4))
        self.result_text = tk.Text(
            right, bg=RESULT_BG, relief="flat", wrap="word",
            font=("Microsoft YaHei", 11), padx=8, pady=6,
        )
        self.result_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.result_text.configure(state="disabled")

        self.calculate()

    def _set_result(self, lines):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        for line in lines:
            self.result_text.insert("end", line + "\n")
        self.result_text.configure(state="disabled")

    def calculate(self) -> None:
        mtype = self.type_var.get()
        direct = mtype.startswith(("直伤月", "星超导", "星扩散直伤"))
        react_month = mtype.startswith("反应月")
        swirl = mtype.startswith("反应星扩散")

        # --- 解析参数 ---
        em = to_float(self.vars["em"].get(), 0.0)
        bb = to_percent(self.vars["base_boost"].get(), 0.0)   # 基础提升
        rb = to_percent(self.vars["bonus"].get(), 0.0)        # 反应增伤
        extra = to_float(self.vars["extra"].get(), 0.0)       # 额外提升
        res = to_percent(self.vars["res"].get(), 10.0)        # 抗性(小数)
        cr = to_percent(self.vars["cr"].get(), 50.0)          # 暴击率
        cd = to_percent(self.vars["cd"].get(), 100.0)         # 暴伤(小数)
        boost = 1 + to_percent(self.vars["boost"].get(), 0.0)  # 擢升
        lvl = int(to_float(self.vars["level"].get(), 90.0))
        cnt = int(to_float(self.vars["count"].get(), 1.0))
        mult = to_percent(self.vars["mult"].get(), 0.0)

        attr = damage.effective_stat(
            to_float(self.vars["attr_base"].get(), 0.0),
            big_bonus=to_percent(self.vars["attr_big"].get(), 0.0),
            flat_bonus=to_float(self.vars["attr_flat"].get(), 0.0),
        )
        em_term = damage.em_skill(em)
        mast = "(1+基提%s%%)×(1+EM%s+增伤%s%%)" % (
            fmt(bb * 100), fmt(em_term), fmt(rb * 100))

        # --- 直伤基础 / 反应基础值 ---
        base_desc = ""
        if react_month:
            rate = damage.MONTH_REACT_COEFF[mtype[2:]]
            base_v = damage.react_base(lvl) * rate * (1 + bb) * (1 + em_term + rb)
            base_desc = "反应值 = 基准%s × 倍率%s ×%s" % (
                fmt(damage.react_base(lvl)), fmt(rate), mast)
        elif swirl:
            sub = "风" if "风" in mtype else "冰"
            if sub == "风":
                rate = damage.STAR_SWIRL_WIND_BASE
                base_desc = "反应星扩散·风 = 基准%s × 0.75 ×%s" % (
                    fmt(damage.react_base(lvl)), mast)
            else:
                rate = damage.STAR_SWIRL_ICE_RATE.get(cnt, 2.0)
                base_desc = "反应星扩散·冰(风涡%s) = 基准%s × 倍率%s ×%s" % (
                    cnt, fmt(damage.react_base(lvl)), fmt(rate), mast)
            base_v = damage.react_base(lvl) * rate * (1 + bb) * (1 + em_term + rb)
        elif mtype.startswith("直伤月"):
            coeff = damage.MONTH_DIRECT_COEFF[mtype[2:]]
            base_v = coeff * attr * mult * (1 + bb) * (1 + em_term + rb)
            base_desc = "直伤基础 = 系数%s × 属性%s × 倍率%s%% ×%s" % (
                fmt(coeff), fmt(attr), fmt(mult * 100), mast)
        elif mtype == "星超导":
            rate = damage.STAR_SUPERCOND_RATE.get(cnt, 1.0)
            base_v = rate * attr * mult * (1 + bb) * (1 + em_term + rb)
            base_desc = "直伤基础 = 星超导倍率%s(hit%s) × 属性%s × 倍率%s%% ×%s" % (
                fmt(rate), cnt, fmt(attr), fmt(mult * 100), mast)
        else:  # 星扩散直伤
            base_v = attr * mult * (1 + bb) * (1 + em_term + rb)
            base_desc = "直伤基础 = 1 × 属性%s × 倍率%s%% ×%s" % (
                fmt(attr), fmt(mult * 100), mast)

        # --- 逐乘区累计 ---
        res_coeff = damage.resistance_coefficient(res)
        rv = base_v
        if direct and extra:
            rv += extra
        after_res = rv * res_coeff
        after_boost = after_res * boost      # 此时尚未乘暴击区 → 未暴击
        crit_val = after_boost * (1 + cd)
        cr_eff = min(cr, 1.0)                    # 有效暴击率封顶100%
        expected = after_boost * (1 + cr_eff * cd)

        # --- 输出 ---
        lines = ["【%s】" % mtype]
        if direct:
            lines.append("最终属性 = %s×(1+大%s%%)+小%s = %s" % (
                fmt(to_float(self.vars["attr_base"].get(), 0.0)),
                fmt(to_percent(self.vars["attr_big"].get(), 0.0) * 100),
                fmt(to_float(self.vars["attr_flat"].get(), 0.0)),
                fmt(attr)))
        lines.append("-" * 22)
        lines.append("【完整计算过程】")
        lines.append(base_desc + " = %s" % fmt(base_v))
        if direct and extra:
            lines.append("+ 额外提升 %s → %s" % (fmt(extra), fmt(rv)))
        lines.append("× 抗性系数 %s → %s" % (fmt(res_coeff), fmt(after_res)))
        lines.append("× 擢升(1+%s%%) → %s   (未暴击)" % (
            fmt((boost - 1) * 100), fmt(after_boost)))
        lines.append("× 暴击区(1+%s%%) → %s   (暴击)" % (
            fmt(cd * 100), fmt(crit_val)))
        lines.append("期望(1+%s%%×%s%%) = %s   (有效暴击封顶100%%)" % (
            fmt(cr_eff * 100), fmt(cd * 100), fmt(expected)))

        lines.append("-" * 22)
        lines.append("参与值(未暴击) : %s" % fmt(after_boost))
        lines.append("参与值(暴击)   : %s" % fmt(crit_val))
        lines.append("期望伤害       : %s" % fmt(expected))

        dist_txt = self.vars["dist"].get().strip()
        if dist_txt:
            parts = [p for p in re.split(r"[,，\s]+", dist_txt) if p]
            vals = [to_float(p, 0.0) for p in parts]
            if vals:
                if react_month:
                    w = damage.MONTH_FINAL_WEIGHTS[: len(vals)]
                    lines.append("分摊权重[%s]" % " ".join(
                        "{:.4f}".format(x) for x in w))
                    lines.append("分摊合计       : %s" % fmt(damage.distribute_damages(vals)))
                else:
                    lines.append("输入角色和     : %s" % fmt(sum(vals)))
        self._set_result(lines)

    def save_report(self) -> None:
        """把当前月/星计算的输入与结果保存为一个文件。"""
        default = _timestamp_name("月星反应")
        path = _save_as_file(default, "保存月/星反应计算")
        if not path:
            return
        rows = [("类型", self.type_var.get())]
        for label, key, _def, unit, _hint in self.FIELDS:
            v = self.vars[key].get().strip()
            if v:
                rows.append((label, "%s%s" % (v, " " + unit if unit else "")))
        body = self.result_text.get("1.0", "end")
        content = _compose_report(
            "原神 · 月/星 反应计算",
            [("输入参数", rows)], body)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.title("月 / 星 反应计算 · 已保存")


HELP_TEXT = """【基本概念】
· 每张卡片 = 一个乘区节点；左侧是输入端口，右侧是输出端口。
· 计算时从「★结果」卡片沿连线反向溯源求值；未接入结果的卡片不影响结果。
· 「＋加法」卡片有 2 个输入。

【连线】
· 从右侧输出端口按住拖到另一张卡片左侧输入端口即可连线。
· 点击连线可删除；卡片右上 ✕ 删除卡片（一并清理连线）。
· 「＋加法合并」卡片标题栏上有 `＋` 按钮，点一下增加一个输入端口（最多 12 个）。
· 鼠标悬停卡片时，与它相关的连线会高亮、其余变灰，便于追踪传递关系。

【添加卡片】
· 左侧“添加卡片”：基础值、增伤区、抗性区、防御区、暴击区、增幅反应、擢升、
  ＋加法、激化值、剧变反应、结晶护盾、属性源、基准值源、×系数、×倍率、
  ×(1+基础提升%)、×精通增益、星超导系数、计算卡、文本、变量、理想圣遗物、★结果。
· “星超导系数”只需填「层数(hit 0~12)」，系数自动查表（0→1.0 … 12→2.0，hit 1 起每层 +0.05）。
· “一键预设”可一键搭好一条链（不含★结果，需要汇总时自己接一张）：
  普通直伤 / 月·直伤 / 月·反应 / 星·超导 / 星·扩散 / 星·扩散直伤 / 剧变反应 / 激化值。

【摆放与缩放】
· 拖动卡片标题（或 ⣿）可在画布上自由摆放。
· 卡片右下角 ◢ 手柄可拖动改变大小；输入框随卡片宽度伸展。
· 画布缩放：工具栏 － / ＋ / 100%，或 Ctrl+滚轮（40%~250%）。
· 文本卡片：右键可调字号（字体 ＋/－、常用字号、重置、复制文本）。

【看结果】
· 结果直接显示在卡片上：★结果卡片（以及暴击区之后的卡片）显示
  未暴击 ｜ 暴击 ｜ 期望。
· 有效暴击率最多按 100% 计入（溢出截断）。
· 若结果链里没有「暴击区」，结果卡片会标注“← 无暴击区”。

【输入框用法】
· 所有数值 / 百分比输入框都支持算式：70+30、200*3、(100+50)*2、2**3。
· 兼容全角 × ÷ ＋ － （） 与千分位逗号。
· 可引用「变量」卡片里定义的变量名，如 攻击力+500、倍率/2。

【变量卡片】
· 每行定义一个变量，格式：名称 = 表达式（可引用前面已定义的变量）。
  例：攻击力 = 1000
      倍率 = 200
      基础伤害 = 攻击力 * 倍率
· 定义后，所有卡片的输入框与计算卡都能使用这些变量名。
· 卡片底部会显示已解析的变量值。

【计算卡】
· 无端口、不参与计算的小算盘：填表达式，实时显示结果。
· 点“复制”把输出数值复制到剪贴板（纯数字，便于直接粘贴到其它输入框）。

【理想圣遗物卡片】
· 一张只读的表格（属性 / 强化区间 / 最高区间 / 平均值，五星满强化）。
· 点单元格即可选中（蓝色高亮），按住拖动可选择一块矩形区域。
· 选中后按 Ctrl+C 复制：单格复制原文，多格/多行复制为 TSV（可直接粘进 Excel）；
  未选中时复制整表。没有复制按钮。

【增幅反应系数提醒】
· 蒸发·水打火 ×2.0 与 融化·火打冰 ×2.0 相同；
  蒸发·火打水 ×1.5 与 融化·冰打火 ×1.5 相同。
· 系数成对相同是游戏规则，选到同一档自然结果一样。

【工程与导出】
· 保存工程… / 打开工程…：整张画布（卡片、参数、连线、尺寸、缩放、变量）
  存为 JSON 文件，可随时完整恢复。
· 保存结果…：导出可读文本报告（含结果与节点求值过程）。

【快捷键】
· F1 打开 / 关闭本教程；Ctrl+滚轮 缩放画布。
· Ctrl+Z 撤销；Ctrl+Shift+Z（或 Ctrl+Y）重做（按编辑停顿自动记录一步）。
"""


class HelpWindow(tk.Toplevel):
    """F1 使用教程窗口。"""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("使用教程 (F1)")
        self.configure(bg=BG)
        self.transient(master)
        _center_window(self, 760, 620)
        txt = tk.Text(self, wrap="word", font=("Microsoft YaHei", 10),
                      padx=12, pady=10, bd=0, highlightthickness=1,
                      highlightbackground="#c3ccd6", bg="#ffffff")
        txt.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=6, padx=8)
        ttk.Button(bar, text="关闭 (Esc)", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F1>", self._close)      # 返回 "break" 阻止再触发主窗口的 F1
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.focus_set()

    def _close(self, event=None):
        self.destroy()
        return "break"


def main() -> None:
    app = DamageApp()
    app.mainloop()


if __name__ == "__main__":
    main()

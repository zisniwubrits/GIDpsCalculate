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

        self.update_button = ttk.Button(
            self.bottom, text="计算", command=self.calculate
        )
        self.update_button.pack(side="right", padx=12, pady=6)
        self.save_button = ttk.Button(
            self.bottom, text="保存结果…", command=self.save_report
        )
        self.save_button.pack(side="right", padx=4, pady=6)
        self.load_json_button = ttk.Button(
            self.bottom, text="打开工程…", command=self.load_project
        )
        self.load_json_button.pack(side="right", padx=4, pady=6)
        self.save_json_button = ttk.Button(
            self.bottom, text="保存工程…", command=self.save_project
        )
        self.save_json_button.pack(side="right", padx=4, pady=6)

        self.calculate()

    def _on_board_change(self) -> None:
        if hasattr(self, "board"):
            self.calculate()

    def save_project(self) -> None:
        """把整张画布（节点+连线+参数）以 JSON 保存为一个工程文件。"""
        path = _fd.asksaveasfilename(
            title="保存工程(JSON)",
            initialfile=_timestamp_name("伤害工程").replace(".txt", ".json"),
            defaultextension=".json",
            filetypes=[("JSON 工程", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.board.to_dict(), f, ensure_ascii=False, indent=2)
        self.title("原神伤害计算器 · 工程已保存")

    def load_project(self) -> None:
        """读取 JSON 工程并恢复到画布。"""
        path = _fd.askopenfilename(
            title="打开工程(JSON)",
            filetypes=[("JSON 工程", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        import json
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._set_result(["【打开失败】%s" % e])
            return
        self.board.from_dict(data)
        self.title("原神伤害计算器 · 已打开工程")
        self.calculate()

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


def main() -> None:
    app = DamageApp()
    app.mainloop()


if __name__ == "__main__":
    main()

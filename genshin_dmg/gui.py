# -*- coding: utf-8 -*-
"""
原神伤害计算 - tkinter 图形界面。

窗口内就是乘区节点画布（见 nodeboard.py），底部为文件与帮助按钮。

运行入口见仓库根目录 main.py：
    python main.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog as _fd
from tkinter import messagebox
import datetime

from genshin_dmg.nodeboard import NodeBoard

# 窗口配色
BG = "#f4f6f8"
ACCENT = "#2f6fa7"


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

        self._build_bottom_bar()
        self.bind_all("<F1>", lambda e: self.show_help())
        # 撤销 / 重做
        self.bind_all("<Control-z>", lambda e: (self.board.undo(), "break")[1])
        self.bind_all("<Control-Z>", lambda e: (self.board.redo(), "break")[1])
        self.bind_all("<Control-y>", lambda e: (self.board.redo(), "break")[1])

        self._set_project_name("")          # 标题显示工程名（未命名）
        self.calculate()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # 关闭前检查未保存改动
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        if getattr(self.board, "dirty", False):
            ans = messagebox.askyesnocancel(
                "未保存的修改",
                "当前工程有未保存的修改。\n\n要保存后再退出吗？",
                parent=self)
            if ans is None:                 # 取消
                return
            if ans:                         # 保存
                if not self.save_project():  # 用户在保存对话框里取消了
                    return
        self.destroy()

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

    def save_project(self) -> bool:
        """把整张画布（节点+连线+参数）以 JSON 保存为一个工程文件。成功返回 True。"""
        # 默认文件名使用当前工程名（导入时得到的名称）
        base = self.board.project_name or _timestamp_name("伤害工程").replace(".txt", "")
        path = _fd.asksaveasfilename(
            title="保存工程(JSON)",
            initialfile="%s.json" % base,
            defaultextension=".json",
            filetypes=[("JSON 工程", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return False
        import json
        import os
        name = os.path.splitext(os.path.basename(path))[0]
        self.board.project_name = name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.board.to_dict(), f, ensure_ascii=False, indent=2)
        self.board.dirty = False
        self._set_project_name(name)
        return True

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
        self.board.dirty = False
        self._set_project_name(name)
        self.calculate()

    def _set_project_name(self, name: str) -> None:
        """工程名显示在窗口标题上。"""
        self.title("原神伤害计算器 · %s" % (name or "未命名"))

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
                             "暴击/期望与未暴击相同（结果卡片只显示单个数值）。")
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


HELP_TEXT = """【基本概念】
· 每张卡片 = 一个乘区节点；左侧是输入端口，右侧是输出端口。
· 计算时从「★结果」卡片沿连线反向溯源求值；未接入结果的卡片不影响结果。
· 「＋加法」卡片有 2 个输入。

【连线】
· 从右侧输出端口按住拖到另一张卡片左侧输入端口即可连线。
· 点击连线可删除；卡片右上 ✕ 删除卡片（一并清理连线）。
· 「＋加法合并」卡片标题栏上有 `＋` 按钮，点一下增加一个输入端口（最多 12 个）。
· 鼠标悬停卡片时，与它相关的连线会高亮、其余变灰，便于追踪传递关系。

【多选与对齐】
· 按住 Shift 点卡片标题 = 多选 / 取消多选（标题变蓝）。
· 左侧「选中的卡片」区可对选中卡片做 左对齐 / 顶对齐 / 水平居中 / 垂直居中。

【关闭与保存】
· 有未保存改动时关闭窗口会问「保存 / 不保存 / 取消」。
· Ctrl+Z 撤销、Ctrl+Shift+Z（或 Ctrl+Y）重做。

【添加卡片】
· 左侧“添加卡片”：基础值、增伤区、抗性区、防御区、暴击区、增幅反应、擢升、
  ＋加法、激化值、剧变反应、结晶护盾、属性源、基准值源、×系数、×倍率、
  ×(1+基础提升%)、×精通增益、星超导系数、计算卡、文本、变量、变量表、理想圣遗物、★结果。
· “星超导系数”只需填「层数(hit 0~12)」，系数自动查表（0→1.0 … 12→2.0，hit 1 起每层 +0.05）。
· “★结果”卡片**外观与原来一致**，不显示额外输入框；在卡片上**点右键**选「设置结果变量…」，
  可把三元组分别命名为变量（未暴击 / 暴击 / 期望，三者各自独立命名，留空 = 不定义），
  之后任何数值框、变量卡片、计算卡都能引用（例：期望变量填 期望伤害，
  计算卡写 期望伤害/20*60 即得 DPS）。右键菜单里的「清除结果变量」可一键清空。
· “一键预设”可一键搭好一条链（不含★结果，需要汇总时自己接一张）：
  普通直伤 / 月·直伤 / 月·反应 / 星·超导 / 星·扩散 / 星·扩散直伤 / 剧变反应 / 激化值。

【摆放与缩放】
· 拖动卡片标题（或 ⣿）可在画布上自由摆放。
· 卡片右下角 ◢ 手柄可拖动改变大小；输入框随卡片宽度伸展。
· 画布缩放：工具栏 － / ＋ / 100%，或 Ctrl+滚轮（40%~250%）。
· 文本卡片：右键可调字号（字体 ＋/－、常用字号、重置、复制文本）。

【看结果】
· 每张卡片的“本卡系数”统一用 × 前缀显示，如 `抗性系数 ×1.200`、`暴击系数 ×2.000 ｜ 期望系数 ×1.500`。
· 结果直接显示在卡片上：链上经过「暴击区」时，★结果卡片（以及暴击区之后的卡片）显示
  未暴击 ｜ 暴击 ｜ 期望；没有暴击区时只显示一个数值（★结果卡片显示“结果 …”），简洁明了，
  若该结果已绑定变量名，还会跟在后面，如 `结果 2000.00 ｜ 变量 期望伤害`。
· 有效暴击率最多按 100% 计入（溢出截断）。
· 「变量表」卡片会实时列出当前所有可用变量（变量卡片定义的 + ★结果卡片命名的），
  可拖选单元格后 Ctrl+C 复制（未选中时复制整表）。

【输入框用法】
· 所有数值 / 百分比输入框都支持算式：70+30、200*3、(100+50)*2、2**3。
· 兼容全角 × ÷ ＋ － （） 与千分位逗号。
· 可引用「变量」卡片里定义的变量名，以及「★结果」卡片命名的三元组变量，
  如 攻击力+500、倍率/2、期望伤害/20*60。

【变量卡片】
· 每行定义一个变量，格式：名称 = 表达式（可引用前面已定义的变量）。
  例：攻击力 = 1000
      倍率 = 200
      基础伤害 = 攻击力 * 倍率
· 定义后，所有卡片的输入框与计算卡都能使用这些变量名。
· 卡片底部会显示已解析的变量值。
· 「★结果」卡片也可命名三元组变量：在卡片上**点右键 →「设置结果变量…」**
  （未暴击 / 暴击 / 期望，各自独立填名，留空即不定义），之后就与变量卡片一样通用，
  如 秒伤 = 期望伤害/20*60。同名时以结果卡片上的名字为准；
  请勿让结果链本身又依赖由结果变量算出的变量（会形成循环）。
· 「变量表」卡片（调色板「变量表」）样式与「理想圣遗物」卡片相同：两列（变量 / 值），
  实时列出当前所有可用变量，可拖选单元格后 Ctrl+C 复制。

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

# -*- coding: utf-8 -*-
"""圣遗物子系统的**独立性**检查（对拍 + 静态 import 检查）。

`GIRelic/` 里搬了两份主程序的副本（见 `GIRelic/AGENTS.md` §10）：

* `relic_tables.py`  ← `genshin_dmg/nodes.py` 的 `RELIC_ROWS`
* `relic_math.py`    ← `genshin_dmg/expr.py` 的 `mangle` / `_FULLWIDTH`
                        + `genshin_dmg/damage.py` 的 `resistance_coefficient` / `defense_coefficient`

副本必须与主体**逐值一致**：主体改了而副本没跟 → 这两组用例会红。
整目录搬走时本文件一并删掉即可（那时没有"主体"可对拍）。
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from genshin_dmg import damage, expr, nodes
from genshin_dmg.GIRelic import relic_math, relic_tables

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "genshin_dmg" / "GIRelic"
# 允许（暂时）出现的跨包依赖：adapter 层落地前 relic.py 里的惰性 Graph import
_PENDING_GRAPH = {"relic.py", "relic_program.py"}


# ---------------------------------------------------------------- 参考表
def test_relic_rows_match_main():
    assert relic_tables.RELIC_ROWS == [list(r) for r in nodes.RELIC_ROWS] or \
        relic_tables.RELIC_ROWS == nodes.RELIC_ROWS


def test_relic_header_matches_main():
    assert relic_tables.RELIC_HEADER == nodes.RELIC_HEADER


# ---------------------------------------------------------------- 文本工具
@pytest.mark.parametrize("text", [
    "",
    "plain",
    "atk",
    "角色::out::atk",
    "::out::atk",
    "A::B::C",
    "A :: B",
    "角色::变量 + 100",
    "x::y::z::w",
    "::",
    ":: ::",
])
def test_mangle_matches_main(text):
    assert relic_math.mangle(text) == expr.mangle(text)


def test_fullwidth_matches_main():
    assert relic_math.FULLWIDTH == expr._FULLWIDTH


# ---------------------------------------------------------------- 伤害系数
_RES_GRID = [-1.5, -1.0, -0.25, 0.0, 0.1, 0.3, 0.5, 0.75, 0.7500001, 0.9, 1.5, 2.5]


@pytest.mark.parametrize("res", _RES_GRID)
def test_resistance_coefficient_matches_main(res):
    assert relic_math.resistance_coefficient(res) == pytest.approx(
        damage.resistance_coefficient(res), rel=0, abs=1e-12)


def test_defense_coefficient_matches_main():
    for char_level in (1.0, 80.0, 90.0, 100.0):
        for enemy_level in (1.0, 85.0, 90.0, 93.0, 100.0):
            for dr in (0.0, 0.1, 0.4, 0.9, 1.5):          # 1.5 → 被 clamp 到 0.9
                for ide in (0.0, 0.2, 1.0, 1.7):          # 1.7 → 被 clamp 到 1.0
                    assert relic_math.defense_coefficient(
                        char_level, enemy_level, def_reduction=dr, ignore_def=ide,
                    ) == pytest.approx(
                        damage.defense_coefficient(
                            char_level, enemy_level, def_reduction=dr, ignore_def=ide),
                        rel=0, abs=1e-12)


def test_clamp_matches_main():
    for v in (-5.0, 0.0, 0.5, 1.0, 7.0):
        assert relic_math.clamp(v, 0.0, 0.9) == damage.clamp(v, 0.0, 0.9)


# ---------------------------------------------------------------- 静态 import 检查
def _module_level_imports(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for stmt in tree.body:                     # 只看模块顶层，函数内的惰性 import 不算
        if isinstance(stmt, ast.Import):
            names += [a.name for a in stmt.names]
        elif isinstance(stmt, ast.ImportFrom) and stmt.module:
            names.append(stmt.module)
    return names


def _all_imports(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", sorted(PKG.glob("*.py")), ids=lambda p: p.name)
def test_no_main_package_imports(path):
    """`GIRelic/` 里不许 import 主程序的实现模块（只许 import 自己）。"""
    banned = ("genshin_dmg.nodes", "genshin_dmg.damage", "genshin_dmg.expr")
    assert not [m for m in _all_imports(path) if m in banned], path.name


@pytest.mark.parametrize("path", sorted(PKG.glob("*.py")), ids=lambda p: p.name)
def test_graph_import_is_lazy_and_temporary(path):
    """`graph.py` 只能在函数内惰性 import，且只允许那一个待迁移的文件。"""
    if path.name not in _PENDING_GRAPH:
        assert not [m for m in _all_imports(path) if m == "genshin_dmg.graph"], path.name
    assert not [m for m in _module_level_imports(path) if m == "genshin_dmg.graph"], path.name


def test_importing_relic_does_not_pull_main_modules():
    """在干净解释器里 import 圣遗物层，不得拉进节点表 / 表达式 / 图求值。

    例外只有 `genshin_dmg.damage`：那是包 `__init__.py` 自己导出的，与圣遗物层无关。
    """
    code = (
        "import sys\n"
        "import genshin_dmg.GIRelic.relic as r\n"
        "import genshin_dmg.GIRelic.relic_program as p\n"
        "import genshin_dmg.GIRelic.relic_math as m\n"
        "import genshin_dmg.GIRelic.relic_tables as t\n"
        "bad = [x for x in ('genshin_dmg.nodes', 'genshin_dmg.expr', 'genshin_dmg.graph')\n"
        "       if x in sys.modules]\n"
        "print(','.join(bad))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", out.stdout

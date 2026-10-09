# -*- coding: utf-8 -*-
"""工程的落盘存储：记住「当前工程目录」，一键保存工程 JSON / 导出报告 txt。

设计要点（与用户确认过的口径）：

* **从哪读就往哪存**：打开工程时记住该文件所在目录，保存就写回那个目录；
* 还没有记忆目录时（首次使用）落到 ``private/projects/``（已被 .gitignore 忽略）；
* 记忆写在 ``private/save_config.json``，属于个人本地状态，不进版本库；
* 一键保存 = 无对话框、直接覆盖同名文件（Ctrl+S 语义）；
* 导出报告用 ``<工程名>_<时间戳>.txt``，每次一个新文件，不会互相覆盖。

本模块只负责「路径与读写」，不依赖 FastAPI、也不参与伤害计算，方便单测。
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

__all__ = [
    "ROOT",
    "DEFAULT_DIR",
    "CONFIG_PATH",
    "DEFAULT_PROJECT_NAME",
    "DEFAULT_REPORT_PREFIX",
    "info",
    "current_dir",
    "remember_path",
    "safe_name",
    "project_file",
    "report_file",
    "write_json",
    "write_text",
    "read_graph",
    "abs_path",
]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "private" / "projects"
CONFIG_PATH = ROOT / "private" / "save_config.json"

DEFAULT_PROJECT_NAME = "伤害工程"
DEFAULT_REPORT_PREFIX = "直伤伤害"

# Windows 文件名非法字符 + 控制字符；顺带挡掉路径分隔符，避免写出目录之外
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_NAME = 80


# ---------------------------------------------------------------------------
# 记忆目录
# ---------------------------------------------------------------------------
def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _store_config(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        # 记不住目录不该让保存失败：本次照常写文件，下次退回默认目录
        pass


def current_dir() -> Path:
    """当前工程目录：优先用记忆的，其次默认目录。返回绝对路径（不保证已存在）。"""
    raw = _load_config().get("dir")
    if isinstance(raw, str) and raw.strip():
        try:
            return Path(raw).expanduser().resolve()
        except OSError:
            pass
    return DEFAULT_DIR.resolve()


def remember_path(path) -> Path:
    """记住「这个文件（或目录）所在的地方」，后续保存就写到这里。"""
    p = Path(path).expanduser()
    directory = p if p.is_dir() else p.parent
    directory = directory.resolve()
    data = _load_config()
    data["dir"] = str(directory)
    data["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _store_config(data)
    return directory


def info() -> dict:
    """给前端显示用的目录信息。"""
    current = current_dir()
    return dict(
        dir=str(current),
        defaultDir=str(DEFAULT_DIR.resolve()),
        configFile=str(CONFIG_PATH),
        exists=current.is_dir(),
    )


# ---------------------------------------------------------------------------
# 文件名与路径
# ---------------------------------------------------------------------------
def safe_name(raw, fallback: str = DEFAULT_PROJECT_NAME) -> str:
    """把工程名清洗成安全的文件名（去掉非法字符/首尾点号/空白），空则用 fallback。"""
    name = _ILLEGAL.sub("_", str(raw or "")).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if not name:
        return fallback
    return name[:_MAX_NAME]


def project_file(project_name) -> Path:
    """工程 JSON 的落盘路径（覆盖式一键保存）。"""
    return current_dir() / ("%s.json" % safe_name(project_name, DEFAULT_PROJECT_NAME))


def report_file(project_name, now: datetime.datetime | None = None) -> Path:
    """报告 txt 的落盘路径：``<工程名>_<时间戳>.txt``（每次新文件）。"""
    prefix = safe_name(project_name, DEFAULT_REPORT_PREFIX)
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M%S")
    return current_dir() / ("%s_%s.txt" % (prefix, stamp))


# ---------------------------------------------------------------------------
# 写文件
# ---------------------------------------------------------------------------
def _prepare(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data) -> Path:
    """把工程写成可读 JSON（UTF-8、缩进 2、不转义中文）。"""
    _prepare(path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def write_text(path: Path, text: str) -> Path:
    _prepare(path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def read_graph(path) -> dict:
    """读取工程 JSON；不存在/非法时抛 ValueError（由接口层转成 4xx）。"""
    p = Path(path)
    if not p.is_file():
        raise ValueError("文件不存在：%s" % p)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError("读取失败：%s" % e)
    if not isinstance(data, dict):
        raise ValueError("不是合法的工程文件")
    return data


def abs_path(path) -> str:
    """统一成绝对路径字符串（前端显示用）。"""
    return str(Path(path).resolve())

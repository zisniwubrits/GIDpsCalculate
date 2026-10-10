# -*- coding: utf-8 -*-
"""前端构建产物是否过期 —— 三处共用的唯一判定逻辑。

**要解决的问题**：`git pull` 拿到新前端源码后如果没有重新 `pnpm build`，
后端会继续把旧的 `web/dist` 交给浏览器 —— 接口全部正常、界面却缺功能。
这种「静默错位」很难查，所以把判定收在这里，供：

* 启动器 `launcher.bat`：过期就自动重建（而不是只看 dist 是否存在）；
* `GET /api/health`：把 ``webStale`` 告诉前端，界面能提示；
* `main.py` 启动时：在终端打一行明确的警告与修复命令。

判定规则：``web/dist/index.html`` 不存在 → 算过期；否则看**前端源码里最新的修改时间**
是否晚于产物时间。监视范围：``web/src`` 下所有文件 + 几个工程配置文件
（``index.html`` / ``package.json`` / ``vite.config.ts`` / ``tsconfig.json`` / 锁文件）。

用法：``python -m server.build_check``（0 = 新鲜，1 = 过期或缺失，2 = 出错），
加 ``--json`` 输出状态；``--print`` 额外打印可读结论。
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

__all__ = [
    "WEB_DIR",
    "DIST_INDEX",
    "SOURCE_DIR",
    "SOURCE_FILES",
    "source_mtime",
    "dist_mtime",
    "is_stale",
    "status",
    "status_for_dist",
    "format_time",
    "main",
]

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DIST_INDEX = WEB_DIR / "dist" / "index.html"
SOURCE_DIR = "src"
# 这些文件一变，产物就该重建（少了任何一项都可能让浏览器拿到旧界面）
SOURCE_FILES = (
    "index.html",
    "package.json",
    "vite.config.ts",
    "tsconfig.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
)
# 遍历源码目录时跳过的东西
_SKIP_DIRS = {"node_modules", "dist", ".vite", "__pycache__"}


def format_time(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _iter_source_files(web_dir: Path):
    """产出参与比较的所有源码文件（可能不存在，由调用方判断）。"""
    src = web_dir / SOURCE_DIR
    if src.is_dir():
        for path in src.rglob("*"):
            if path.is_file() and not any(part in _SKIP_DIRS for part in path.parts):
                yield path
    for name in SOURCE_FILES:
        yield web_dir / name


def source_mtime(web_dir: Path | None = None) -> float:
    """前端源码的最新修改时间；一个文件都没有时返回 0。"""
    web_dir = Path(web_dir or WEB_DIR)
    newest = 0.0
    for path in _iter_source_files(web_dir):
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
    return newest


def dist_mtime(web_dir: Path | None = None) -> float | None:
    """构建产物（web/dist/index.html）的修改时间；不存在返回 None。"""
    web_dir = Path(web_dir or WEB_DIR)
    index = web_dir / "dist" / "index.html"
    try:
        return index.stat().st_mtime
    except OSError:
        return None


def is_stale(web_dir: Path | None = None) -> bool:
    """没有产物，或产物比源码旧 → True（该重新构建）。"""
    built = dist_mtime(web_dir)
    if built is None:
        return True
    return source_mtime(web_dir) > built


def status(web_dir: Path | None = None) -> dict:
    """给接口/启动提示用的状态（都是可 JSON 序列化的基本类型）。

    ``web_dir`` 是**前端工程目录**（里面应有 ``src/`` 与 ``dist/``）。
    只有 ``web/dist`` 路径时请用 :func:`status_for_dist`，别自己拼错层级。
    """
    web_dir = Path(web_dir or WEB_DIR)
    built = dist_mtime(web_dir)
    src = source_mtime(web_dir)
    stale = built is None or src > built
    return dict(
        webDir=str(web_dir),
        distIndex=str(web_dir / "dist" / "index.html"),
        built=built is not None,
        stale=stale,
        buildTime=format_time(built),
        sourceTime=format_time(src),
        reason=("还没有构建产物" if built is None
                else "前端源码比构建产物新" if stale
                else "产物是最新的"),
    )


def status_for_dist(dist_dir) -> dict:
    """按「dist 目录」判断（server/app.py 只拿得到 web/dist）。

    单独提供这个入口是为了不再出现「把 web/dist 当成 web/ 传进去」这种层级错误 ——
    那会让产物明明在、却被判成「还没有构建产物」。
    """
    return status(Path(dist_dir).parent)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="build_check",
                                     description="检查 web/dist 是否比前端源码旧")
    parser.add_argument("--json", action="store_true", help="输出 JSON 状态")
    parser.add_argument("--print", dest="show", action="store_true",
                        help="额外打印一行可读结论")
    parser.add_argument("--web-dir", default=str(WEB_DIR), help="前端目录（默认 web/）")
    args = parser.parse_args(argv)

    try:
        state = status(Path(args.web_dir))
    except OSError as e:                                    # pragma: no cover
        print("检查失败：%s" % e, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(state, ensure_ascii=False))
    if args.show or not args.json:
        print("前端产物：%s（%s；源码最新 %s）" % (
            state["buildTime"] or "无", state["reason"], state["sourceTime"] or "无"))
    return 1 if state["stale"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

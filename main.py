# -*- coding: utf-8 -*-
"""原神伤害计算器 —— 启动入口（Web 后端 + 静态托管）。

用法：
    python main.py                  # 启动后端并打开浏览器（127.0.0.1:8777）
    python main.py --port 9000      # 换端口（前端开发时用 DSH_API 指向它）
    python main.py --reload         # 开发时热重载
    python main.py --no-browser     # 不自动打开浏览器

开发前端（推荐，改代码即时生效）：
    cd web
    pnpm install
    pnpm dev        # 打开 http://127.0.0.1:5173 ，/api 已代理到本后端

生产构建（由后端直接托管）：
    cd web && pnpm build        # 产物在 web/dist，然后刷新 http://127.0.0.1:8777
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

from server import build_check

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8777


def _open_browser_later(url: str, delay: float = 1.2) -> None:
    threading.Timer(delay, lambda: webbrowser.open(url)).start()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="main.py", description="原神伤害计算器（Web）")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="端口（默认 8000）")
    parser.add_argument("--reload", action="store_true", help="代码热重载（开发用）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        print("缺少依赖：pip install -r requirements.txt", file=sys.stderr)
        return 1

    url = "http://%s:%d" % (args.host, args.port)
    state = build_check.status()
    print("原神伤害计算器后端： %s" % url)
    if not state["built"]:
        print("前端构建产物： 未构建 —— 开发请另开终端跑 cd web && pnpm dev，"
              "或先 cd web && pnpm build")
    elif state["stale"]:
        # 关键提醒：接口会完全正常，但浏览器拿到的是旧界面（缺新功能），极难自行发现
        print("=" * 66)
        print("【注意】前端产物已过期：%s" % state["reason"])
        print("        产物时间 %s ／ 源码最新 %s" % (state["buildTime"], state["sourceTime"]))
        print("        浏览器会继续显示旧界面（接口正常但缺新功能）。请执行：")
        print("            cd web && pnpm build")
        print("        或直接用 launcher.bat 启动（它会自动重建）。")
        print("=" * 66)
    else:
        print("前端构建产物： 已就绪（%s）" % state["buildTime"])
    if not args.no_browser:
        _open_browser_later(url)

    uvicorn.run("server.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

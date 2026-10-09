# -*- coding: utf-8 -*-
"""Web 后端包（FastAPI）。

启动见仓库根目录 ``main.py``：

    python main.py                 # 127.0.0.1:8000
    python main.py --port 9000     # 换端口
    python main.py --reload        # 开发时热重载
"""

from server.app import app, create_app, WEB_DIST

__all__ = ["app", "create_app", "WEB_DIST"]

# -*- coding: utf-8 -*-
"""Web 后端包（FastAPI）。

启动见仓库根目录 ``main.py``：

    python main.py                 # 127.0.0.1:8777
    python main.py --port 9000     # 换端口
    python main.py --reload        # 开发时热重载

这里**刻意不在包导入时就拉 FastAPI 应用**：`server.storage` / `server.dialogs` /
`server.build_check` 都是可独立使用的纯模块（启动器会直接
``python -m server.build_check``），若本文件 import 了 ``server.app``，
那三处都会连带加载 FastAPI 并触发 runpy 的 “already in sys.modules” 警告。

需要应用对象时显式写 ``from server.app import app``（或让 uvicorn 用
``server.app:app`` 字符串导入）。
"""

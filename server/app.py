# -*- coding: utf-8 -*-
"""原神伤害计算器 —— Web 后端（FastAPI）。

职责边界（重要）：

* **公式与图求值只在 Python 这一份**（``genshin_dmg/``）：
  前端不做任何伤害计算，只把整张图 POST 上来，拿回每个卡片的显示数据。
* 前端（``web/``，Vite + React）负责画布交互与渲染，开发时用 Vite 代理 ``/api``。

接口：

===========================  ==========================================
``GET  /api/health``         健康检查
``GET  /api/schema``         卡片类型 / 菜单分组 / 预设 / 参考表（前端单一数据源）
``GET  /api/help``           F1 使用教程文本
``POST /api/evaluate``       传入整张图（工程 JSON），返回全部节点结果
``POST /api/report``         传入整张图，生成文本报告并写到当前工程目录
``GET  /api/storage``        当前工程目录（记忆目录）
``POST /api/save/project``   一键保存工程 JSON（覆盖，写回当前工程目录）
``POST /api/open``           弹本机原生对话框打开工程，并记住其所在目录
``GET  /``                   生产构建产物（``web/dist``）；未构建时给出提示页
===========================  ==========================================
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from genshin_dmg import __version__, nodes, report, tutorial
from genshin_dmg.graph import Graph, GraphError
from server import dialogs, storage

__all__ = ["app", "create_app", "WEB_DIST"]

# 仓库根目录 / web/dist
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIST = os.path.join(_ROOT, "web", "dist")

DEV_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
]

_FALLBACK_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>原神伤害计算器 · 后端已就绪</title>
<style>
 body{font-family:"Microsoft YaHei",system-ui,sans-serif;background:#f4f6f8;color:#22303c;
      margin:0;padding:48px;line-height:1.8}
 .box{max-width:720px;margin:0 auto;background:#fff;border:1px solid #dbe3ea;
      border-radius:10px;padding:28px 32px}
 h1{font-size:20px;margin:0 0 4px;color:#2f6fa7}
 code{background:#eef3f8;border-radius:4px;padding:2px 6px;font-size:13px}
 li{margin:4px 0}
 a{color:#2f6fa7}
</style></head><body><div class="box">
<h1>后端已启动 ✓</h1>
<p>但还没有找到前端构建产物 <code>web/dist</code>。</p>
<p><b>开发模式</b>（推荐）：另开一个终端启动 Vite，浏览器访问它即可：</p>
<ol>
 <li><code>cd web &amp;&amp; pnpm install</code></li>
 <li><code>pnpm dev</code> → 打开 <a href="http://127.0.0.1:5173">http://127.0.0.1:5173</a></li>
</ol>
<p><b>生产模式</b>：先构建前端，再刷新本页即可由后端直接托管：</p>
<ol><li><code>cd web &amp;&amp; pnpm build</code></li></ol>
<p>接口自查：<a href="/api/health">/api/health</a> ·
<a href="/api/schema">/api/schema</a> ·
<a href="/docs">/docs</a></p>
</div></body></html>
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="原神伤害计算器 API",
        version=__version__,
        description="乘区节点图求值后端：公式只在 Python 一份，前端只负责渲染。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEV_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return dict(ok=True, app="GenshinDamageCalc", version=__version__,
                    webBuilt=os.path.isfile(os.path.join(WEB_DIST, "index.html")))

    @app.get("/api/schema")
    def get_schema():
        """前端渲染所需的全部描述（卡片类型、菜单、预设、参考表）。"""
        return nodes.schema()

    @app.get("/api/help")
    def get_help():
        return dict(text=tutorial.HELP_TEXT, sections=tutorial.SECTIONS)

    @app.post("/api/evaluate")
    async def evaluate(request: Request):
        """传入整张图（与工程 JSON 同格式），返回变量表、每个节点输出与最终结果。"""
        try:
            data = await request.json()
        except Exception as e:
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="请求体不是合法 JSON：%s" % e))
        if not isinstance(data, dict):
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="请求体必须是工程对象"))
        try:
            graph = Graph.from_dict(data.get("graph") if "graph" in data else data)
            out = graph.evaluate()
        except GraphError as e:
            return JSONResponse(status_code=400, content=dict(ok=False, error=str(e)))
        except Exception as e:                                  # 计算异常也返回结构化错误
            return JSONResponse(status_code=200, content=dict(
                ok=False, error=str(e), nodes={}, variables=[],
                result=None, chainTypes=[], warnings=[]))
        out["graph"] = graph.to_dict()      # 回传规范化后的图（字段类型已统一）
        return out

    @app.post("/api/report")
    async def make_report(request: Request):
        """生成可读文本报告（含结果与节点求值过程）并直接写到「当前工程目录」。

        文件名规则：``<工程名>_<时间戳>.txt``（每次新文件，不覆盖旧报告）。
        """
        try:
            data = await request.json()
        except Exception as e:
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="请求体不是合法 JSON：%s" % e))
        try:
            graph = Graph.from_dict(data.get("graph") if isinstance(data, dict) and "graph" in data else data)
            now = datetime.datetime.now()
            text = report.build_report(
                graph, title=data.get("title") or report.APP_TITLE,
                timestamp=now.strftime("%Y-%m-%d %H:%M:%S"))
            name = (data.get("name") if isinstance(data, dict) else "") or ""
            path = storage.report_file(name, now)
            storage.write_text(path, text)
        except GraphError as e:
            return JSONResponse(status_code=400, content=dict(ok=False, error=str(e)))
        except OSError as e:
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="写入失败：%s" % e))
        return dict(ok=True, path=storage.abs_path(path), dir=str(path.parent),
                    filename=path.name, text=text)

    # ------------------------------------------------------------------
    # 工程落盘（一键保存 / 打开）
    # ------------------------------------------------------------------
    @app.get("/api/storage")
    def get_storage():
        """当前工程目录（前端在工具栏显示，便于确认「存哪儿」）。"""
        return storage.info()

    @app.post("/api/save/project")
    async def save_project(request: Request):
        """一键保存工程 JSON：写到「当前工程目录/<工程名>.json」，直接覆盖。

        目录记忆规则见 server/storage.py：打开工程时记住该文件所在目录，从哪读就往哪存；
        还没记忆目录时落到 private/projects/。
        """
        try:
            data = await request.json()
        except Exception as e:
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="请求体不是合法 JSON：%s" % e))
        if not isinstance(data, dict):
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="请求体必须是工程对象"))
        try:
            path = storage.project_file(data.get("name"))
            storage.write_json(path, data)
        except OSError as e:
            return JSONResponse(status_code=400,
                                content=dict(ok=False, error="写入失败：%s" % e))
        return dict(ok=True, path=storage.abs_path(path), dir=str(path.parent),
                    filename=path.name)

    @app.post("/api/open")
    def open_project():
        """弹本机原生「打开文件」对话框选工程，读回内容并记住它所在目录。

        用户取消（或没有图形环境）时返回 ``ok=False, cancelled=True``，前端静默处理。
        """
        try:
            chosen = dialogs.pick_open_file(storage.current_dir())
        except Exception as e:                                  # 弹窗异常不该 500
            return JSONResponse(status_code=200,
                                content=dict(ok=False, error="打开对话框失败：%s" % e))
        if not chosen:
            return dict(ok=False, cancelled=True)
        try:
            graph = storage.read_graph(chosen)
        except ValueError as e:
            return JSONResponse(status_code=400, content=dict(ok=False, error=str(e)))
        storage.remember_path(chosen)         # 从哪读就往哪存
        return dict(ok=True, path=storage.abs_path(chosen), dir=str(Path(chosen).parent),
                    graph=graph, storage=storage.info())

    # ------------------------------------------------------------------
    # 生产构建产物（web/dist）
    # ------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def index():
        page = os.path.join(WEB_DIST, "index.html")
        if os.path.isfile(page):
            return FileResponse(page, media_type="text/html")
        return HTMLResponse(_FALLBACK_HTML)

    @app.get("/{path:path}")
    def static_files(path: str):
        """静态资源；未命中的路径回落到 index.html（前端路由用）。"""
        if path.startswith("api/") or path in ("docs", "openapi.json", "redoc"):
            return JSONResponse(status_code=404, content=dict(ok=False, error="未知接口"))
        full = os.path.normpath(os.path.join(WEB_DIST, path))
        if full.startswith(WEB_DIST) and os.path.isfile(full):
            return FileResponse(full)
        page = os.path.join(WEB_DIST, "index.html")
        if os.path.isfile(page):
            return FileResponse(page, media_type="text/html")
        return HTMLResponse(_FALLBACK_HTML, status_code=200)

    return app


app = create_app()

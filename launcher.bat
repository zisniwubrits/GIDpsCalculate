@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem ===========================================================================
rem  原神伤害计算器（Web 版）—— 本地启动 / 关闭
rem
rem  双击运行            → 出现菜单（启动 / 关闭 / 开发模式 / 退出）
rem  launcher.bat 9000        → 直接用 9000 端口启动
rem  launcher.bat stop        → 关闭默认端口（8777）上的服务
rem  launcher.bat stop 9000   → 关闭 9000 端口上的服务
rem  launcher.bat dev         → 开发模式：后端 + Vite（前端热更新，需 Node）
rem  launcher.bat 8777 --reload
rem                            → 端口后面的参数原样转给 main.py
rem                              （常用：--reload 后端热重载 / --no-browser 不开浏览器）
rem
rem  首次启动会自动补齐（都在 .gitignore 中，新克隆的仓库没有）：
rem    web\dist\     前端构建产物  → 自动 install + build
rem    后端依赖      fastapi/uvicorn → 优先用已装好的 python，缺了才建 .venv 并安装
rem ===========================================================================

set "ROOT=%~dp0"
set "PY=python"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

rem ---- 解析参数：stop [端口] / dev [端口] / [端口] [额外参数] / 无参走菜单 ----
set "ACTION=%~1"
set "PORT=%~2"
set "FLAG=%~3"

if /i "%ACTION%"=="stop" goto :resolve_port
if /i "%ACTION%"=="dev" goto :resolve_port
if "%ACTION%"=="" goto :resolve_port
rem 第一个参数既不是 stop/dev 也不是空 → 当作端口号，直接启动
rem （注意必须显式设成 start，清空会掉进下面的菜单分支，脚本调用时会挂住）
set "PORT=%~1"
set "FLAG=%~2"
set "ACTION=start"

:resolve_port
if "%PORT%"=="" set "PORT=8777"
set "URL=http://127.0.0.1:%PORT%"
set "DEV_URL=http://127.0.0.1:5173"
title 原神伤害计算器 (%PORT%)

if not defined ACTION call :menu

if /i "%ACTION%"=="stop" goto :stop
if /i "%ACTION%"=="quit" exit /b 0
if /i "%ACTION%"=="dev" goto :dev
goto :start

rem ===========================================================================
rem  菜单（双击时用）
rem ===========================================================================
:menu
set "FROM_MENU=1"
cls
echo.
echo   原神伤害计算器（Web 版）
echo   ------------------------------------------------------------
echo     项目目录：%ROOT%
echo     端口　　：%PORT%
echo.
echo     [1] 启动服务（并打开浏览器）
echo     [2] 关闭服务
echo     [3] 开发模式（前端热更新，需 Node）
echo     [4] 退出
echo.
set "SEL="
set /p "SEL=   请选择 [1]: "
if "%SEL%"=="" goto :menu_start
if "%SEL%"=="1" goto :menu_start
if "%SEL%"=="2" goto :menu_stop
if "%SEL%"=="3" goto :menu_dev
if "%SEL%"=="4" goto :menu_quit
echo.
echo    无效输入。
ping -n 2 127.0.0.1 >nul
goto :menu

:menu_start
set "ACTION=start"
goto :eof

:menu_stop
set "ACTION=stop"
goto :eof

:menu_dev
set "ACTION=dev"
goto :eof

:menu_quit
set "ACTION=quit"
goto :eof

rem ===========================================================================
rem  关闭服务
rem ===========================================================================
:stop
cls
echo.
echo   正在关闭 %URL% 上的服务...
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr /C:":%PORT% "') do (
    set "FOUND=1"
    echo     结束进程 PID %%p
    taskkill /PID %%p /T /F >nul 2>nul
)
if not defined FOUND (
    echo     没有找到监听 %PORT% 端口的服务。
) else (
    echo.
    echo   服务已关闭。
)
echo.
if defined FROM_MENU pause
exit /b 0

rem ===========================================================================
rem  启动服务
rem ===========================================================================
:start
cls
echo.
echo   原神伤害计算器 —— 本地启动器
echo   项目目录：%ROOT%
echo.

rem ---- 已经在跑了？直接开浏览器 ------------------------------------
netstat -ano | findstr "LISTENING" | findstr /C:":%PORT% " >nul 2>nul
if not errorlevel 1 (
    echo   服务已在 %URL% 运行，直接打开浏览器。
    start "" "%URL%"
    ping -n 2 127.0.0.1 >nul
    if defined FROM_MENU pause
    exit /b 0
)

call :ensure_python
if errorlevel 1 goto :fail

rem ---- 前端构建产物 ------------------------------------------------
rem 这里刻意用 goto 而不是 if(...) 块：批处理会把整个括号块一次性解析，
rem 块内的 %PKG% 会在赋值前被展开成空串，导致 call 报错。用 goto 避开。
if exist "%ROOT%web\dist\index.html" goto :frontend_ready

echo   [1/2] 未找到前端构建产物 web\dist，正在构建...
call :pick_pkg
if not defined PKG goto :no_pkg
echo   使用包管理器：%PKG%
pushd "%ROOT%web"
call %PKG% install
if errorlevel 1 (popd & goto :fail)
call %PKG% build
if errorlevel 1 (popd & goto :fail)
popd
echo   前端构建完成。
echo.
goto :frontend_ready

:no_pkg
echo.
echo   [错误] 找不到可用的包管理器（pnpm / corepack pnpm / npm 都不可用）。
echo          请先安装 Node.js 20+，然后手动构建一次：
echo              cd web
echo              pnpm install
echo              pnpm build
echo.
pause
exit /b 1

:frontend_ready

rem ---- 启动 --------------------------------------------------------
pushd "%ROOT%"
echo   正在启动服务：%URL%
echo.
echo   浏览器会自动打开（想自己控制就用 --no-browser 参数）。
echo   关闭服务：按 Ctrl+C，或双击 launcher.bat 后选 [2]。
echo.
"%PY%" "%ROOT%main.py" --port %PORT% %FLAG%

echo.
echo   服务已停止。
if defined FROM_MENU pause
popd
exit /b 0

rem ===========================================================================
rem  开发模式：后端 + Vite（改前端代码即时生效）
rem ===========================================================================
:dev
cls
echo.
echo   原神伤害计算器 —— 开发模式
echo   后端：%URL%    前端：%DEV_URL%
echo.

call :ensure_python
if errorlevel 1 goto :fail
call :pick_pkg
if not defined PKG goto :no_pkg

if exist "%ROOT%web\node_modules" goto :dev_deps_ready
echo   未找到 web\node_modules，正在安装前端依赖...
pushd "%ROOT%web"
call %PKG% install
if errorlevel 1 (popd & goto :fail)
popd

:dev_deps_ready
netstat -ano | findstr "LISTENING" | findstr /C:":%PORT% " >nul 2>nul
if not errorlevel 1 goto :dev_frontend
echo   在后台窗口启动后端（%URL%）...
start "原神伤害计算器 · 后端" /min cmd /c ""%PY%" "%ROOT%main.py" --no-browser --port %PORT%"
ping -n 3 127.0.0.1 >nul

:dev_frontend
echo   启动前端开发服务器（%DEV_URL%），按 Ctrl+C 结束。
echo.
pushd "%ROOT%web"
call %PKG% dev
popd
echo.
echo   前端已停止。若后台还留着后端窗口，关掉它或执行：launcher.bat stop %PORT%
if defined FROM_MENU pause
exit /b 0

rem ===========================================================================
rem  子过程：准备 Python（优先现成的，缺依赖才建 .venv）
rem ===========================================================================
:ensure_python
if exist "%VENV_PY%" goto :use_venv
where python >nul 2>nul
if errorlevel 1 goto :no_python
rem 系统 python 已经装了后端依赖 → 直接用，省掉建虚拟环境的时间
python -c "import fastapi, uvicorn" >nul 2>nul
if not errorlevel 1 goto :ensure_python_check

echo   [1/2] 系统 Python 缺少后端依赖，正在创建 .venv 并安装...
python -m venv "%ROOT%.venv"
if errorlevel 1 goto :ensure_python_fail
set "PY=%VENV_PY%"
"%PY%" -m pip install --upgrade pip >nul 2>nul
"%PY%" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 goto :ensure_python_fail
echo   后端依赖安装完成。
echo.
goto :ensure_python_check

:use_venv
set "PY=%VENV_PY%"

:ensure_python_check
"%PY%" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 goto :ensure_python_fail
exit /b 0

:ensure_python_fail
echo.
echo   [错误] 后端依赖不可用（fastapi / uvicorn）。
echo          请手动执行：python -m pip install -r requirements.txt
echo.
exit /b 1

:no_python
echo.
echo   [错误] 找不到 python 命令。
echo          请先安装 Python 3.11+ 并勾选 "Add to PATH"。
echo.
exit /b 1

:fail
echo.
echo   [错误] 初始化失败，请查看上面的输出。
echo.
if defined FROM_MENU pause
exit /b 1

rem ===========================================================================
rem  子过程：探测可用的包管理器，结果写入 PKG
rem
rem  顺序刻意是 pnpm → corepack pnpm → npm：
rem    * 本项目的 pnpm-lock.yaml 由 pnpm 11 生成，直接用本机 pnpm 最稳妥；
rem    * corepack 会按 package.json 的 packageManager 决定版本，作为兜底
rem      （若本机 pnpm 是坏 shim 或没装，它才生效）；
rem    * npm 最后兜底（会忽略 pnpm-lock.yaml，另外生成 package-lock.json）。
rem  放文件末尾是为了不被主流程顺序执行到（用 call :pick_pkg 显式调用）。
rem ===========================================================================
:pick_pkg
set "PKG="
call pnpm --version >nul 2>nul
if not errorlevel 1 set "PKG=pnpm"
if defined PKG exit /b 0
call corepack pnpm --version >nul 2>nul
if not errorlevel 1 set "PKG=corepack pnpm"
if defined PKG exit /b 0
call npm --version >nul 2>nul
if not errorlevel 1 set "PKG=npm"
exit /b 0

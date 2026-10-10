@echo off
rem ===========================================================================
rem  Genshin Damage Calculator (Web) -- local launcher
rem
rem  Double-click            -> menu (start / stop / dev mode / quit)
rem  launcher.bat 9000       -> start on port 9000
rem  launcher.bat stop       -> stop the service on the default port (8777)
rem  launcher.bat stop 9000  -> stop the service on port 9000
rem  launcher.bat dev        -> dev mode: backend + Vite (frontend HMR, needs Node)
rem  launcher.bat 8777 --reload
rem                          -> extra args after the port are passed to main.py
rem                             (--reload backend hot reload / --no-browser)
rem
rem  First run fills in what a fresh clone is missing (both are gitignored):
rem     web\dist\    frontend build   -> rebuilt automatically when missing **or
rem                                      older than web\src** (see the note below)
rem     fastapi/uvicorn backend deps  -> reuse the installed python, else make .venv
rem
rem  NOTE: keep this file PURE ASCII and CRLF. cmd.exe parses batch files using
rem        the console code page at read time; non-ASCII text (Chinese) makes it
rem        lose byte alignment on a CP-936 console, so `echo ` gets eaten and a
rem        menu line is executed as a command ("'[4]' is not recognized").
rem        test_launcher.py enforces this.
rem ===========================================================================
setlocal EnableExtensions

set "ROOT=%~dp0"
set "PY=python"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"

rem ---- parse args: stop [port] / dev [port] / [port] [extra] / no arg = menu --
set "ACTION=%~1"
set "PORT=%~2"
set "FLAG=%~3"

if /i "%ACTION%"=="stop" goto :resolve_port
if /i "%ACTION%"=="dev" goto :resolve_port
if "%ACTION%"=="" goto :resolve_port
rem first arg is neither stop/dev nor empty -> treat it as a port and start now
rem (must set ACTION=start explicitly: clearing it would fall into the menu and
rem  block on input when called from a script)
set "PORT=%~1"
set "FLAG=%~2"
set "ACTION=start"

:resolve_port
if "%PORT%"=="" set "PORT=8777"
set "URL=http://127.0.0.1:%PORT%"
set "DEV_URL=http://127.0.0.1:5173"
title Genshin Damage Calculator (%PORT%)

if not defined ACTION call :menu

if /i "%ACTION%"=="stop" goto :stop
if /i "%ACTION%"=="quit" exit /b 0
if /i "%ACTION%"=="dev" goto :dev
goto :start

rem ===========================================================================
rem  Menu (used when double-clicked)
rem ===========================================================================
:menu
set "FROM_MENU=1"
cls
echo.
echo   Genshin Damage Calculator  (Web)
echo   ------------------------------------------------------------
echo     Project : %ROOT%
echo     Port    : %PORT%
echo.
echo     [1] Start server   (and open the browser)
echo     [2] Stop server
echo     [3] Dev mode       (Vite HMR, needs Node)
echo     [4] Quit
echo.
set "SEL="
set /p "SEL=    Choice [1]: "
if "%SEL%"=="" goto :menu_start
if "%SEL%"=="1" goto :menu_start
if "%SEL%"=="2" goto :menu_stop
if "%SEL%"=="3" goto :menu_dev
if "%SEL%"=="4" goto :menu_quit
echo.
echo     Invalid input.
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
rem  Stop
rem ===========================================================================
:stop
cls
echo.
echo   Stopping the service on %URL% ...
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr /C:":%PORT% "') do (
    set "FOUND=1"
    echo     killing PID %%p
    taskkill /PID %%p /T /F >nul 2>nul
)
if not defined FOUND (
    echo     no service is listening on port %PORT%.
) else (
    echo.
    echo   Service stopped.
)
echo.
if defined FROM_MENU pause
exit /b 0

rem ===========================================================================
rem  Start
rem ===========================================================================
:start
cls
echo.
echo   Genshin Damage Calculator -- local launcher
echo   Project : %ROOT%
echo.

rem ---- already running? just open the browser -------------------------------
netstat -ano | findstr "LISTENING" | findstr /C:":%PORT% " >nul 2>nul
if not errorlevel 1 (
    echo   Service is already running on %URL%, opening the browser.
    start "" "%URL%"
    ping -n 2 127.0.0.1 >nul
    if defined FROM_MENU pause
    exit /b 0
)

call :ensure_python
if errorlevel 1 goto :fail

rem ---- frontend build -------------------------------------------------------
rem Use goto instead of an if(...) block on purpose: cmd parses a whole block at
rem once, so %PKG% would expand to an empty string before it is set, and
rem `call %PKG% build` would fail with "'build' is not recognized".
rem
rem Checking only whether web\dist\index.html exists is not enough: after a
rem `git pull` the old dist is still there, so the backend keeps serving the
rem OLD ui (APIs fine, features missing - very hard to notice).
rem The staleness rule lives in Python so launcher / health / main.py agree.
pushd "%ROOT%"
"%PY%" -m server.build_check >nul 2>nul
set "STALE=%errorlevel%"
popd
if "%STALE%"=="0" goto :frontend_ready

echo   [1/2] web\dist is missing or older than web\src, building the frontend ...
call :pick_pkg
if not defined PKG goto :no_pkg
echo   package manager: %PKG%
pushd "%ROOT%web"
call %PKG% install
if errorlevel 1 (popd & goto :fail)
call %PKG% build
if errorlevel 1 (popd & goto :fail)
popd
echo   frontend build done.
echo.
goto :frontend_ready

:no_pkg
echo.
echo   [ERROR] No package manager found (pnpm / corepack pnpm / npm).
echo           Install Node.js 20+ and build once by hand:
echo              cd web
echo              pnpm install
echo              pnpm build
echo.
pause
exit /b 1

:frontend_ready

rem ---- launch ---------------------------------------------------------------
pushd "%ROOT%"
echo   Starting: %URL%
echo.
echo   The browser will open automatically (use --no-browser to control it).
echo   To stop: press Ctrl+C, or run launcher.bat and pick [2].
echo.
"%PY%" "%ROOT%main.py" --port %PORT% %FLAG%

echo.
echo   Service stopped.
if defined FROM_MENU pause
popd
exit /b 0

rem ===========================================================================
rem  Dev mode: backend + Vite (frontend hot reload)
rem ===========================================================================
:dev
cls
echo.
echo   Genshin Damage Calculator -- dev mode
echo   backend : %URL%      frontend : %DEV_URL%
echo.

call :ensure_python
if errorlevel 1 goto :fail
call :pick_pkg
if not defined PKG goto :no_pkg

if exist "%ROOT%web\node_modules" goto :dev_deps_ready
echo   web\node_modules not found, installing frontend deps ...
pushd "%ROOT%web"
call %PKG% install
if errorlevel 1 (popd & goto :fail)
popd

:dev_deps_ready
netstat -ano | findstr "LISTENING" | findstr /C:":%PORT% " >nul 2>nul
if not errorlevel 1 goto :dev_frontend
echo   Starting the backend in a background window (%URL%) ...
start "Genshin Damage Calculator - backend" /min cmd /c ""%PY%" "%ROOT%main.py" --no-browser --port %PORT%"
ping -n 3 127.0.0.1 >nul

:dev_frontend
echo   Starting the Vite dev server (%DEV_URL%), press Ctrl+C to stop.
echo.
pushd "%ROOT%web"
call %PKG% dev
popd
echo.
echo   Frontend stopped. If the backend window is still open, close it or run:
echo       launcher.bat stop %PORT%
if defined FROM_MENU pause
exit /b 0

rem ===========================================================================
rem  Sub: prepare python (reuse what is installed, only make .venv when needed)
rem ===========================================================================
:ensure_python
if exist "%VENV_PY%" goto :use_venv
where python >nul 2>nul
if errorlevel 1 goto :no_python
rem the system python already has the backend deps -> use it, skip the venv
python -c "import fastapi, uvicorn" >nul 2>nul
if not errorlevel 1 goto :ensure_python_check

echo   [1/2] System python lacks backend deps, creating .venv and installing ...
python -m venv "%ROOT%.venv"
if errorlevel 1 goto :ensure_python_fail
set "PY=%VENV_PY%"
"%PY%" -m pip install --upgrade pip >nul 2>nul
"%PY%" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 goto :ensure_python_fail
echo   backend deps installed.
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
echo   [ERROR] Backend deps are not usable (fastapi / uvicorn).
echo           Run: python -m pip install -r requirements.txt
echo.
exit /b 1

:no_python
echo.
echo   [ERROR] "python" was not found.
echo           Install Python 3.11+ and check "Add python.exe to PATH".
echo.
exit /b 1

:fail
echo.
echo   [ERROR] Setup failed, see the output above.
echo.
if defined FROM_MENU pause
exit /b 1

rem ===========================================================================
rem  Sub: detect a package manager, result goes into PKG
rem
rem  Order is pnpm -> corepack pnpm -> npm:
rem    * this repo's pnpm-lock.yaml was written by pnpm 11, so the local pnpm
rem      matches it best;
rem    * corepack uses package.json's packageManager field as a fallback;
rem    * npm is the last resort (ignores pnpm-lock.yaml, writes package-lock).
rem  Kept at the end of the file so the main flow never falls into it.
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

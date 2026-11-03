@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "EDITION=%~1"
if "%EDITION%"=="" set "EDITION=self"
set "UV=%CD%\.tools\uv.exe"
if exist "%UV%" goto have_uv
for /f "delims=" %%U in ('where uv.exe 2^>nul') do if not defined UV_FOUND set "UV_FOUND=%%U"
if defined UV_FOUND set "UV=%UV_FOUND%"
if defined UV_FOUND goto have_uv
echo [1/3] 正在准备安装工具，首次启动需要联网……
if not exist ".tools" mkdir ".tools"
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $p=Join-Path (Get-Location) '.tools\uv.zip'; Invoke-WebRequest -UseBasicParsing 'https://github.com/astral-sh/uv/releases/download/0.13.7/uv-x86_64-pc-windows-msvc.zip' -OutFile $p; if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() -ne '0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021'){throw '安装工具校验未通过，请重新下载'}; Expand-Archive -LiteralPath $p -DestinationPath '.tools\uv-download' -Force; $exe=Get-ChildItem '.tools\uv-download' -Filter 'uv.exe' -Recurse | Select-Object -First 1; if(-not $exe){throw '安装工具缺少入口'}; Copy-Item -LiteralPath $exe.FullName -Destination '.tools\uv.exe'"
if errorlevel 1 goto failed
:have_uv
if exist ".runtime\Scripts\python.exe" goto have_python
echo [2/3] 正在准备 Python 3.11，安装在当前用户目录……
"%UV%" venv --python 3.11 --managed-python .runtime
if errorlevel 1 goto failed
:have_python
set "PY=%CD%\.runtime\Scripts\python.exe"
powershell.exe -NoProfile -Command "$h=(Get-FileHash -LiteralPath 'requirements-runtime.lock' -Algorithm SHA256).Hash; if((Test-Path '.runtime\hyper-evolution-lock.txt') -and (Get-Content '.runtime\hyper-evolution-lock.txt' -Raw).Trim() -eq $h){exit 0}else{exit 1}"
if not errorlevel 1 goto ready
echo [3/3] 正在安装学习工作台依赖，完成后自动打开……
"%UV%" pip sync --python "%PY%" requirements-runtime.lock
if errorlevel 1 goto failed
powershell.exe -NoProfile -Command "(Get-FileHash -LiteralPath 'requirements-runtime.lock' -Algorithm SHA256).Hash | Set-Content -LiteralPath '.runtime\hyper-evolution-lock.txt' -Encoding ascii"
:ready
set "PYTHONPATH=%CD%\src"
set "PYTHONUTF8=1"
"%PY%" -m growth_local --edition "%EDITION%" %2 %3 %4 %5 %6 %7 %8 %9
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo 启动尚未完成。请检查网络后再次运行；已有学习记录保存在用户数据目录。
echo 使用说明：docs\getting-started.md
pause
exit /b 1

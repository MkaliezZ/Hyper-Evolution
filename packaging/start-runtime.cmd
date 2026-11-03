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
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $p=[IO.Path]::GetFullPath('.tools\uv.zip'); (New-Object Net.WebClient).DownloadFile('https://github.com/astral-sh/uv/releases/download/0.13.7/uv-x86_64-pc-windows-msvc.zip',$p); $sha=[Security.Cryptography.SHA256]::Create(); $hash=[BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($p))).Replace('-','').ToLower(); if($hash -ne '0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021'){throw '安装工具校验未通过，请重新下载'}; [void][Reflection.Assembly]::LoadWithPartialName('System.IO.Compression.FileSystem'); $d=[IO.Path]::GetFullPath('.tools\uv-'+[Guid]::NewGuid().ToString('N')); [IO.Compression.ZipFile]::ExtractToDirectory($p,$d); $exe=[IO.Directory]::GetFiles($d,'uv.exe',[IO.SearchOption]::AllDirectories); if($exe.Length -ne 1){throw '安装工具缺少入口'}; [IO.File]::Copy($exe[0],[IO.Path]::GetFullPath('.tools\uv.exe'),$true)"
if errorlevel 1 goto failed
:have_uv
if exist ".runtime\Scripts\python.exe" goto have_python
echo [2/3] 正在准备 Python 3.11，安装在当前用户目录……
"%UV%" venv --python 3.11 --managed-python .runtime
if errorlevel 1 goto failed
:have_python
set "PY=%CD%\.runtime\Scripts\python.exe"
"%PY%" -c "import hashlib,pathlib,sys; p=pathlib.Path('.runtime/hyper-evolution-lock.txt'); h=hashlib.sha256(pathlib.Path('requirements-runtime.lock').read_bytes()).hexdigest(); sys.exit(0 if p.exists() and p.read_text().strip()==h else 1)"
if not errorlevel 1 goto ready
echo [3/3] 正在安装学习工作台依赖，完成后自动打开……
"%UV%" pip sync --python "%PY%" requirements-runtime.lock
if errorlevel 1 goto failed
"%PY%" -c "import hashlib,pathlib; pathlib.Path('.runtime/hyper-evolution-lock.txt').write_text(hashlib.sha256(pathlib.Path('requirements-runtime.lock').read_bytes()).hexdigest(),encoding='ascii')"
if errorlevel 1 goto failed
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

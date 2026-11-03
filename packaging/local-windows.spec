from pathlib import Path
import tomllib
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
root=Path(SPECPATH).parent
version=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf8'))['project']['version']
datas=[]
for package in ['base','growth_local','growth','genai_prices']:
    datas += collect_data_files(package)
for package in ['genai-prices','pydantic-ai-slim','keyring','mcp','aiortc']:
    datas += copy_metadata(package)
hidden=['keyring.backends.Windows','win32cred','pydantic_ai.providers.deepseek','pydantic_ai.models.openai']
hidden += collect_submodules('mcp.server.fastmcp')
hidden += ['PIL.PngImagePlugin','PIL.JpegImagePlugin']
a=Analysis([str(root/'packaging/local_entry.py')],pathex=[str(root/'src')],binaries=[],datas=datas,hiddenimports=hidden,hookspath=[],runtime_hooks=[],excludes=['pytest','tkinter','IPython','numpy','matplotlib'],noarchive=False)
pyz=PYZ(a.pure)
gui=EXE(pyz,a.scripts,[],exclude_binaries=True,name='HyperGrowth',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False)
mcp=EXE(pyz,a.scripts,[],exclude_binaries=True,name='HyperGrowthMCP',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(gui,mcp,a.binaries,a.datas,strip=False,upx=False,name='HyperGrowth-Windows-'+version)

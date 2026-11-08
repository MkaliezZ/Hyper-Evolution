# 开发与扩展

## 运行环境

Windows 工程包以 Python 3.11 x64 构建。源码环境建议也使用 Python 3.11，安装 `requirements-local.lock`。运行 `python -m growth_local --edition teacher|student|self`；三个 edition 分别有独立默认目录，`--data` 可指定测试目录。

Linux/macOS 源码运行需要可用的系统密钥库，Linux 桌面通常使用 Secret Service。连接服务可以独立运行于 Linux。当前发布提供 Windows 源码与一键在线启动包。

## 三层与六对象

保留 `src/base/app/companion/aesthetic`、`functional`、`assets` 三个目录及其职责。

| 对象 | 在开发时写清 |
| --- | --- |
| Scenario | 谁遇到什么问题、约束与预期结果 |
| Module | 职责边界、输入输出、依赖与版本 |
| Capability | 接受什么任务、返回什么、怎样判断失败 |
| Agent / Skill / Workflow | 内部如何协调和执行 |
| Policy Pack | 专业判断、适用条件、正反例与验收 |
| Asset | 来源、权限、用途、版本与质量状态 |

能力通过 `LocalRuntime.invoke_capability` 对外提供，网页、MCP 和内置助手共享同一门面。模块内部可替换模型、算法或工作流，保持公开契约和权限语义。详细约定见[架构文档](architecture.md)和[契约目录](contracts/)。

## 本地验证

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m pytest tests -q
node --test tests/*.test.cjs
python scripts/check.py --business
python scripts/verify_experience.py
python scripts/verify_local_peer.py
```

PowerShell 如未展开 Node 通配符，可运行 `Get-ChildItem tests/*.test.cjs | ForEach-Object { node --test $_.FullName }`。

验证脚本使用合成资料与独立目录，回执写入被 Git 忽略的 `artifacts/` 或 `data/verify/`。`scripts/verify_release.py` 从三个 ZIP 的解压源码验证入口、网页/MCP共享、配对、提交、反馈和自学多条引用的保存。

## 三版本工程包

工程包提供完整应用源码和一键在线启动脚本。首次运行通过 uv 准备 Python 与锁定依赖，之后使用本机环境。

运行 python scripts/package_public.py --output releases，从已提交的公开源码创建三个 ZIP 和 SHA256 清单。打包后解压验证三入口、网页与 MCP、配对、提交和反馈。

离线二进制可在开发机用 PyInstaller 本地构建。公开分发前需完成媒体组件对应源码与许可材料，详见[第三方说明](../THIRD_PARTY_NOTICES.md)。

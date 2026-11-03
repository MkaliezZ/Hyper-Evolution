# 第三方与内容授权

## 项目源码

Hyper Evolution / 超维成长的应用源码采用 MIT 许可，保留根目录 `LICENSE`。原伴学 BASE v0.3.2-r2 的源码也采用 MIT，保留原版权声明。公开版本延续其本机活动、提交与反馈闭环。

部分评估模式与自学流程借鉴 HKUDS/DeepTutor。相关出处、适配说明和 Apache-2.0 许可位于 `third_party/deeptutor/`，沿用独立许可与署名。此次公开保留原三层结构和能力契约。

## 首批工程包采用的分发方式

v0.6.0-rc.1 的三个 ZIP 提供本项目源码、教程和在线启动脚本。首次运行使用 uv 从各上游下载 Python 与锁定依赖，安装在用户电脑上。ZIP 本身不附带 Python、PyAV/FFmpeg、编解码 DLL、第三方教材或音频。

安装脚本固定 uv 版本 0.13.7，并校验官方 Release 的 SHA256。uv 采用 MIT / Apache-2.0 双许可；来源为 https://github.com/astral-sh/uv 。运行环境的版本见 `requirements-runtime.lock`，构建和开发依赖见 `requirements-local.lock`。

## 主要依赖

| 项目 | 用途 | 许可 |
| --- | --- | --- |
| Python | 本地运行环境 | PSF |
| FastAPI / Starlette / Uvicorn | 本机网页与 API | MIT / BSD-3-Clause |
| MCP Python SDK | 本机 stdio / HTTP MCP | MIT |
| Pydantic / Pydantic AI | 数据约束与助手编排 | MIT |
| aiortc / aioice | WebRTC 连接 | BSD-3-Clause |
| PyAV | 媒体库接口 | BSD-3-Clause，所链接媒体库另有许可 |
| cryptography | 加密、签名与恢复包 | Apache-2.0 OR BSD-3-Clause |
| keyring | 系统凭据管理 | MIT |
| Pillow | 原图处理 | MIT-CMU，内含组件见上游许可 |
| certifi | TLS 证书库 | MPL-2.0 |

逐项构建环境清单见 [`docs/dependency-inventory.json`](docs/dependency-inventory.json)。安装者可从依赖包的 `.dist-info/licenses` 或上游项目查阅完整许可。MPL/LGPL/GPL 等组件继续适用各自条款。

## 离线冻结包的后续分发

现有开发环境的 PyAV 媒体 DLL 还依赖 x264/x265、LAME、libiconv 等组件。发布带这些二进制的离线包，需要逐库整理准确版本、许可、对应源码和构建配方。首个公开 Release 使用上述在线源码安装方式；本机试构建的冻结二进制保留在私有工作目录。

开发者本地可使用 PyInstaller 构建。其启动器例外允许分发应用程序；最终包内各依赖的分发条件仍需分别落实。参考：https://pyinstaller.org/en/stable/license.html 、https://ffmpeg.org/legal.html 。

## 教材、题库、音频与作品

公开示例为本项目原创的工程演示内容。剑桥系列、TPO、第三方真题、真人音频、私人词库和学习者作品分别遵循权利人的授权。可以免费获取的材料，是否允许再次公开分发需要另行核对。

该 Release 提供导入和来源管理能力，使用者在自己的工作区导入有权使用的材料。私有资料目录和历史测试资源未纳入公开仓库或安装包。

# 师生配对与连接服务

## 使用配对码

老师生成十二位配对码，学生在“我的老师”中输入。配对码十分钟有效，双方保持程序在线。连接成功后，任务、提交和反馈通过签名消息交换，并分别保存在本机。

当前默认使用社区测试连接服务。它负责加密连接协商，并在需要时提供 TURN 中转。自学阅读、资料管理和本机 MCP 可独立使用；师生实时交换需要可用的连接服务与双方在线。

## 使用自己的连接服务

老师和学生使用同一个连接服务。退出本机服务后，在程序目录打开终端，用启动参数保存自己的 `wss://.../ws` 地址：

```powershell
$env:PYTHONPATH = "$PWD/src"
.\.runtime\Scripts\python.exe -m growth_local --edition teacher --coordinator wss://YOUR_HOST/ws
```

学生将 `teacher` 换成 `student`。也可设置进程环境变量 `HYPER_EVOLUTION_COORDINATOR`。连接服务启动命令：

```bash
PYTHONPATH=src python -m uvicorn growth_local.signal:create_app --factory --host 127.0.0.1 --port 8878
```

使用 Nginx/Caddy 提供 HTTPS 和 WebSocket 反向代理，将 `/ws` 转发到连接进程。公开网络使用可信 TLS 证书。

## 配置 TURN

可部署 coturn，并在连接服务的进程环境中设置 `GROWTH_TURN_SECRET` 和 `GROWTH_TURN_URLS`。前者与 coturn 的 `static-auth-secret` 一致；后者使用逗号分隔 TURN URL，例如 `turn:YOUR_HOST:3478?transport=udp,turn:YOUR_HOST:3478?transport=tcp`。密钥由部署者生成并保存在服务端私有配置中。

连接服务动态签发临时 TURN 凭据，房间状态保存在内存。按自己的 coturn 配置放行监听端口和中继端口范围。

学习文件、模型 Key 和设备私钥保存在用户设备；连接服务转发加密协商，TURN 转发加密网络流量。服务端可见连接 IP、时间与流量等元数据，部署时按需配置日志保留。

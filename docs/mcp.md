# 连接自己的 Agent

## 推荐：复制本机生成的配置

1. 先启动所需版本，完成身份设置。
2. 打开“连接与设置 → 模型与本机设置”，找到 MCP 配置。
3. 复制页面生成的配置，粘贴到你使用的 Agent 的 MCP 设置。
4. 重新连接，在 Agent 中说：“先读取本机状态，告诉我当前身份和学科。”

首次运行准备好的 `.runtime/Scripts/python.exe` 提供 stdio 接口，配置会携带当前数据目录。Windows 路径放入 JSON 时使用双反斜杠。实际配置以本机页面生成为准。

```json
{
  "mcpServers": {
    "hyper-evolution": {
      "command": "C:\\Apps\\Hyper-Evolution\\.runtime\\Scripts\\python.exe",
      "args": ["-m", "growth_local.mcp"],
      "env": {
        "PYTHONPATH": "C:\\Apps\\Hyper-Evolution\\src",
        "HYPER_GROWTH_DATA": "C:\\Users\\YOUR_NAME\\AppData\\Local\\HyperEvolution\\Enlighter\\data"
      }
    }
  }
}
```

示例路径需要换成你的程序与数据位置。外部 Agent 使用它自己的模型配置；网页的 API 设置服务于网页内置助手。

## 先让 Agent 做一个小任务

- 教师：“读取当前学生列表，帮我整理最近提交的作品；先展示评阅草稿。”
- 学生：“读取老师布置给我的任务，按要求帮我理解这段资料。”
- 自学：“读取当前资料和目标，建议一次短练习，先让我看设计。”

工具列表按本机身份和学科提供。Agent 可以先调用 `get_local_status`、`get_companion_architecture`，再通过 `invoke_companion_capability` 调用适用能力。教师 Agent 详见[操作规范](usage/teacher-agent.md)。

## HTTP MCP

运行中的本机服务也提供 Streamable HTTP MCP。地址和认证信息从本机设置复制，只交给你信任的客户端。它与网页共用当前工作区。关闭本机服务后，HTTP 连接随之结束；stdio 客户端可以自行启动 MCP 进程。

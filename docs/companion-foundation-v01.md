# 第一阶段：授权证据、能力契约与资产引用

本地源码新增三项只读能力，契约 `companion.capability.v1`。运行于现有本地网页 / MCP / BASE，没有数据库迁移，没有删除旧记录，没有改师生配对协议。架构约定见 [architecture.md](architecture.md)。

## 入口

本地 HTTP 仍需原有 cookie 或 bearer 凭据：

- `GET /api/local/evidence`：学生本人；教师带 `peer_id`；可加 `task_id`。
- `GET /api/local/capabilities`：读取三层约定、已实现能力与待补边界。
- `POST /api/local/capabilities/invoke`：按同一契约调用。

MCP 保留所有原工具，增加 `get_authorized_evidence`、`get_companion_architecture`、`invoke_companion_capability`。初始化之前仍仅可查询本机状态。两种入口返回同一服务的结果，仅各自默认 request_id 不同；显式传同一请求可逐字段比较。

```json
{
  "contract_version": "companion.capability.v1",
  "request_id": "example-read-1",
  "operation": "evidence.read",
  "limits": {"tasks": 20, "attempts": 5}
}
```

教师加 `peer_id`。身份和授权范围来自本机，不接受 caller 提供 `actor_scope`、评分者或放行标记。未知版本、未知操作、非法定位和多余字段拒绝，错误不反射原始请求或密钥。

只读结果有 `request_id / operation / status / data / evidence_refs / missing / decision_trace`；不返回伪造的保存回执。截断返回 partial 和 coverage；缺少历史帮助条件不妨碍读取，但必须明确缺项。状态与持久化、评分或达标无关。

## 证据范围

学生读取自主任务和仍有效配对教师任务，包括题目安全投影、实际已提交回答、可见反馈、评阅历史和待送达队列。队列与教师确认的尝试分开，不能因 ACK 就认定已经评阅。教师必须选择当前配对学生，且只读取本机布置并收到的相关作品。

不返回称呼、教师私注、未提交草稿、密钥、文件路径、原始附件字节、题目参考答案、完整听力转写或参考解答。公开评价按白名单投影，保留客观核对和正式评阅来源；不新增主观自动评分。长期掌握、本人帮助条件和旧场景规则缺少证据时保持未知。

内置 Agent 从相同证据视图获取最近记录，包含可见教师反馈与逐题作答；上下文有单独预算，预算不足有标记。Agent 工具读取和模型返回后再次检查当前授权。外部 Agent 仍使用其自己的模型配置。

## 资产引用

`snapshot_ref / source_ref / answer_ref / evaluation_ref / review.asset_ref` 可作为 `input_refs` 传给 `asset.resolve`。先使用服务实际返回的引用，不要手造 ID。

```json
{
  "request_id": "example-resolve-1",
  "operation": "asset.resolve",
  "input_refs": ["这里替换为服务返回的完整引用对象"]
}
```

引用绑定 ID、版本、来源哈希、主体与任务；没有有效任务权限，即使持有旧引用也不能读。当前内容变化返回 needs_input，不静默使用其他版本。文字定位支持 `{ "kind":"text", "start":0, "end":12 }`，超出边界明确失败。页、区域、时间仅验证结构，解析返回 unavailable，等待后续能力接入。

所有历史读都保留原始数据库。本阶段是投影而非新评价账本；当前评价变化后可用旧 review 引用回查历史评阅，但并不冻结完整业务算法。技术验证、领域审阅与真实学习效果分别记录。

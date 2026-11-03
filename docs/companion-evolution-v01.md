# 可选安排、写作与方法资产 v5

0.4.0 工程测试包扩展。固定三层和六对象，保留本机网页、MCP、密钥库、角色权限与师生配对。新入口使用 `companion.capability.v5`，v1—v4 契约不变。

## 可选安排

`path.create/list/read/preview/confirm/publish`。建立自己的安排不要求完整诊断或前置图谱。每次调整记录目标、理由、步骤顺序、负担、日期、关联任务、准确差异与父版本哈希；先预览再以 expected_revision 确认。重复请求回放同一回执，旧预览不能覆盖新版本。

教师安排须选有效配对学生。保存本机草案与发布分别操作；发布关联至少一份已布置任务，通过已有签名 task.updated 的外层 companion_paths 扩展传送已发布的精确版本。未发布的后续修改不随一般反馈泄露。学生侧教师安排只读；可另建自己的安排。调整不会修改任务标准、原作、分数或正式评价。旧客户端忽略未知外层字段，不增加网络事件类型或重新配对。

## 写作与贡献

`writing.create/list/read/suggestions/suggest/share_suggestion/preview/confirm/submit/history`。首稿保存不可覆盖，后续版本追加。学习者输入及自行修订仅代表本人声明；不证明独立完成。教师从实际收到的文字作品取得首稿快照，不得把改写冒充原始提交。

外部建议和教师建议为候选，每组最多六处 Unicode 字符位置、准确原句、替换和理由。局部重叠、原文不同、版本过期均拒绝。模型仅有只读当前稿工具，返回后重新授权、核对版本，再通过同一 v5 门面存候选；不直接改稿、提交或评价。选择建议或自己写新稿两种方式分别预览，确认后保留差异、帮助声明与候选来源。手动参考建议仍须如实声明帮助，系统不能识别实际作者。

学生另行明确提交进行中的文字任务，发送当前稿、首稿和最多最近24版历史（超过25版明确截断）。完整历史保存在新增侧表，通过已有签名 submission 扩展交换；BASE 的答案仅存紧凑历史引用，20k限制保留。教师只能通过当前授权任务实际回答中的引用读取侧表，不因知道历史ID而读取其他作品。历史完整性不能证明人类身份、独立完成或能力增长。教师建议另行分享，不代替正式评阅。

## 方法回流

`method.candidate/list/read/review/publish/export` 为本机教师方法库。与个人档案独立，不自动抓取札记、私注、原答或未经授权作品。候选由使用者填写问题、范围、用途依据、来源、脱敏、操作、验收、好例、反例和证据局限；明显邮箱、手机号、密钥、路径会拒绝，但程序不能保证彻底脱敏。

审阅绑定候选哈希，记录审阅者、经验声明、逐项核对、范围与理由。未全部核对用途、脱敏、案例和范围，不能声明通过。负责人须另行发布，才可显式导出 `companion.method.asset.v1` 声明式JSON。最新否决或待修订阻止旧通过继续发布/导出。发布只产生本机方法资产，不上传公共库、不执行脚本、不自动替换 P01—P10。身份、资质、授权依据及专业结论均为调用者声明，平台未认证；AI不得冒人代勾真实审阅。

## 存储与复验

增加九张不可变版本/记录表：companion_path_versions、companion_path_previews、companion_writing_versions、companion_writing_suggestions、companion_writing_previews、companion_writing_receipts、companion_method_candidates、companion_method_reviews、companion_method_releases。不改旧BASE schema，不反填历史未知条件。加密备份包含新表；真实模型和教师私注不进公共包。

运行 test_companion_evolution.py、test_companion_method_assets.py、架构测试与原有回归；verify_companion_evolution.py 验证真实HTTP、独立stdio、HTTP MCP及签名传递，可用 --executable 指定冻结程序。工程结果与真实教学专业审定、体验和学习效果分开。

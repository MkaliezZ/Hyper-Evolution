# Enlighter / Evolver / Self-Evolver：导航整合与自主学习

2026-11-02，源码工程版。官网安装包另行构建、验收和发布。

沿用超维伴学与伴学 BASE，复用此前借鉴 DeepTutor 的“阅读—提问—练习—反馈—复习”流程，不引入第二套数据库或完整 DeepTutor 服务。上游本轮核对 HEAD `f7aed0744c36c5afef16a4261c31ebee1208cac2`；已有借鉴与许可见 `third_party/deeptutor/`。本轮模式组合与自主作品反馈由本项目实现。

## 页面归属

| Enlighter 教师一级入口 | 二级页面 |
|---|---|
| 教学首页 | 今日待办与现有快捷操作 |
| 学生与目标 | 学生档案、成长与目标、学习安排、学习札记 |
| 备课与任务 | 设计与布置、资料阅读、练习与题库、教学助手、检索对照 |
| 作业与反馈 | 作业评阅、写作与修订 |
| 教学方法 | 学习设计与规则、案例与验收、方法资产 |

“学科与路线”切换工作区，K12是其二级路线。“连接与设置”收纳配对、模型、备份、MCP和说明。旧路由和数据继续有效，一级组与二级页面各自显示选中状态。

2026-11-03更新：Evolver学生端也使用统一侧栏，主入口为学习首页、我的任务、反馈与修订、目标与安排。老师的规划、学习安排放在“目标与安排”的二级导航；我的老师、模型与本机设置、指南收进“连接与设置”。任务中的阅读与写作继续跟随原任务入口。

自学版统一命名为Self-Evolver，明确切换后使用。入口为自学首页、读资料与提问、练习与作品、反馈与复习、目标与安排。自主列表只显示本机任务；老师任务仍从Evolver学生版完成。

## 三层实现

审美层沿用P01—P10、场景与六类方法装配：先明确目标、材料、操作、帮助、标准，再预览活动。新增 `aesthetic/self_feedback.py` 定义自主反馈的判断原则与证据检查，无数据库、模型和网络访问。

功能层 `functional/experience.py` 新增v11组合能力，调用原v3活动、原v2评价账本和原v3复习。自主反馈Agent必须读取实际提交、来源快照与规则条件，核对原文引用，保存model_suggestion。本人反思保存self_report。教师评阅沿用人工确认与签名发布流程。

资产层沿用材料原件、来源版本、活动快照、每次提交、评价、札记和复习卡，继续分学科存放。不新增资产数据库，不搬移历史任务。评价保留原答哈希、来源和规则版本，模型任务记录保留完整输出与观察范围。

## 身份与契约

底层身份仍为teacher/student。Enlighter是teacher的界面名称；Evolver学生版与Self-Evolver自学版都为student身份，experience继续使用student/self。切换保留原权限与配对。

`local_config.learning-experience-v1` 在各学科共用。首次网页setup接受role=self，验证后保存role=student与experience=self；旧setup不变。角色、模式组合先验证再创建身份。

v1—v10快照冻结，新增companion.capability.v11：

- experience.read/select：读取或明确切换模式，历史只读区也可切换这项全机设置。
- self.context：本学科自主任务。
- self.start：调用原v3 Policy Pack装配，冻结资料来源。
- self.feedback_context：本人自主作品的实际提交，不接受teacher-origin任务。
- self.reflect：反思与可选复习；已有安排沿用，写操作具备指纹与重放处理。

精确payload见architecture.describe().experience_extension和docs/contracts/companion.capability.v11.*.schema.json。网页、Agent和MCP统一通过LocalRuntime.invoke_capability。

网页AI任务mode=self_review使用用户自己配置的模型，先检查模式与任务归属。外部Agent可读上下文，用自身模型推理后通过v2保存model_suggestion，不需配置工作台API。AI和自评不写教师达标结论。文字反馈Agent不读取录音或附件，保留相应观察范围。

## 验证与交付范围

tests/test_experience.py覆盖身份、归属、来源和规则、重放、备份恢复、FunctionModel调用与归因、中途切换模式、HTTP/MCP和v11快照。tests/experience.test.cjs检查最终导航投影。旧学生与导航回归继续运行。

scripts/verify_experience.py真实启动HTTP，用独立stdio MCP与HTTP MCP创建活动、读取作品与保存反思，验证学科隔离及重启。所有记录位于独立合成目录。真实服务商的教学质量、真人试用、新安装包验收另行完成。本轮不引入完整DeepTutor运行时。

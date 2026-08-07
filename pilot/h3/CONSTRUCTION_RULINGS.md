# H3 构造裁决书（parent，2026-08-08）

> 由 agent-8 canonical 交付后提交的五项歧义，parent 逐项裁决。裁决前的实际构造见 `pilot/h3/canonical.py`、`canonical_sa_report.json`、`canonical_tokenstats.json`、`canonical_samples.md`（agent-8 已按"先问后做"停在 canonical 阶段，未擅启后续）。

## R1 provenance：canonical-deterministic transcripts（接受偏离 §14.5）

冻结协议 §14.5 要求 transcript 素材用 qwen7b 真实成功 rollout（无 oracle fallback）；agent-8 按上位指令（parent 派活时明确写从 sealed oracle_plan/任务记录派生 canonical set）用了**确定性渲染**：canonical set 由 oracle_plan 执行轨迹派生（64/64 源任务 run_oracle_plan 全过；CHECK 观测值取自真实执行轨迹，非编造）。

**冲突**：§14.2（transcript 与 script 由同一 canonical set 渲染、程序化 diff 验证覆盖率 100%）与 §14.5（rollout 素材）在此互斥——真实 rollout 的步骤顺序/措辞与 canonical 序列不可能逐字命题对齐，SA=100% 无法同时成立。

**裁决**：canonical-deterministic 构造**接受**。理由：
1. 内容匹配是 H3 存在的科学理由（分离 form/coverage 与内容），这条优先级高于"transcript 生态真实感"；
2. "真实 rollout 素材"的生态维已由 eco 臂（H-C 原样 300-token 硬截 transcript， 全部来自真实 qwen7b rollout）覆盖——即生态问题在 H3 内已被 eco 臂回答；
3. §14.5 的"provenance 登记"要求以 cards_map.jsonl 的 construction 字段如实满足（每张卡记录 derivation= oracle_plan 轨迹渲染）。

**对论文叙事的影响**：主结果必须表述为"deterministic canonical renderings of verified episodes"，不得写"real agent transcripts"；该措辞限制随本裁决绑定 H3 全部产出。

## R2 prefix 切分语义：decision-start 命题边界切（接受，token 失衡登记）

prefix 切分=命题边界（在 write-decision 命题开始处截断），非固定 300-token 硬切。结果：prefix 臂恰好且只恰缺 write-decision+finish（断言 512/512 通过），但 token 分布明显短于窗口（script_prefix 均值 144，504/512 <200）。

**裁决**：接受。token 失衡是 coverage 操纵的**内禀重复量**（coverage 改变了保留内容量，长度随之变），按 GPT-5.6 明确预判的"exact verbatimness、等长、完整语义覆盖三者不可兼得"处理：
- 不强行补长 prefix、不强行截短 complete；
- 分析时按 §16 加 token 数协变量稳健性检验（在主 estimand 同号报告中附 covariate-adjusted 版本）；
- arms 间 token 分布如实报 SMD（§14.4 的 <0.2 目标不落实在本设计，改为登记+协变量，记录为本文件 R2）。

## R3 transcript/script token 密度差（登记为 form 的内禀属性）

transcript_complete 均值 713 vs script_complete 均值 465：形式本身携带信息密度差。form 对比将部分吸收"同等内容下对话式记录更啰嗦"——这正是部署中真实存在的形式差异。

**裁决**：接受为 form 操纵的一部分；分析时同样附 token 协变量稳健性；eco 臂恰是测量该密度差在 300-token 部署帽下的真实后果的臂。

## R4 header（task instruction 放卡首行）（接受）

H-C 卡无 header，H3 有（transcript 以 `user:` 开头、script 以 `Task:` 开头）。理由：真实检索到的对话天然携带请求行，且 prefix 臂需要接近 200–300 窗口。H-C↔H3 跨实验比较请仅以 cell 级主效应对比（N/Q 共参考），不跨格式直接比 Δ。

## R5 SA=marker-presence diff + 512 vs 640（接受）

marker-based 程序化命题对齐会漏检相同值重复出现的极端情形；samples.md 5 对已人工抽查（parent 亲自读）：内容逐句对齐、数字一致、无命题丢失，合格。640 vs 512：640 含 Q 卡，Q 按协议跳过，正确计数为 512 = 32×4×4 A-cells。

## 登记的剩余已知局限（不处理）

- eco 臂与 (transcript,prefix) 在 H-C 边界上 0/512 重合（截断语义不同属实测事实）；
- 114/512 (?) eco 卡保留 write-decision（硬切落在决策中），这正是 H-C raw 的部署噪声，不作为缺陷。
- 所有构造决策同时记录在 cards_map.jsonl 的每行元数据中，供审稿人追溯。

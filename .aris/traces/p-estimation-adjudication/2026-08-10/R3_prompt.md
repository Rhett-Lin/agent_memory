# Round 3：三个收口问题（最后一轮，之后我按你的裁决写方案）

R2 的 P0–P9 我基本照单接受。三个问题不解决，方案落地就是自欺。

## 问题 1（最重要）：接口曲线的 X 点有循环论证风险，请裁决 X 的合法来源

你把 certified P 的闭合路径定为：`F 保留 canonical executable IR → Canon(IR_x)=Canon(IR_m)`。
接口梯度第 4 点 X = "canonical executable artifact"。

**但在本 benchmark 里，唯一现成的 canonical executable IR 就是 generator 的 z 本身。**
如果 P5 的 confirm set 里 X 由 generator 直接吐出，那么：

- `Cert(T+S+V+X)` 恒等于 1.0、`Prec` 恒等于 1.0——因为那就是把 sealed oracle 换个名字读回来；
- 接口曲线上最重要的那一跳（X 点）**没有任何科学内容**，审稿人一眼看穿；
- 而且它违反你自己的证明义务 11（"必须证明存下来的 executable IR 确实是当时执行的程序，而非事后声明"）。

我认为唯一诚实的 X 定义是：**X 必须从 agent 在写入时的真实执行轨迹机械地导出**，而不是从 z 导出。
真实系统在写入时拥有的正是这个：实际调用的工具序列 + 环境记录的状态增量。于是真正的研究问题从
"从散文里恢复程序"缩小为"**把一条具体轨迹泛化成参数化过程**"（哪些常量是参数、哪些顺序是必需依赖）——
这是 programming-by-demonstration / trace generalization 的经典难题，但比从 prose 抽取容易得多，
且**不需要 LLM 自省**（我们已实测这个 7B 判不了程序等价：分解式 judge A10 误杀 85%）。

**请裁决**：

1. X 是否必须定义为 `trace → 参数化 IR` 的机械泛化产物？若是，请给出它的**合法性判据**
   （怎样算"机械"？允许用 LLM 吗？我倾向：泛化算法本身冻结且不看 sealed 标签，允许 LLM 只做
   命名/角色标注这类不影响签名的部分——请裁定边界）。
2. 单条轨迹**天然不足以识别参数与依赖**（一条轨迹里常量与参数不可分、独立操作的顺序无法与必需依赖区分）。
   这是否意味着 X 点必须再拆成 X1（单轨迹泛化）与 X2（多轨迹/多实例泛化）？后者在真实系统里对应
   "同一 skill 被执行过 k 次"。若是，请给 k 的量级判据。
3. 若 (1)(2) 都做不到，X 点是否应当**直接从接口梯度删除**，只保留 T / T+S / T+S+V / +W？
   （即：诚实地说"我们能测的是文本+schema+provenance+witness，可执行件我们没有合法来源"。）

## 问题 2：这条线与已完成论文的关系，请给资源裁决

现状：17pp 论文本体已完成、外部评审 6/10 "Almost" 终止、贡献计 2/3、Part V 外部验证线已
NOT_ESTIMATED 关闭。P0–P7 按你的估算是 CPU 数周量级（P5 confirm set 400 families/800 pairs +
独立 renderer + 独立 challenger）。

**请在三个选项里裁决，并说明触发条件：**

- (a) **先投**：把 interface curve 作为现有论文的新 main section，推迟投稿，赌它把档位从 6/10 抬上去；
- (b) **并行**：现有论文按当前形态投出（诚实标注 P 的部署缺口为 open problem），interface curve 作为
  论文 #2 独立推进；
- (c) **先做 P0–P2（≈2.5 天 CPU）再决定**：用 census 与形式化语义审计的结果作为分流点，
  给出具体的分流判据（例如 OBSCURED 比例、canonical hash 与 benchmark P 能否证等价）。

我倾向 (c)，但需要你给**可执行的分流判据**而不是"看情况"。

## 问题 3：请给最小可决定切片（我下周就能跑完的那一块）

在 P0–P9 里，请指出**唯一一个**"跑完就能改变战略判断"的最小切片，满足：

- ≤1 周 CPU、不占 GPU（10×A5000 现被别的项目占用）；
- 产出一个可以写进台账的二值判定（不是"有信息量的观察"）；
- 失败时明确指向哪条路被杀死。

并请给这个切片的**前置冻结清单**（哪些必须先 hash 才能开跑），以及它**不得**碰 sealed 标签的哪些部分。

## 附：我会照办的两件事（不用裁决，登记备查）

1. F′ 的 novelty confidence 你给的是"中等偏低"，正式 claim 前必须专门检索
   `skill verification / test-carrying agents / mutation-based workflow validation /
   distinguishing tests / programming-by-demonstration for agent memory`。我会在写方案时把它列为
   P0 的并行前置，未通过不得写任何 novelty 措辞。
2. 台账将按 R1 第 4 节更正措辞（16 对样本量限定、532 vs 640 单位、P̂ v1 "未迁移"而非"仅指纹"、
   删除"全部发现被 P 卡死"的过度框定）。

约束同前：只读，不改仓库。给判据与数字。

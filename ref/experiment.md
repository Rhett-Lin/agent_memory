可以。这个问题其实比“选几个 benchmark 跑一下”更关键，因为如果你们要做的是一个新的 **Agent Memory Retrieval 方法**，审稿人真正会追问的是：

> **你提升的是“检索相似度”，还是检索出来的 memory 真的让 Agent 做出了更好的决定？**

我重新对照了目前最相关的几篇工作，尤其是 **Experience-Following、SAMem、RMM、SeCom、AgeMem、HiAgent、LongMemEval / LongMemEval-V2** 的实验设置。我的结论是：

> 如果目标是 ICLR / ICML / NeurIPS / ACL 级别的 Agent Memory Retrieval 论文，**只在 LoCoMo/LongMemEval 上做 Recall@K + QA accuracy 是不够强的**；最好同时做
>
> **“离线 retrieval correctness + 在线 Agent 行为提升 + hard-negative/noisy-memory stress test + scaling/efficiency”**。
>
> 最理想的数据集组合是：
>
> [
> \boxed{
> \text{LongMemEval-V2}
> +
> \text{ALFWorld}
> +
> \text{ScienceWorld}
> +
> \text{LongMemEval}
> }
> ]
>
> 再增加一个类似 Experience-Following 中 RegAgent 的**可控合成实验**，专门证明“我们的 retrieval score 真正对应 memory utility”。

下面我详细解释为什么。

---

# 一、先明确：你们到底要证明什么

我下面默认你说的 memory retrieval 是这种场景：

[
\mathcal M
==========

{m_1,m_2,\ldots,m_N}
]

其中每个 (m_i) 是过去 Agent 的：

* trajectory；
* trajectory segment；
* state-thought-action；
* experience；
* distilled skill；

当前 Agent 到达状态：

[
s_t
]

然后 retrieval module：

[
R(s_t,\mathcal M)
\rightarrow
{m_{i_1},m_{i_2},\ldots,m_{i_K}}
]

把这些历史经验送给 Agent：

[
a_t
===

\pi_\theta(
s_t,
R(s_t,\mathcal M)
)
]

也就是说你们做的是 **cross-trial episodic / experiential memory retrieval**，而不是单纯从当前 context 中找过去某一句话。

如果是这种方法，那么整篇论文其实需要证明下面这条因果链：

[
\boxed{
\text{Better Retrieval}
\Rightarrow
\text{Better Retrieved Experience}
\Rightarrow
\text{Better Agent Decision}
\Rightarrow
\text{Better Task Performance}
}
]

这里四个箭头缺一个，审稿人都有可能质疑。

---

# 二、为什么只看 Recall@K 不够

RAG 论文经常这样：

[
Recall@K\uparrow
]

然后证明 retriever 更好。

但 Agent Memory 不一样。

例如当前 Agent：

```text
Goal:
把苹果放进冰箱

Current state:
已经拿到苹果，站在冰箱前
```

Memory A：

```text
任务：
把苹果放进冰箱

经验：
先寻找苹果
```

Memory B：

```text
任务：
把牛奶放进冰箱

状态：
已经拿着牛奶站在冰箱前

经验：
open fridge → put object in fridge
```

如果按照 **task semantic similarity**：

[
sim(A,current)>sim(B,current)
]

因为 A 和当前任务都是“苹果”。

但是从当前决策来看：

[
Utility(B,current)>Utility(A,current)
]

这就是 SAMem 直接指出的问题：task-level 或 scene-level 相似并不意味着与**当前 decision state** 对齐。SAMem 因而把 memory 做到 state-thought 粒度，根据当前 state 检索高价值 reasoning。([ACL Anthology][1])

所以真正应该优化的目标不是：

[
\max sim(q,m)
]

而应该更加接近：

[
\boxed{
m^*
===

\arg\max_m
U(m\mid s_t)
}
]

其中：

[
U(m\mid s_t)
============

\text{memory }m
\text{ 对当前决策产生的实际帮助}
]

这其实应该成为你们实验设计的核心。

---

# 三、目前顶会论文分别告诉我们实验必须证明什么

把几篇最相关论文放在一起看，会非常清楚。

| 工作                             | 它重点证明什么                                 | 对我们实验设计的启示                                             |
| ------------------------------ | --------------------------------------- | ------------------------------------------------------ |
| SeCom, ICLR 2025               | memory granularity / retrieval 影响 QA    | **固定 retrieval token budget**                          |
| RMM, ACL 2025                  | retrieval recall 与最终 QA 都提升             | 同时报告 **retrieval metric + downstream metric + Oracle** |
| HiAgent, ACL 2025              | retrieval 对 long-horizon Agent 有帮助      | 不能只测 QA，要测 **SR、steps、context、runtime**                |
| Experience-Following, ACL 2026 | 检索到坏经验会导致 Agent 模仿错误                    | 必须做 **noise / misleading memory test**                 |
| SAMem, ACL 2026 Findings       | task-similar memory 可能 state-misaligned | 必须做 **state hard negative**                            |
| AgeMem, ACL 2026               | memory quality 应该和 task outcome 联合考虑    | 不应该只报告 memory relevance                                |
| LongMemEval-V2, 2026           | Agent memory 要能从海量历史 trajectory 提取环境经验  | 必须测 **large memory bank + latency**                    |

尤其值得注意的是，RMM 不只是报告最终回答准确率，而是在 LongMemEval 上同时报告 **Recall@5 和 QA Accuracy**，并提供 ground-truth Oracle retrieval：Oracle Recall@5 为 100%，对应 QA accuracy 90.2%，从而可以看到实际 retriever 距离上限还有多少空间。这个实验设计非常值得借鉴。

SeCom 则做了另一个非常重要的控制：它不是简单让所有方法都取 Top-5，而是在 LoCoMo 上固定约 **4K token retrieval budget**，在 Long-MT-Bench+ 上固定约 **1K tokens**。这是因为不同 memory unit 长度差异很大；只固定 K 并不公平。

---

# 四、因此，我建议把整篇实验设计成“四层证据链”

你们最好不要做：

```text
Dataset A
Dataset B
Dataset C

Method > Baseline
```

而应该设计成：

```text
Level 1
Retrieval 本身找得更准吗？
        ↓
Level 2
找得更准真的让 Agent 更好吗？
        ↓
Level 3
面对很难区分的错误 memory 还能找到正确的吗？
        ↓
Level 4
memory 很多、很脏、环境变化以后还能工作吗？
```

最后再加：

```text
Level 5
代价是多少？
```

这样整篇论文的论证链条就会非常完整。

---

# 五、第一层实验：Intrinsic Retrieval Quality

第一个问题非常简单：

> 给定一个 Agent 当前状态，我们到底有没有 retrieve 到真正应该 retrieve 的 memory？

这里需要有 ground-truth evidence 的数据集。

## 我最推荐：LongMemEval

LongMemEval 是 ICLR 2025 benchmark，共有 500 个精心构造的问题，覆盖：

* information extraction；
* multi-session reasoning；
* temporal reasoning；
* knowledge updates；
* abstention。

它最大的优势不是规模，而是存在明确的历史 evidence，可以比较 retrieval 是否找到了真正需要的信息。([arXiv][2])

因此可以直接测：

[
Recall@K
]

[
Precision@K
]

[
MRR
]

[
nDCG@K
]

以及：

[
AnswerAccuracy
]

---

# 六、为什么一定要同时测 Retrieval 和 QA？

假设：

### Method A

[
Recall@5=75%
]

[
QA=70%
]

### Method B

[
Recall@5=68%
]

[
QA=74%
]

那么非常有意思。

这说明：

> A 找到了更多“标注上相关”的 memory，但 B 找到的 memory 对 LLM 更有用。

也就是说：

[
\text{relevance}
\neq
\text{utility}
]

这正是 Agent Memory Retrieval 中很值得研究的东西。

RMM 就是按照这种方式把 retrieval quality 和 response quality 分开报告的。它还给出 Oracle retrieval，因此可以估计：

[
Gap_{\text{retrieval}}
======================

## Performance_{\text{oracle}}

Performance_{\text{ours}}
]

这是非常漂亮的实验。

---

# 七、但 LongMemEval 有一个明显缺点

它主要还是：

[
Conversation\ history
\rightarrow
retrieve
\rightarrow
QA
]

严格来说更接近：

> personalized conversational memory。

而如果你们的论文说：

> “Our method improves memory retrieval for LLM **agents**.”

审稿人完全可能问：

> “Where is the agent?”

因为这里只有：

```text
历史
→ 检索
→ 回答一个问题
```

而没有：

```text
state
→ retrieve memory
→ action
→ environment changes
→ next state
```

所以：

> **LongMemEval 可以作为 retrieval benchmark，但绝对不建议作为唯一的 benchmark。**

---

# 八、目前我更推荐 LongMemEval-V2

截至 2026 年 8 月，**LongMemEval-V2** 是特别值得关注的新 benchmark。

它和原始 LongMemEval 最大区别是：

原始：

[
\text{conversation history}
]

V2：

[
\boxed{
\text{historical web-agent trajectories}
}
]

也就是说，memory 真的是过去 Agent 在环境中的 interaction。

它包含 **451 个人工构造问题**，历史可以扩展到 **500 条 trajectories / 超过 1 亿 token 级别**，专门测试五类 Agent experience：

| 能力                     | 在测试什么         |
| ---------------------- | ------------- |
| Static state recall    | 环境里长期不变的东西记得吗 |
| Dynamic state tracking | 环境状态变化记得吗     |
| Workflow knowledge     | 以前学会的操作流程记得吗  |
| Environment gotchas    | 以前踩过的坑记得吗     |
| Premise awareness      | 当前前提条件是否和过去一致 |

其 context-gathering formulation 就是：

[
\text{Historical Agent Trajectories}
\rightarrow
\text{Memory System}
\rightarrow
\text{Compact Evidence}
\rightarrow
\text{Answer}
]

而且 benchmark 本身同时关注 **accuracy 和 query latency**。([arXiv][3])

这和一个新 Agent Memory Retriever 的目标非常契合。

---

# 九、为什么 LongMemEval-V2 特别适合你们？

因为它能天然测试一个非常重要的场景：

```text
现在：
一个 web agent 遇到问题

过去：
有几百条 agent trajectories

问题：
过去到底哪一段经验对当前问题有帮助？
```

这已经非常接近现实 Agent Memory 了。

例如：

```text
Memory 1:
以前点击某个按钮成功了

Memory 2:
以前同一个页面，
但是另一个 account 状态下，
点击这个按钮失败了

Memory 3:
另一个 app 有类似按钮
```

一个简单 embedding retriever 很可能：

[
sim(M_1,q)
\approx
sim(M_2,q)
]

但真正需要的是：

[
U(M_1|s)>U(M_2|s)
]

所以如果你们的方法核心是：

* state-aware；
* utility-aware；
* context-aware；
* trajectory-aware；

LongMemEval-V2 会非常合适。

需要说明的是，它目前是 2026 年新发布的 arXiv/项目 benchmark；因此我会把它作为**最新主 benchmark**，但不会只依赖它证明方法。([arXiv][3])

---

# 十、第二层实验：真正让 Agent 执行任务

这一层我认为是整篇论文最重要的。

我会选：

[
\boxed{\text{ALFWorld + ScienceWorld}}
]

原因不是它们“大家都用”，而是它们特别适合分离：

[
\text{Task}
]

和：

[
\text{Current State}
]

之间的差别。

SAMem 之所以使用它们，也是这个原因之一。其正式实验覆盖 ALFWorld、ScienceWorld 和 Jericho；ALFWorld 用每类 5 个训练任务构建 experience，并测试跨六类的 **134 个 unseen tasks**；ScienceWorld 覆盖全部 30 个 task types，每类 3 个训练实例，并在 **90 个 unseen instances** 上测试。

---

# 十一、ALFWorld 为什么特别适合 Retrieval 研究？

比如任务：

```text
Put a clean apple in the fridge.
```

可能经过：

```text
find apple
↓
take apple
↓
find sink
↓
clean apple
↓
find fridge
↓
open fridge
↓
put apple
```

现在假设 Agent 到：

```text
Current state:
apple 已经洗干净
正在 kitchen
fridge closed
```

过去 memory 里面有：

```text
M1:
Put apple in fridge
→ first find apple
```

和：

```text
M2:
Put clean tomato in fridge
State:
already cleaned tomato
→ find fridge
→ open fridge
→ put tomato
```

M1 task 更相似：

[
sim_{\text{task}}(M1)>sim_{\text{task}}(M2)
]

但是：

[
U(M2|s_t)>U(M1|s_t)
]

这就是一个天然的 **state-misaligned hard negative**。

而这正是 SAMem 指出的 task-level retrieval 问题。

所以 ALFWorld 对你们非常重要。

---

# 十二、ALFWorld 主实验应该怎么跑？

我建议设计成两个阶段。

## Phase A：固定 Memory Bank

先运行训练任务，得到：

[
\mathcal M_{\text{train}}
]

例如按照 SAMem 类似协议：

[
6\ task\ types
\times
5\ tasks/type
=============

30\ training\ tasks
]

但是这里有一个非常重要的实验设计：

> **所有 retrieval 方法必须使用完全同一份 memory bank。**

也就是说：

```text
                         Same Memory Bank
                                │
         ┌──────────────────────┼──────────────────────┐
         ↓                      ↓                      ↓
       BM25                 Dense Retriever         Ours
         ↓                      ↓                      ↓
      Same Agent             Same Agent            Same Agent
```

不能：

```text
Baseline:
自己的 memory construction

Ours:
另一种 memory construction
```

否则 reviewer 会问：

> 提升到底来自 memory construction，还是 retrieval？

如果论文贡献明确声称是：

[
\boxed{\text{Retrieval}}
]

那么主实验必须**冻结 write / memory construction**。

---

# 十三、测试阶段也不要 online 更新 Memory

第一套主实验：

[
\mathcal M_t=\mathcal M_{\text{train}}
]

整个 test 固定。

为什么？

因为如果：

```text
Test task 1
↓
写入 memory
↓
Test task 2
```

那么性能变化可能来自：

[
\text{retrieval}
+
\text{addition}
+
\text{memory evolution}
]

你就无法证明 retrieval 自己有效。

所以：

### Main experiment

[
\boxed{\text{Static Memory Bank}}
]

先干净地证明 retrieval。

之后再加：

### Secondary experiment

[
\boxed{\text{Online Evolving Memory}}
]

证明在真实长期 Agent 下依然有效。

这是非常重要的实验隔离。

---

# 十四、每一步具体怎么运行？

当前：

[
s_t
]

形成 query：

[
q_t=f(goal,s_t)
]

所有方法得到：

[
R(q_t,\mathcal M)
]

然后严格限制：

[
Tokens(R)\leq B
]

再给同一个 Agent：

```text
Goal
Current State
Retrieved Experience
↓
LLM
↓
Action
```

执行：

[
a_t
\rightarrow Env
\rightarrow s_{t+1}
]

继续直到成功或者达到 max steps。

于是唯一变化的是：

[
\boxed{Retriever}
]

这样 downstream improvement 才能归因给 retrieval。

---

# 十五、ALFWorld 要报告什么？

最基本的：

[
Success\ Rate
=============

\frac{#successful\ tasks}
{#tasks}
]

但只报 SR 还不够。

再报告：

[
Average\ Steps
]

以及：

[
SPL
]

SAMem 就使用 Success weighted by Path Length 来衡量“是不是不但成功，而且走了更短路径”。

这个指标对 retrieval 特别有意义：

假设：

### Baseline

```text
success = 80%
平均 22 steps
```

### Ours

```text
success = 82%
平均 13 steps
```

虽然 SR 只提高 2%，但其实 retrieval 很有价值：

> Agent 少走了大量无意义步骤。

所以建议 ALFWorld 至少报告：

| 指标                   | 说明                        |
| -------------------- | ------------------------- |
| SR ↑                 | 最终成功率                     |
| Progress ↑           | 未完全成功时完成了多少               |
| Avg Steps ↓          | 路径效率                      |
| SPL ↑                | success + path efficiency |
| Invalid Actions ↓    | 是否减少错误操作                  |
| Retrieved Tokens ↓   | memory context 成本         |
| Retrieval latency ↓  | 检索耗时                      |
| End-to-end latency ↓ | 整个任务耗时                    |

HiAgent 同样把 success/progress、average steps、context efficiency 和 runtime 同时纳入评估，而不是只看任务是否成功。

---

# 十六、ScienceWorld 为什么也应该做？

只跑 ALFWorld 一个 interactive environment 会有一个问题：

> 你的方法是不是只适用于 household navigation？

ScienceWorld 的任务结构复杂得多。

比如：

```text
Determine if an object conducts electricity.
```

可能需要：

```text
find object
↓
find battery
↓
find wire
↓
build circuit
↓
connect object
↓
observe bulb
↓
infer answer
```

因此其中会有：

[
\text{procedural state}
+
\text{scientific state}
+
\text{long-range dependency}
]

而且一个任务中相邻 stage 的正确 memory 差别很大。

SAMem 使用全部 30 类 ScienceWorld task，并以每类 3 个任务训练、3 个 unseen variant 测试，总计 90 个测试任务。

所以我会建议直接采用这一 protocol，方便和 SAMem / ExpeL / AutoGuide / CDMem 等对照。

---

# 十七、为什么我不建议只用 Jericho？

Jericho 可以作为第三个 robustness benchmark，因为它是 interactive fiction，状态比较复杂，也被 SAMem 和 AgentBoard 使用。

但它不是我最建议的第一优先级，因为：

* 环境和语言本身噪声更大；
* 不同 game 的 action space 差别明显；
* failure source 很难 attribution；
* 很容易出现 Agent 本身能力不足，而不是 retrieval 不行。

所以优先顺序我建议：

[
\boxed{
ALFWorld

>

ScienceWorld

>

Jericho
}
]

---

# 十八、第三层实验：这可能是最能体现创新的——Hard Negative Retrieval

如果你们只做普通 test：

```text
query:
clean apple

memory:
clean apple
clean sofa
heat potato
```

embedding retrieval 已经很强。

你们很难拉开差距。

真正应该构造的是：

[
\boxed{\text{Semantically Similar but Behaviorally Wrong}}
]

也就是：

> 看起来很像，但用它会害死 Agent 的 memory。

这和 ACL 2026 Experience-Following 的结论直接对应：Agent 会显著跟随 retrieved experience，因此 noisy / flawed memory 并不是无害 context，而会影响未来执行；作者进一步发现 selective addition 和 memory quality 对长期性能非常重要。([ACL Anthology][4])

---

# 十九、我会构造四类 Hard Negative

这是我认为你们论文最值得认真设计的一组实验。

### Type A：Same Task, Wrong State

Current：

```text
Goal:
clean apple and put in fridge

State:
apple already cleaned
```

Bad memory：

```text
Goal:
clean apple and put in fridge

State:
apple not found

Advice:
find apple
```

语义：

[
Similarity\uparrow
]

实际 utility：

[
Utility\downarrow
]

这是直接针对 SAMem。

---

### Type B：Same State, Wrong Goal

Current：

```text
holding apple
standing next to fridge
Goal:
cool apple
```

Memory：

```text
holding apple
standing next to fridge
Goal:
inspect apple

Advice:
examine apple
```

state 很像：

[
sim_s\uparrow
]

但 goal 不一致。

这样可以证明：

> 只 state-aware 也不够。

---

### Type C：Successful but Misaligned Experience

过去 trajectory：

```text
Task A
Success = 1
```

但是它在当前环境：

```text
Task B
```

会导致错误。

这个实验尤其重要，因为 Experience-Following 已经说明：

[
\text{Successful Past Experience}
\not\Rightarrow
\text{Useful Current Experience}
]

论文甚至做了 error-free 和 memory-quality 的分析，并通过 size-matched experiment 隔离 memory 数量与质量；相同 1000 条 memory 规模下，高质量保留策略仍然更好。

---

### Type D：Stale Memory

例如：

```text
Old:
button A opens Settings

Current:
UI changed
button A now opens Account
```

这种特别适合 WebAgent / LongMemEval-V2。

测试：

[
\text{recency / temporal validity}
]

而不仅仅是 semantic relevance。

---

# 二十、然后系统性改变污染比例

例如：

[
NoiseRatio
\in
{0,10%,30%,50%,70%}
]

然后画：

[
x=\text{Noise Ratio}
]

[
y=\text{Success Rate}
]

你希望看到：

```text
SR
│ Ours ───────────────
│             \
│ Dense        \
│       \        \
│        \        \
│         \        \
└──────────────────── Noise
  0   10  30  50  70%
```

如果方法在 clean memory：

[
+1.5%
]

但在 50% misleading memory：

[
+15%
]

这个故事比“平均涨 3%”强得多。

因为你证明了：

> **我们真正解决的是 memory retrieval 中 semantic similarity 与 behavioral utility 不一致的问题。**

---

# 二十一、第四层：Memory Bank Scaling

Agent Memory 的一个基本特征就是：

[
|\mathcal M_t|
\rightarrow
\text{越来越大}
]

如果实验永远：

```text
100 memories
```

reviewer 很容易质疑：

> 为什么需要一个新的 retrieval 方法？Brute-force LLM reranking 就行。

所以必须做：

[
N
=

10^2,,
10^3,,
10^4,,
10^5
]

如果数据允许，再做到：

[
10^6
]

LongMemEval-V2 特别适合这一点，因为它的历史 trajectory context 本身就可以扩展到极大规模。([arXiv][3])

---

# 二十二、Scaling 实验不要只画 Accuracy

建议同时画三条曲线：

[
RetrievalQuality(N)
]

[
TaskPerformance(N)
]

[
Latency(N)
]

理想情况：

```text
Memory size ↑

Ours:
Accuracy        stable
Agent SR        stable
Latency         slowly ↑

Baseline:
Accuracy        ↓
Agent SR        ↓
Latency         ↑↑
```

那么你才能说：

[
\boxed{
\text{Our retriever scales with long-term memory}
}
]

---

# 二十三、第五层：一定要固定 Token Budget

这是很多 Agent Memory 实验非常容易踩的坑。

例如：

### Baseline

retrieve：

```text
3 memories
400 tokens
```

### Ours

retrieve：

```text
3 memories
2400 tokens
```

然后 ours 更好。

这完全不能说明 retrieval 更好。

因为：

[
Context_{\text{ours}}
=6\times Context_{\text{baseline}}
]

---

# 二十四、所以不能只固定 Top-K

应该主实验固定：

[
\boxed{
\sum_{m\in R}Tokens(m)\leq B
}
]

例如：

[
B=
1024
]

或：

[
B=
2048
]

或：

[
B=
4096
]

然后不同方法在**完全相同 token budget** 下检索。

SeCom 正是如此：LoCoMo 设置约 4K tokens，Long-MT-Bench+ 设置约 1K，而不是机械固定相同 memory unit 数。

然后再做 sensitivity：

[
B=
512,1024,2048,4096
]

画：

[
\text{Performance vs Context Budget}
]

这能得到一个很漂亮的 Pareto curve：

[
\boxed{
\text{Agent Performance}
\quad vs\quad
\text{Retrieved Tokens}
}
]

---

# 二十五、Baseline 应该怎么选？

如果是 top-conference paper，我不会只比较：

```text
BM25
Dense
Ours
```

太弱。

至少应该形成一个**逐层增强**的 baseline ladder：

| 类别                | Baseline                   | 它回答的问题                 |
| ----------------- | -------------------------- | ---------------------- |
| No Memory         | 不 retrieve                 | memory 到底有帮助吗          |
| Random            | 随机 memory                  | 提升是不是“塞经验就行”           |
| BM25              | lexical retrieval          | 最基础 sparse retrieval   |
| Dense Retrieval   | embedding cosine           | 当前最常见 memory retrieval |
| Hybrid            | BM25 + Dense               | lexical+semantic 能不能解决 |
| Reranker          | Dense + reranker           | 强 retrieval pipeline   |
| Task-level Memory | 按 task retrieval           | 传统 experiential memory |
| State-aware       | SAMem-compatible retrieval | state information能否解决  |
| Our Method        | 你们的方法                      | —                      |
| Oracle            | ground-truth / best memory | 理论上限                   |

其中 **No Memory、Random 和 Oracle 特别重要**。

---

# 二十六、为什么 Random 必须有？

假如：

[
NoMemory=50
]

[
RandomMemory=58
]

[
Dense=61
]

[
Ours=63
]

那么意味着：

> 大部分提升只是因为给模型更多 examples。

你们 retrieval 的真实贡献只有：

[
63-58=5
]

而不是：

[
63-50=13
]

这会让解释更加科学。

---

# 二十七、为什么 Oracle 特别重要？

假设：

[
NoMemory=50
]

[
Dense=62
]

[
Ours=65
]

看起来 +3。

但如果：

### Oracle

[
66
]

那么：

[
Ours=65
]

已经接近 ceiling。

这是很强的结果。

反过来如果：

[
Oracle=90
]

那么：

[
65
]

说明还有巨大 retrieval gap。

RMM 的 LongMemEval 实验就明确加入 Oracle retrieval，因此能够把“检索问题”和“生成问题”部分分离。

---

# 二十八、Agent environment 怎么构造 Oracle？

LongMemEval 相对简单，因为有 evidence annotation。

ALFWorld / ScienceWorld 就比较困难，因为不存在天然：

```text
ground_truth memory ID
```

这里我建议做一个额外的 **Retrieval Audit Subset**。

随机采：

[
300\sim500
]

个 Agent states。

对每个：

[
s_i
]

从 memory bank 挑：

```text
1 relevant/useful memory
1 neutral memory
1 hard-negative memory
```

然后分别给**同一个 frozen Agent**：

[
\pi(s_i,m)
]

观察：

* next action correctness；
* short-horizon reward；
* full-trajectory success。

于是给 memory 定义一个实际 utility：

[
U(m,s)
======

## J(\pi|s,m)

J(\pi|s,\varnothing)
]

如果：

[
U>0
]

说明有帮助。

如果：

[
U<0
]

说明有害。

---

# 二十九、这会产生一个非常有价值的新指标

传统：

[
Relevance@K
]

你们可以进一步报告：

[
\boxed{Utility@K}
]

例如：

[
Utility@K
=========

\frac{1}{N}
\sum_i
\frac{1}{K}
\sum_{m\in R_K(s_i)}
U(m,s_i)
]

甚至：

[
HarmRate@K
==========

\frac{
#{m:U(m,s)<0}
}{
#Retrieved
}
]

这会非常符合目前 Agent Memory 的研究趋势。

因为你们不再说：

> “我们的 retrieved memory 在 embedding space 更 relevant。”

而是在说：

> **“我们的 retrieved memory 更可能真正改善 Agent 行为，同时更少检索到 harmful experiences。”**

这是一个明显更“Agentic”的 retrieval 定义。

---

# 三十、我甚至建议把论文的核心优化目标写成这样

传统 memory retriever：

[
R^*
===

\arg\max_R
\operatorname{Recall}(R)
]

而 Agent Memory Retrieval：

[
\boxed{
R^*
===

\arg\max_R
\mathbb E
[
J(
\pi_\theta
\mid
s,
R(s,\mathcal M)
)
]
}
]

subject to：

[
Tokens(R)\leq B
]

[
Latency(R)\leq L
]

也就是说：

> 在有限 token 和 latency budget 下，retrieve 最能改善 downstream Agent behavior 的 memory。

这个问题定义会比：

[
\text{better semantic retrieval}
]

有研究价值很多。

---

# 三十一、第六层：Distribution Shift

一个 memory retrieval 方法最终一定会遇到：

[
P_{\text{memory}}
\neq
P_{\text{test}}
]

所以可以构造：

### IID

memory 和 test task 同 distribution。

### Near-OOD

同一 task type，但：

```text
object
location
ordering
initial state
```

不同。

### Cross-task OOD

memory：

```text
put object
```

test：

```text
clean + put
```

### Cross-environment

如果方法允许：

```text
ALFWorld learned retriever
→ ScienceWorld
```

AgeMem 的一个有启发性的设计是只在 HotpotQA training set 上做 RL，然后直接在 ALFWorld、SciWorld、PDDL、BabyAI、HotpotQA 等不同任务上测试，以验证 learned memory management 的迁移能力。

对于纯 retrieval 方法，你们不一定需要跨环境 zero-shot，但至少应该证明：

[
\boxed{
\text{retrieval method 不只是在记住训练 task}
}
]

---

# 三十二、如果你们的方法需要训练 Retriever

那么数据一定要严格拆成：

[
D_{\text{train}}
]

[
D_{\text{dev}}
]

[
D_{\text{test}}
]

而且：

[
MemoryBank_{\text{test}}
]

可以包含过去 training experiences，但不能包含：

```text
同一个 test task 的 future information
```

尤其要避免 exact duplicate leakage。

例如：

```text
Training:
put apple in fridge, house configuration A

Test:
put apple in fridge, house configuration A
```

如果环境完全相同，很可能只是 trajectory memorization。

最好：

```text
same task family
different environment state
different objects
different goal combinations
```

SAMem 也是在 ALFWorld 上从训练任务构建 memory，再使用 unseen 134-task test set；ScienceWorld 同样使用 unseen task variants。

---

# 三十三、第七层：Backbone Generalization

Retriever 提升也可能是某个 LLM 特有的。

所以我建议至少：

[
\boxed{
3\ backbone\ settings
}
]

比如实验结构上用：

```text
强闭源模型
+
中等开源模型
+
较小开源模型
```

不要所有 main experiments 都只跑一个模型。

SAMem 的实验覆盖 GPT-4o、GPT-4o-mini、Qwen-2.5-72B 和 Llama-3.1-70B，并报告三次运行平均值，其目的就是说明 memory mechanism 的提升不是单一 backbone artifact。

你们不一定需要四个，但：

[
2\sim3
]

个是比较合理的。

尤其一个很有价值的分析是：

> **Retriever 对弱模型的帮助是不是更大？**

可能会看到：

[
\Delta_{\text{small}}

>

\Delta_{\text{large}}
]

因为小模型自身 reasoning 较弱，更依赖好的经验。

这会是很有意思的结果。

---

# 三十四、第八层：Top-K Sensitivity

不要只报告：

[
K=5
]

然后结束。

RMM 专门测试了不同 retrieval / reranking 数量，并观察到 retrieval 数量变化会同时改变 Recall 和 QA accuracy。

所以至少测试：

[
K=
1,3,5,10
]

但是记住：

主结果还是：

[
\boxed{\text{fixed token budget}}
]

K sensitivity 是 secondary analysis。

---

# 三十五、一个特别有价值的实验：Retrieval Score vs Actual Utility

假设你们的方法输出：

[
Score(m_i,s)
]

然后我们通过刚才的 controlled evaluation 得到：

[
U(m_i,s)
]

就可以画：

[
x=RetrieverScore
]

[
y=ActualDownstreamUtility
]

算：

[
Pearson
]

或者：

[
Spearman
]

你真正想证明的是：

[
corr(
Score(m,s),
U(m,s)
)
\uparrow
]

相比 embedding similarity：

[
corr(
Cosine(m,s),
U(m,s)
)
]

更高。

---

# 三十六、这个实验为什么非常重要？

因为 ACL 2026 的 Experience-Following 做了一个非常关键的观察：

[
InputSimilarity\uparrow
\Rightarrow
OutputSimilarity\uparrow
]

也就是 memory 越像当前 query，Agent 越容易模仿它；问题是这个 memory **不一定是对的**。

所以你们如果进一步证明：

[
\boxed{
\text{Our Retrieval Score}
\approx
\text{Behavioral Utility}
}
]

其实是在直接解决它暴露出来的核心问题：

> **Similarity is not Utility.**

我认为这个实验的说服力会非常强。

---

# 三十七、第九层：Counterfactual Memory Swap

还可以做一个非常漂亮的因果实验。

当前：

[
s
]

你们 retrieve：

[
m^+
]

Agent 成功。

然后保持：

```text
LLM
prompt
state
temperature
everything
```

全部不变。

只把：

[
m^+
]

替换成：

[
m^-
]

其中 (m^-) 是 semantic similarity 很高但 state-misaligned 的 memory。

比较：

[
P(success|m^+)
]

和：

[
P(success|m^-)
]

如果：

[
P(success|m^+)
\gg
P(success|m^-)
]

那么你就直接证明：

> 改变结果的确实是 retrieved memory quality。

而不是 Agent 自己本来就会做。

---

# 三十八、再加 No-Memory Counterfactual

同一个 state：

[
\pi(s,m^+)
]

[
\pi(s,m^-)
]

[
\pi(s,\varnothing)
]

形成三组：

| 条件                | 目的              |
| ----------------- | --------------- |
| Useful Memory     | memory 能带来多少正收益 |
| No Memory         | Agent 自身能力      |
| Misleading Memory | memory 能造成多大负收益 |

于是可以定义：

[
Gain
====

J(m^+)-J(\varnothing)
]

以及：

[
Damage
======

J(\varnothing)-J(m^-)
]

一个好的 retriever应该：

[
Gain\uparrow
]

同时：

[
P(retrieve\ harmful)\downarrow
]

---

# 三十九、第十层：Online Memory 实验

在 Static Bank 证明完 retrieval 后，再做真正长期运行：

```text
Memory M0
↓
Task 1
↓
retrieve
↓
execute
↓
new memory
↓
M1
↓
Task 2
↓
...
```

即：

[
\mathcal M_0
\rightarrow
\mathcal M_1
\rightarrow
\cdots
\rightarrow
\mathcal M_T
]

这时候画：

[
x=\text{Task Index}
]

[
y=\text{Rolling Success Rate}
]

以及：

[
x=\text{Memory Size}
]

[
y=\text{Success}
]

---

# 四十、为什么这组实验一定要作为 secondary？

因为 Experience-Following 的一个重要发现就是，动态添加低质量 memory 可能导致长期性能下降，而更严格的 memory selection 能改善长期表现。论文也专门做了 fixed memory、add-all、coarse evaluator 和 strict evaluator 的比较。

如果你们 retriever 能做到：

```text
memory 越积越多
```

但是：

[
Performance
]

不下降，甚至提升，

那么能说明：

> retrieval 在长期 memory pollution 下仍然鲁棒。

这比 static benchmark 更接近真正 lifelong Agent。

---

# 四十一、Efficiency 也必须认真做

Retrieval 方法很容易出现：

```text
Dense:
10 ms

Ours:
先用 GPT-4 rerank 100 条
15 seconds
```

然后准确率 +3%。

这种结果很难称为实用 improvement。

LongMemEval-V2 本身就把 accuracy 和 query latency 都作为关键维度，并显示复杂 agentic retrieval 方法虽然准确率更高，但 latency 仍是突出问题。([arXiv][3])

所以建议至少记录：

| Efficiency Metric        | 为什么需要                  |
| ------------------------ | ---------------------- |
| Query encoding latency   | query processing 多贵    |
| Retrieval latency P50    | 平均实际检索成本               |
| Retrieval latency P95    | tail latency           |
| Reranking latency        | reranker 是否成为瓶颈        |
| End-to-end Agent latency | 最终用户真正感受到的时间           |
| Retrieved tokens         | 增加多少 context           |
| LLM calls                | retrieval 是否额外调用模型     |
| Index size               | memory store 开销        |
| Index build time         | offline preparation 成本 |

最好画：

[
\boxed{
Accuracy\ /SR
\quad vs\quad
Latency
}
]

Pareto curve。

---

# 四十二、Ablation 应该怎么设计？

假设你们最后 retrieval score 是：

[
Score(m,s)
==========

\alpha S_{\text{semantic}}
+
\beta S_{\text{state}}
+
\gamma Q_{\text{quality}}
+
\delta U_{\text{utility}}
+
\eta R_{\text{recency}}
]

那么不要只做：

```text
Ours
Ours w/o component A
```

最好完整地显示：

| Variant   | Semantic | State | Quality | Utility | Recency |
| --------- | -------: | ----: | ------: | ------: | ------: |
| Dense     |        ✓ |       |         |         |         |
| + State   |        ✓ |     ✓ |         |         |         |
| + Quality |        ✓ |     ✓ |       ✓ |         |         |
| + Utility |        ✓ |     ✓ |       ✓ |       ✓ |         |
| Full      |        ✓ |     ✓ |       ✓ |       ✓ |       ✓ |

并分别报告：

[
Recall
]

[
Utility@K
]

[
AgentSR
]

这样能看到一个很重要的问题：

> 某个 component 是让 retrieval 更“相关”，还是让 Agent 真正表现更好？

这两者可能不同。

---

# 四十三、最终我最推荐的数据集组合

如果让我替你们设计一篇完整的 top-conference paper，我会采用：

| Dataset                 | 地位             | 主要证明什么                                             |
| ----------------------- | -------------- | -------------------------------------------------- |
| **LongMemEval-V2**      | Main           | 大规模 Agent trajectory retrieval                     |
| **ALFWorld**            | Main           | retrieval 是否改善真实 Agent actions                     |
| **ScienceWorld**        | Main           | long-horizon procedural/state-aware generalization |
| **LongMemEval**         | Main/Auxiliary | 有 ground-truth evidence 的精确 retrieval evaluation   |
| RegAgent-like synthetic | Analysis       | similarity vs utility 的因果实验                        |
| Jericho                 | Optional       | 开放式复杂环境 robustness                                 |
| LoCoMo                  | Optional       | conversational memory generalization               |

---

# 四十四、LoCoMo 要不要做？

可以做，但是我不会把它放在核心。

SeCom 在 LoCoMo 和 Long-MT-Bench+ 上很好地研究了 memory segmentation、compression 和 retrieval，而且固定 token budget 的 protocol 很值得沿用。([国际学习代表大会会议记录][5])

但是 LoCoMo 更像：

[
\text{Long Dialogue Memory}
]

而不是：

[
\text{Agent Experience Memory}
]

所以如果你们主打：

> **Agent memory retrieval for decision-making**

我会：

[
ALFWorld+ScienceWorld
]

优先于：

[
LoCoMo
]

---

# 四十五、HotpotQA 要不要做？

可以作为：

[
\text{supporting evidence retrieval}
]

或者 retriever training dataset。

AgeMem 就利用 HotpotQA 的 supporting facts 来训练与评价部分 memory quality。

但是我强烈不建议：

> HotpotQA 是唯一主实验。

因为 reviewer 很容易说：

> “This is retrieval-augmented QA, rather than agent memory.”

所以它最多作为 controlled retrieval dataset。

---

# 四十六、如果计算资源有限，我建议最小实验版本

如果先验证 idea，不需要一开始把所有东西跑完。

第一阶段做：

[
\boxed{
ALFWorld
+
LongMemEval
}
]

ALFWorld：

```text
证明：
retrieval → Agent performance
```

LongMemEval：

```text
证明：
retrieval → ground-truth evidence
```

然后做：

```text
Dense
State-aware baseline
Ours
Oracle
```

再加：

[
NoiseRatio
==========

0/30/50%
]

如果这时候已经能看到：

[
Ours>StateAware>Dense
]

并且：

[
Noise\uparrow
\Rightarrow
Ours\ degradation\ slower
]

就说明 idea 值得继续。

---

# 四十七、完整顶会版本，我会这样排 Main Experiments

### Main Table 1：Retrieval Quality

LongMemEval / LongMemEval-V2：

| Method      | Recall@5 | nDCG@5 | QA Acc | Tokens | Latency |
| ----------- | -------: | -----: | -----: | -----: | ------: |
| BM25        |          |        |        |        |         |
| Dense       |          |        |        |        |         |
| Hybrid      |          |        |        |        |         |
| Reranker    |          |        |        |        |         |
| State-aware |          |        |        |        |         |
| Ours        |          |        |        |        |         |
| Oracle      |      100 |        |        |        |         |

回答：

> “我们真的 retrieve 得更好吗？”

---

# 四十八、Main Table 2：Agent Performance

ALFWorld + ScienceWorld：

| Method      | ALF SR | ALF SPL | Sci SR | Sci Reward | Avg Steps |
| ----------- | -----: | ------: | -----: | ---------: | --------: |
| No Memory   |        |         |        |            |           |
| Random      |        |         |        |            |           |
| Dense       |        |         |        |            |           |
| Task Memory |        |         |        |            |           |
| SAMem-style |        |         |        |            |           |
| Ours        |        |         |        |            |           |
| Oracle      |        |         |        |            |           |

回答：

> “retrieval 的提升真的改善 Agent 了吗？”

---

# 四十九、Main Figure 1：Noise Robustness

[
x=NoiseRatio
]

[
y=SuccessRate
]

回答：

> “memory 中有坏经验的时候还能工作吗？”

这是直接回应 Experience-Following。

---

# 五十、Main Figure 2：Memory Size Scaling

[
x=MemoryBankSize
]

画：

[
Recall
]

[
SR
]

[
Latency
]

回答：

> “长期运行以后还能用吗？”

---

# 五十一、Main Figure 3：Similarity vs Utility

画两张：

### Dense

[
x=CosineSimilarity
]

[
y=ActualUtility
]

### Ours

[
x=OurScore
]

[
y=ActualUtility
]

比较：

[
\rho_{\text{Dense}}
]

和：

[
\rho_{\text{Ours}}
]

如果：

[
\rho_{\text{ours}}
\gg
\rho_{\text{dense}}
]

这可能会成为整篇论文最有说服力的一张图。

---

# 五十二、Main Table 3：Hard Negative

| Method      | Normal | Wrong-State | Wrong-Goal | Stale | Failed Experience |
| ----------- | -----: | ----------: | ---------: | ----: | ----------------: |
| Dense       |        |             |            |       |                   |
| Hybrid      |        |             |            |       |                   |
| State-aware |        |             |            |       |                   |
| Ours        |        |             |            |       |                   |

回答：

> “为什么不是直接 cosine similarity？”

---

# 五十三、Main Table 4：Ablation + Generalization

可以把不同 backbone 和组件拆开。

SAMem 的设计有一个值得借鉴的地方：它在多个 backbone 上、多个 environment 上报告结果，并且三次运行取平均，而不是只展示单次最优结果。

你们最好至少：

[
3\ runs
]

报告：

[
mean\pm std
]

对于 paired task outcomes，可以进一步使用：

* paired bootstrap；
* Wilcoxon signed-rank；
* 二元 success 可考虑 paired significance test。

HiAgent 的分析中也使用了统计检验而不仅仅是单点数字。([ACL Anthology][6])

---

# 五十四、一个非常重要的公平性原则

我会把这个原则甚至写进论文 experimental setup：

[
\boxed{
\textbf{Only the retrieval module changes.}
}
]

所有方法严格固定：

```text
same memory bank
same memory unit
same memory construction
same base LLM
same prompt
same action space
same environment
same decoding parameters
same retrieval token budget
same maximum steps
```

唯一不同：

[
R(\cdot)
]

如果你们做到这一点，就能非常有力地说：

> Improvement can be attributed specifically to the proposed retrieval mechanism.

否则 Agent Memory 论文特别容易有 confounding。

---

# 五十五、我尤其建议做两种 Memory Bank

这是我在看完 Experience-Following 后认为非常重要的设计。

## Bank A：Clean / Verified Memory

全部来自：

```text
successful
+
verified
```

experience。

作用：

> 在 memory 本身没有质量问题时，单独测试 retrieval ability。

---

## Bank B：Realistic / Noisy Memory

包含：

```text
successful
failed
partially correct
stale
state-misaligned
redundant
```

experience。

作用：

> 模拟真正长期 Agent。

因为现实 Agent 不可能 memory 永远都是完美的。

Experience-Following 的结果已经表明，低质量 addition 会导致长期 memory utility 下降，因此如果新 retriever 只在 perfect bank 上有效，现实价值有限。

---

# 五十六、这样你们会得到一个非常干净的二维分析

```text
                   Memory Quality
                 Clean        Noisy
               ┌──────────┬──────────┐
Dense          │          │          │
               ├──────────┼──────────┤
Ours           │          │          │
               └──────────┴──────────┘
```

如果：

### Clean

[
Ours-Dense=+3
]

### Noisy

[
Ours-Dense=+14
]

就说明：

> 你们的优势不是单纯更强 semantic matching，而是能区别**有用经验和诱导性经验**。

这个故事会非常强。

---

# 五十七、我认为最值得追求的论文主张

如果你们的方法真的和“状态 (p) / memory utility”有关，我不建议最后把论文包装成：

> We propose a better memory retriever.

这太普通。

更有研究价值的问题应该是：

[
\boxed{
\textbf{Semantic relevance is not equivalent to behavioral utility in agent memory retrieval.}
}
]

然后提出：

> Agent memory retrieval should retrieve experiences that are not merely similar to the current task, but **useful under the agent's current decision state**.

整个实验围绕这个 hypothesis：

[
H_1:
Similarity\neq Utility
]

[
H_2:
OurScore\rightarrow Utility
]

[
H_3:
BetterUtilityRetrieval
\rightarrow BetterAgentBehavior
]

[
H_4:
The advantage grows under
hard negatives/noisy memory
]

[
H_5:
The method remains scalable and efficient
]

这样会比单纯：

[
Recall@5+2.3
]

有完整得多的 scientific story。

---

# 五十八、如果让我现在直接确定实验配置

我会采用下面这套作为**最终方案**：

> **核心 retrieval benchmark：LongMemEval-V2 + LongMemEval；核心 interactive Agent benchmark：ALFWorld + ScienceWorld；额外做一个 RegAgent-like controlled environment。主实验统一固定 memory bank 和 token budget，只改变 retriever。LongMemEval 系列报告 Recall@K、nDCG、QA accuracy 和 Oracle gap；ALFWorld/ScienceWorld 报 SR、reward/progress、SPL、steps。然后专门构造 state-misaligned、goal-misaligned、successful-but-harmful、stale memory 四种 hard negatives，再做 0–70% noise、(10^2)–(10^5) memory scale、K/token-budget sensitivity、多个 LLM backbone 和完整 efficiency analysis。**

如果这一整套结果都成立，那么你们证明的就已经不是：

> “Retriever A 的 Recall 比 Retriever B 高。”

而是：

[
\boxed{
\text{Our retrieval method identifies memories that are causally more useful for future agent decisions.}
}
]

我认为这才是目前 **Agent Memory Retrieval** 方向真正足够有力的实验论证。

而且从最新工作来看，这个设计正好卡在一个很有价值的空隙上：**Experience-Following 已经证明了 Agent 会跟随 retrieved memory，SAMem 已经证明 task similarity 会遇到 state misalignment；但“怎样直接估计一条 memory 对当前状态的 behavioral utility，并据此 retrieval”仍然远没有被彻底解决。** ([ACL Anthology][4])

如果你们接下来真准备把这个方向落成论文，下一步最应该做的不是马上写方法，而是先把 **ALFWorld / ScienceWorld 中“memory bank 如何构造、每一个 memory 具体长什么样、current state 如何形成 query、ground-truth useful memory 怎么定义”** 彻底定下来。这个实验协议一旦定好，才知道你们的方法到底应该预测什么。

[1]: https://aclanthology.org/2026.findings-acl.722/ "SAMem: State-Aware Memory as a Fine-Grained Memory for LLM Agents in Decision-Making - ACL Anthology"
[2]: https://arxiv.org/abs/2410.10813?utm_source=chatgpt.com "LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory"
[3]: https://arxiv.org/abs/2605.12493?utm_source=chatgpt.com "LongMemEval-V2: Evaluating Long-Term Agent Memory Toward Experienced Colleagues"
[4]: https://aclanthology.org/2026.acl-long.27/?utm_source=chatgpt.com "How Memory Management Impacts LLM Agents"
[5]: https://proceedings.iclr.cc/paper_files/paper/2025/hash/e56f394bbd4f0ec81393d767caa5a31b-Abstract-Conference.html?utm_source=chatgpt.com "SeCom: On Memory Construction and Retrieval for ..."
[6]: https://aclanthology.org/2025.acl-long.1575.pdf?utm_source=chatgpt.com "HiAgent: Hierarchical Working Memory Management for ..."

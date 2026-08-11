 # 基于该论文的研究方向

## 一、实践应用方向

### 方向 1：Memory Retrieval 从 Similarity Retrieval 转向 Procedure Retrieval

目前很多 memory retriever 使用：

\[
\operatorname{cos}(e_{\text{task}},e_{\text{memory}})
\]

但论文表明：

\[
\text{textual semantic similarity}
\neq
\text{procedural equivalence}
\]

因此，未来 memory retrieval 更应该判断：

\[
\boxed{
\text{procedural compatibility}
}
\]

而不仅仅是：

\[
\text{text similarity}
\]

更进一步，可以设计：

\[
score(m,x)
=
f(
\text{program compatibility},
\text{state},
\text{expected utility}
)
\]

即：memory 是否真正适用于当前任务，应该取决于它与当前任务底层程序是否兼容，而不只是表面文本是否相似。

---

### 方向 2：Memory Admission / Abstention

传统 memory system 往往是：

```text
检索到 top-1 memory
→ 直接给 Agent 使用
```

但论文中的 near-miss 结果说明，一段看起来很相似但底层程序错误的 memory 可能反而降低 Agent 的成功率。

因此系统应该允许：

\[
\boxed{
\text{retrieve nothing}
}
\]

即加入 memory admission / abstention 机制。

例如，如果估计：

\[
P(\text{near-miss})>\delta
\]

则不使用当前 memory。

更进一步，可以直接估计 memory 对当前任务的 causal utility：

\[
\boxed{
E[
Y(x,\{m\})-Y(x,\emptyset)
\mid x,m
]
}
\]

如果：

\[
U(m,x)<0
\]

则不应该 retrieve 或注入该 memory。

---

### 方向 3：Memory Compression

论文的实验表明，不是所有 memory token 都同样重要。

memory 中真正关键的信息可能包括：

- causal decision；
- branch condition；
- critical state；
- action；
- termination criterion。

而很多内容，例如：

- 对话中的礼貌语；
- 重复 observation；
- 无效 intermediate tokens；

可能并没有太高的决策价值。

因此未来可以研究：

\[
\boxed{
\text{decision-aware memory compression}
}
\]

即在压缩 memory 时优先保留：

- decision；
- condition；
- action；
- finish / termination。

而不是简单按照固定 token budget 从尾部截断。

这个方向还可以进一步和 Agent inference efficiency 结合，因为减少 memory token 可以降低：

- prompt 长度；
- prefill latency；
- attention 计算量；
- API 输入 token 成本。

---

### 方向 4：Agent Memory Benchmark

未来 Agent Memory benchmark 不应该只比较：

\[
\text{Memory ON}
\quad vs.\quad
\text{Memory OFF}
\]

而应该系统地区分：

```text
P=1, S=0
P=1, S=1
P=0, S=1
P=0, S=0
```

其中尤其值得关注：

\[
A01=(P=0,S=1)
\]

因为它对应：

> 表面高度相似，但底层程序错误的 memory。

因此 A01 很适合作为：

\[
\boxed{
\text{memory robustness benchmark}
}
\]

未来评测 memory system 时，可以同时报告：

- structural transfer；
- replay；
- harmful flip；
- context effect。

这样才能判断一个 memory system 的提升到底来自真正的迁移，还是主要来自 replay。

---

## 二、未来研究方向

### Future 1：学习真实世界的 Latent Program

论文中的 latent program：

\[
z
\]

来自人工设计的 generator。

但现实 Agent 任务中并没有现成的 program oracle。

因此未来一个重要方向是从真实 trajectory 中自动抽取：

\[
\tau
\rightarrow z
\]

例如：

```text
raw trajectory
↓
workflow abstraction
↓
dependency graph
↓
program representation
```

也就是说，需要研究：

> 如何从 Agent 的历史执行轨迹中学习一个能够表示底层程序结构的 representation。

---

### Future 2：Program-aware Retriever

可以构建：

\[
f(x,m)
\rightarrow
P(P=1\mid x,m)
\]

用于预测当前 task 与 memory 是否属于同一个底层 program。

相比单纯 embedding similarity，可以考虑利用：

- action dependency graph；
- tool-call structure；
- causal state transitions；
- symbolic program induction；
- learned workflow representation。

目标是让 retriever 真正识别：

\[
\boxed{
\text{program equivalence}
}
\]

而不是只识别文本相似度。

---

### Future 3：Utility-aware Memory Admission

真正需要估计的可能不是：

\[
P(P=1)
\]

而是：

\[
\boxed{
E[
Y(x,\{m\})-Y(x,\emptyset)
\mid x,m
]
}
\]

也就是：

> 这段 memory 对当前 task 的 causal utility。

如果：

\[
U(m,x)<0
\]

那么即使它在文本上非常相似，也不应该被使用。

因此未来可以研究：

\[
\boxed{
\text{utility-aware memory admission}
}
\]

即让 Agent 学会判断：

> 什么时候应该使用 memory，什么时候应该拒绝 memory。

---

### Future 4：研究更大模型是否出现 Program Abstraction Emergence

论文中观察到：

\[
3B<0,\quad 7B>0,\quad 8B>0
\]

即小模型的 structural transfer 可能为负，而更强模型开始出现正向 structural transfer。

因此一个自然问题是研究：

\[
\tau_{\text{struct}}(M)
\]

随着模型规模或能力 \(M\) 如何变化。

是否存在一个阈值：

\[
M>M^*
\]

之后：

\[
\tau_{\text{struct}}>0
\]

如果存在，这可能意味着：

\[
\boxed{
\text{procedural abstraction emergence}
}
\]

即模型达到一定能力后，才真正具备跨表面差异提取并复用底层程序的能力。

---

### Future 5：把 Replay 和 Agent Cache 统一起来

论文的结果显示，大量 matched-memory improvement 实际上来自 replay。

因此很多所谓的 memory system，在系统层面可能更接近：

\[
\boxed{
\text{semantic cache + execution trace reuse}
}
\]

而不一定是真正意义上的 lifelong learning。

未来可以明确区分两类 memory：

#### Episode Cache

主要优化：

\[
\text{exact / near replay}
\]

用于快速复用过去几乎相同的任务经验。

#### Procedural Memory

主要优化：

\[
\text{cross-surface transfer}
\]

用于保存和迁移跨任务、跨领域可复用的 procedure。

因此可以进一步研究：

\[
\boxed{
\text{Episode Cache}
+
\text{Procedural Memory}
}
\]

的双层 Agent Memory 架构。

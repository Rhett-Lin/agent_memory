# H3 结果分析备忘录（2026-08-08，先自分析 → 再走 GPT-5.6 讨论流程）

## 1. 数据与合规

- 网格：32 fresh families × 4 siblings × {A10,A11} × 5 arms × 3 seeds × 2 models = 7680 memory rollouts + N/Q 参考 1536 → 9216 条；parseable：7B 99.8%、3B 96.6%。
- 五门验收全过；canonical SA PASS（512/512 对 100% 命题对齐）；隔离 0 命中；oracle 640/640 + 复跑 64/64；N 条件双模型处 30–70% 区间（7B 0.557 / 3B 0.388）。
- 入网登记：family 簇协方差驱动的 power 模拟 → 24→32（冻结上限）；α 功率记录于 power_sim.json。

## 2. 冻结 estimand（family-cluster bootstrap 2000，Holm m=6 = 3 estimand × 2 models）

| estimand | 7B | 3B | Holm 判定 |
|---|---|---|---|
| **ε_form = τ_rl(SC) − τ_rl(TC)** | −0.034 [−0.106,+0.039] | −0.065 [−0.132,−0.000] | 均 n.s.（3B raw p=0.054；且**方向与 H-C 相反**：TC > SC） |
| **ε_int** | −0.029 [−0.135,+0.072] | −0.008 [−0.125,+0.113] | 均 n.s. |
| **ε_cov(larger)=transcript: TC−TP** | +0.081 [−0.019,+0.178] | +0.102 [+0.019,+0.190] | raw p 0.115/0.018；**Holm（m=6）0.46/0.108 均 n.s.** |

τ_rl 各臂：

| arm | 7B | 3B |
|---|---|---|
| transcript_complete | **+0.104 [+0.042,+0.171] SIG** | **+0.190 [+0.123,+0.259] SIG** |
| script_complete | +0.070 [−0.004,+0.146] | +0.125 [+0.053,+0.201] SIG |
| transcript_prefix | +0.023 [−0.051,+0.105] | +0.089 [+0.016,+0.159] SIG |
| script_prefix | +0.018 [−0.042,+0.079] | +0.031 [−0.031,+0.096] |
| **eco（H-C 原样 300-token 硬截）** | **−0.003 [−0.083,+0.083]** | +0.052 [−0.020,+0.127] |

- TOST(τ_rl(TC), ±3pp)：两模型均**拒绝等价** → transcript-complete 的重放收益是实质性非零（7B est 0.104 ci90 [0.036,0.174]；3B 0.190 [0.120,0.268]）。
- token-协变量敏感性（exploratory）：7B ε_form 调整 token 后 **−0.102 [−0.177,−0.034] 显著为负**——TC 相对 SC 的优势不是"更长"造成的假象（反而被低估）；3B −0.078 n.s.。
- eco−tp 差：7B −0.026 / 3B −0.036，n.s.，方向一致（eco 比 propositional-boundary prefix 更差）。

## 3. 冻结判定树（GATE_PROTOCOL §13）在当前证据下的读数

1. ε_form CI 不含 0 且与 H-C 同向 → **不满足**（两模型 n.s.，且方向反）。
2. ε_form CI 含 0 且 ε_cov 显著 → **严格 Holm 不满足**（raw 方向一致 2/2 models，但 m=6 后 n.s.）。
3. 两者含 0 且生态臂显著 → eco−tp n.s. → 不满足。
4. 全 n.s. + 点估计 <4pp + CI 半宽 <4pp → 不满足（点估计大、CI 宽）。

→ 冻结 GO 判据**未达成**。同时必须如实登记：判定树的分肢 2 在方向上成立（coverage 是却是唯一在两模型一致方向的操纵）、TC 臂在两模型 SIG 非零、eco 臂复现 H-C 的 ≈0。

## 4. 我的解读（提交 GPT-5.6 质询）

1. **H-C 的 −15.8pp 差异几乎全部可以解释为覆盖+预算帽**：eco（300-token 硬截）在 7B 给出 −0.003 ≈ H-C 的 −0.014；而相同内容完整呈现为 transcript 时，replay 溢价为 +10.4pp/+19.0pp。"transcript 不兑现 replay"被证伪——**完整 transcript 不仅兑现，还优于 script**。
2. **SC（procedural/imperative）没有任何形式优势**：主判据 ε_form 两模型为负。H-C 时报表象的"procedural >> raw"其实是"complete-ish schema-of-decision >> truncated transcript"，覆盖差是根因。pilot 的 τ_rl=+0.144（procedural 卡）与 H3 的 SC=+0.070/+0.125、TC=+0.104/+0.190 同量级——形式之间没有系统性差距。
3. 严格 Holm 下 ε_cov n.s. → 严格措辞是：**覆盖解释得到方向性支持（2/2 models、eco 与 H-C 数值吻合、完整覆盖 SIG），但 ε_cov 的 m=6 显著性未达**，应报告为方向+机制证据链，不写"已确认"。
4. ε_form 方向反 + token 调整后更负（7B SIG−）暗示 **transcript 的实际内容量（context/证据展开）可能真有增益**——值得作为 exploratory 报告，不是主结论。
5. 对项目主线的含义：
   - "只写因果测量论文"路径现在更实：F-MED 分解 + scale 反转 + HFR 结构证据 + no-recognition + 两个诚实 NO_GO（H-C 与 H3 判据未达但机制清晰）+ H3 的 boundary finding（覆盖论）。
   - H3 也给出可写的结果："H-C anomaly 归因于预算-截断，而非表示形式"——用 fresh data + 预注册析因干净回答了一个 mech 问题。这是 method paper 的"validate-the-instrument"贡献。

## 5. 待 GPT-5.6 回答的三个问题

1. 在"ε_form n.s. 且反向 + ε_cov Holm n.s. + TC SIG + eco≈H-C"的组合下，最诚实的 Gate 判定与下一步（按 loop §15）是什么？算第 2 次连续 NO_GO 吗（我认为 H3 是"判据未达但识别目标已回答"，应记为负结果但**不**算是 Gate A/B 型失败，而是 H-C 链路的澄清实验——你同意吗）？
2. ε_cov 的 Holm family 定义（"两形式取大号为 pre-registered single test"）被我自己写得含糊，我按 larger=transcript 在双模型做 Holm（p_raw 唯一显著的 3B 0.018 → adj 0.108）。这是否合法，还是应该把整个 coverage 判读降级为 exploratory？请给审稿级别的措辞建议。
3. 现在的正确下一步是开始写测量论文（含 H-C/H3 全部证据链），还是再花一轮资源补 ε_cov 的方向性确认（比如在 7B 上把 family 上限自 32 推到 48）？成本和收益怎么权衡？

## 6. 冻结声明（复用治理规则）

讨论完成前不启动新实验、不修改 hypothesis、不写 Gate 结论。

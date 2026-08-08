# Llama-3.1-8B 第二家族复现记录（2026-08-08）

## 数据

- 网格：40 pilot families × 4 sib × 6 cells × 4 seeds = 3840 rollouts，6 shards（GPU0–5），`configs/pilot_llama8b.yaml`；模型 = `NousResearch/Meta-Llama-3.1-8B-Instruct`（本地 HF 缓存 d10aef79）；vllm 0.6.6.post1，gpu_mem_util 0.9。
- 产物：`rollouts_llama8b_shard000..005-of-006.jsonl`；`pilot/llama8b/LLAMA8B_RESULTS.json`（family-cluster bootstrap 10,000 reps，seed 1234，与 pilot 完全同构的估计流程，由 parent 接手执行因 agent-12 超时）。
- parseable action rate = **0.9939**（selfcheck 早 PASS；harness 无 chat-template 改动，唯一记录点：vllm 的 Llama 模板与 Qwen 同构的 JSON-mime 输出直接可用）。
- agent-12 在网格满员后 timeout；分析与判定由 parent 接手，未重跑任何 rollout。

## 结果（family-cluster bootstrap）

| 量 | Llama-3.1-8B | Qwen2.5-7B（参照） | Qwen2.5-3B（参照） |
|---|---|---|---|
| N rate | 0.373 | 0.547 | 0.420 |
| τ_context (Q−N) | **+0.034** [+0.010,+0.058] **SIG** | +0.027 n.s. | −0.019 n.s. |
| τ_struct (A10−A00) | **+0.047** [+0.020,+0.073] **SIG** | +0.092 [+0.036,+0.152] SIG | −0.066 [−0.131,−0.002]（Holm n.s.） |
| τ_trap (A01−A00) | **+0.087** [+0.043,+0.134] SIG | +0.081 [−0.006,+0.173] n.s. | −0.011 n.s. |
| τ_replaylike (A11−A10) | **+0.133** [+0.069,+0.193] SIG | +0.144 [+0.087,+0.200] SIG | +0.102 [+0.039,+0.161] SIG |
| A11 rate | 0.544 | 0.733 | 0.409 |
| A11-leg share of matched effect | **79%**（0.180/(0.180+0.047)） | 72% | （不适用，τ_struct 反号） |
| HFR(A01) | 0.100 [0.075,0.125] | 0.092 [0.063,0.120] | 0.188 [0.151,0.225] |

## 判定（parent）

1. **replay 主导再次确认**：Llama 的 A11 腿占 matched 效应 79%（7B 72% 同量级）。
2. **结构迁移方向随规模反转的家族间一致性**：τ_struct 在 Qwen3B 为负、Qwen7B 正、Llama-8B 正——同一 harness 同一程序族下，结构效应的方向呈能力门槛而非 Qwen 特异。**支持论文主线"structural transfer scales, helpfulness doesn't"。**
3. **近错卡危害再次确认**：HFR=10.0%，处 7B(9.2%) 与 3B(18.8%) 同量级。
4. **家族特异点登记**：τ_context 仅 Llama 显著为正（+0.034，sham 控制有效但带 small positive format/context effect）——论文将如实报告而非掩盖。
5. **scope**：仅 1 个 Llama 家族、frozen backbone、同 harness；不涉及 Instruct 系列其它成员或 frontier model 外推。

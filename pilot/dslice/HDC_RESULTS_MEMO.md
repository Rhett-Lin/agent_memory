# H-DC 结果备忘（2026-08-08，Part IV + Part IV-A 执行完毕）

**Verdict: GO（qwen7b）。** ≥1 模型 E1 Holm SIG+ 且 ≥+5pp 且 E3 非劣成立，满足 A5 GO 判据。

## 数据
- 网格全部完成：dslice / raw_matched / raw(300) / procedural，每模型每系统 2,560 A-cell rollouts（40 fam × 4 sib × 4 cells × 4 seeds），N/Q 复用 pilot。合计新增 12,800 rollouts。
- 分析 `pilot/dslice/analyze_dslice.py`：family-cluster bootstrap 2,000 reps，Holm m=6（primary 族见 GATE_PROTOCOL Part IV-A A4）。完整数值在 `pilot/dslice/HDC_RESULTS.json`。

## Primary contrasts（Holm m=6）
| contrast | 7b | 3b |
|---|---|---|
| E1 = τ_rl(dslice)−τ_rl(raw_matched) | **+0.145 [+0.048,+0.233], p_holm=.012** | −0.084 [−0.177,+0.002], p_holm=.973 |
| E2 = τ_rl(dslice) | +0.112, p_holm=.051 | +0.041, p_holm=.662 |
| E3a = ΔHFR 非劣（u95<+5pp） | −0.055 (u95 −0.016) ✓ | −0.022 (u95 +0.011) ✓ |

- E1(7b)：decision-aware 压缩比**等长**朴素截断多兑现 +14.5pp 回放溢价（raw_matched 的 τ_rl ≈ −0.03，几乎归零；dslice 把 7b 回放溢价从 0.112（自身）对比到 0.670 vs 0.527 的 A11）。
- E3a 双模型非劣成立（dslice 的 HFR 反而低于 raw_matched）。

## Secondary（CI only, 未 Holm）
- E1 vs raw(300)：7b +0.127 [+0.034,+0.214]；3b −0.123 [−0.216,−0.039]。
- Δτ_trap vs raw_matched：7b +0.139 [+0.075,+0.204]——τ_trap 更高 = 近失危害更轻，dslice 双优。
- τ_struct(dslice)：7b +0.048 [−0.008,+0.111]；3b +0.053 [−0.003,+0.114]。
- 3b 解读：弱模型无 E1（基线 τ 结构在 pilot 即为负/弱），且 E1_300 显著为负——3b 上截断到 300 的 raw 反而比 dslice 好；E3a 非劣仍成立。论文措辞：效应在 7B 显现，3B 未见增益（能力门槛，与 pilot τ_struct 的 scale 依赖一致）。

## A6 时间混杂断言（全部通过）
- config_hash：7b 四臂一致；3b 的 pilot N/Q 文件 hash 不同，唯一差异 = `gpu_memory_utilization 0.6→0.85`（资源配置，与任务/解码/提示无关）。
- env_versions（vllm/torch/GPU）全臂一致。
- harness.py 在 raw(300)-7b 之后有改动（`_chat_single_bos`）：**对 Qwen 已验证为无操作**——两条 token 化路径在 Qwen2.5-7B 上逐 id 相同（见提交记录中的验证脚本输出）。

## 卡片层事实（Part IV-A A3 已披露）
- dslice 卡 mean 237.5 tok（min 102, max 299），escalation 分布 {0:14,1:76,2:281,3:8,4:252,5:9}，QA-fail=0，finish/决策参数/aggregate 值 100% 保留。
- raw_matched 与 dslice 逐卡 |Δtok| = 0（640/640）。

## 论文可用声明（边界）
- 可写：在同源轨迹、逐卡等 token 预算下，decision-aware 压缩策略在 Qwen2.5-7B 上相对朴素截断多兑现 14.5pp 回放溢价（Holm 校正后显著），且不放大近失陷阱（非劣）。
- 不可写：效应归因于某一单独规则（D1–D5 是打包策略）；3B 上有正效应（没有）；dslice 达到 procedural 卡水平（A11 0.670 < procedural 0.733，仍有差距）。

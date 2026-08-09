# NEXT_ACTION — 评审阶段已完成，相机就绪前事项（2026-08-09 更新）

**Loop 全程 + 写作评审阶段已完成**（Gate 0 → pilot/Gates → H-C/H3 → 论文初稿 → H-DC deployment → auto-review-loop 3 轮终止）。

## 当下完成位置

- **论文 17pp**：`iclr2027/main.pdf`（pdflatex ×2：0 错误 / 0 未定义引用 / 0 overfull），全部数字与归档 JSON 一致（评审独立复算 max 差异 0）。
- **auto-review-loop 终止**：4/10 → 5/10 → **6/10, verdict Almost，达停止条件**（≥6 且 ready/almost）。记录：`review-stage/AUTO_REVIEW.md`(+\.html)、`REVIEW_STATE.json`(completed)、trace `.aris/traces/auto-review-loop/2026-08-08_run01/`。
- **H-DC 结论档位**（评审认可）：mixed-provenance benchmark 对比——7B pooled E1=+14.5pp Holm p=.012、HFR 主 guardrail 双模型成立、τ_trap 次项仅 7B 成立、3B 无 pooled 获益证据（−8.4pp）；provenance 交互显著（7B +0.382 [+0.166,+0.606]）。
- 台账已同步：`RESEARCH_LEDGER.md`（写作/评审阶段 + 外部讨论记录 2026-08-09）、`DECISION.md`（决策链第 8 行）。

## Blocking follow-up（未执行，需新算力+裁决）

- **fallback-free re-harvest + H-DC 重跑**：验证 dslice 在真实模型轨迹上的部署获益（当前未确立：+4.1pp，CI 跨 0）。受 fix budget 与 2026-08-08"停实验"裁决约束，启动前须按负结果处置规则先自析 + GPT-5.6 讨论。

## 相机就绪前（可选）

- 图 vector 化、模型作者匿名状态复核、reproducibility 仓库脱敏；
- 工作区未提交改动（评审修复三轮 + 新产物）尚未 commit——待用户确认后提交。

## 纪律（保持中）

- Gate C cond3 放弃、TRU-Mem 不启动、power chasing 禁令、负结果处置三件套——全部按既有记录执行；
- Part IV 预注册 provenance 以 commit 时间线披露（实现前注册不可独立验证），不再使用 "pre-registered" 称呼 Part IV/IV-A。

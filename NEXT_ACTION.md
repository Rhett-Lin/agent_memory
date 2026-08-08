# NEXT_ACTION — 写作打磨与评审阶段（2026-08-08 收尾）

**Loop 全程已完成**（Gate 0 → Round 1 pilot/GateA/GateB/H-C/H3 → Round 2 文献复核/Gate C-lite/§11/论文计划 → 补强实验两枚 + iclr2027 初稿）。

## 当下完成位置

- **§11 审查通过**（贡献 2/3，main 档路径铺通）；`PAPER_PLAN.md` archive
- **论文初稿完成**：`iclr2027/main.tex` → `main.pdf`（14 页，pdflatex 0 错误，全部主图主表来自实测 JSONL；两个 NO_GO 如实写；第二家族与外部验证附录已补）
- **补强实验（两枚）全部完成**：
  1. Llama-3.1-8B 第二家族 pilot（3840 rollouts，`pilot/llama8b/`）——replay 主导 79%、τ_struct=+0.047 SIG、HFR=0.100、τ_context=+0.034（家族特异）；→ 整合进 `appendix.tex app:llama` 与 findings 段
  2. ALFWorld 外部效度（144 rollouts，`pilot/external/`）——ordering 部分复现（R 22.2% > S 19.4% > N 16.7%）、clean family 全复现；**near-miss 危害未复现**（X=25%≥N），类型差异（recoverable omission vs active flip）如实写入 `app:alfworld` 与 discussion

## 下一步（写作阶段，可选）

- 对 `iclr2027/` 做 per-section polish（methods reviewer 视角：estimand 命名/多重性/措辞），随后 `auto-review-loop` 跑 2 轮外部评审与 90 天 fresh-arxiv 复查；
- camera-ready 前复核：图变 vector、模型作者匿名状态、reproducibility 仓库脱敏。

## 纪律（保持中）

- Gate C cond3 放弃、TRU-Mem 不启动、power chasing 禁令、负结果处置三件套——全部按既有记录执行；
- 两项补充实验均有 timeout 恢复曲线（ALFWorld install/env 独立性、Llama 超时代理），全部如实写入 `pilot/external/EXTERNAL_VALIDATION.md` 与 `pilot/llama8b/LLAMA_NOTES.md`。

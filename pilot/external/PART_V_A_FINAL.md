# Part V-A(冻结版)— 池构造修正案(实现期缺口,分析前登记;本轮裁决的最终可行性修正)

> 状态:FINAL(2026-08-10),经 GPT-5.6 裁决(thread 019fe550 第六轮,GO with mandatory amendments)。
> 触发:Part V(冻结§3.3–3.5)池构造规则不可行。**本修正案只动池构造与网格规模;翻转机制、构造断言、provenance、分析(Part V §6)、终态与出版边界、headroom、prompt 包全部不变。**
> **最终性条款:本修正案是最后一次可行性修正。修订分配器的模拟达不到可行动门槛,或实际 harvest 在预算内产不出 50+50,一律记 NOT_ESTIMATED 并关闭 Part V——不再缩减网格、不再加尝试数、不再放松匹配、不再复用源。**

## A1. 为什么原冻结规则不可行(实施期实测)

- 静态资格(8R+8X/目标):heat 158 / cool 112,表面充足;
- 冻结全局池序(heat 先 cool 后)+ "attempt=死亡"保留:(对象,容器)元组跨角色互相吞并,dry-run(p=0.5):heat ≈39/60,cool ≈0-2/60;
- 我此前的 accept-only 模拟存在**建模错误**(裁决指出):被否决候选若为其他目标复用,在 `candidate|role|attempt_idx` 的确定性 seed 规则下拿到的是**重复同批尝试**而非新伯努利试验;其 cache-consistent 复核(p=0.17)50+50 达成率仅 2% → A1 原方案不可行。

## A2. 源-尝试契约(冻结,取代 §3.5.4 的保留语义)

1. **ex-ante 角色分立**:每个 game 预先恰好指派一个角色(target / R-source / X-source,于具名池内)。曾被用作"源"尝试的 game 永不得再当 target 或异角色源;
2. **全局尝试上限**:每 `(candidate_path, assigned_role)` 全局至多 **8 次尝试**,结果缓存;同一 attempt key 绝不重复执行(杜绝"重复假装独立试验");
3. 首次成功 → 该源可用;8 次全败 → 该源**永久失格**(但不连坐其元组里未尝试的局);
4. 被接受的源严格唯一(仅服务一个 cluster)。
→ 保留 accept-only 的合法部分(失败不毁灭无关局/元组),杜绝重复机会与 target 污染。

## A3. 池构造改为冻结的元组约束匹配(取代贪心序)

- 源可用性确立后,按 **确定性的 (obj, recep) 元组约束匹配/流**分配唯一成功的 R/X 源给预冻结目标:
  同 obj + 同 recep;最大化 `min(n_heat, n_cool)`;一切 tie 按 sha256(canonical path) 序;
  校准池(20+20)与 headroom(6+6×2)在同一次全池分配中预留;
  **必须恰好 50 heat + 50 cool,否则 NOT_ESTIMATED。**
- 因果 estimand 与推断(Part V §6)不受影响——改动仅限池构造。

## A4. 规模、尝试数与预算(冻结)

- 主网格:**50 heat + 50 cool × 4 seeds × {N,R,X}** = 400 triads(1,200 rollouts);校准/headroom 不变;
- 候选槽 k=2/角色/目标 × ≤8 次全局尝试(角色尝试预算 ≤16);**k=2×8glob 被接受,k=2×8/target-exposure 被拒绝**;
- 预算:harvest ≤ 30 A5000·h;全程 ≤ **60 A5000·h 硬顶**(接受);
- 功效文稿:**E-harm 为唯一前瞻功率端点,计划功率 ≈ 76–78%,低于 80%**(删除任何"功率保障"措辞);power artifact v2(`PART_V_POWER.md` 更新)在 harvest 前冻结。

## A5. GPU 前的可行动门槛(冻结)

修订分配器落代码后,先跑**可复现的 cache-consistent 模拟**:10,000 seeds(起始 20260811),**第 5 百分位完成数 ≥ 50(两类型各自,在 p=0.17 敏感性条件下)**。不过门槛 → 不开 GPU,直接 NOT_ESTIMATED。

## A6. 其余全部重申冻结

见表头清单。分析代码 `pilot/external/partv/analyze_gate.py` 已冻结(hash 在 FREEZE_MANIFEST);任何针对池构造的新代码在 harvest 前 commit 并入 manifest(hash 更新入档)。

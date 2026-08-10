# PART V-A Allocator 实现记录 + 可行性门槛裁决（2026-08-10，CPU-only）

> 状态：修订分配器已落代码并入 freeze manifest（$A6）；$A5 可行动门槛已跑完。
> **裁决：FAIL** —— p=0.17（预注册敏感点）下 confirmatory 完成数第 5 百分位
> heat=25、cool=23，远低于门槛 50。按最终性条款建议 Part V 记
> **NOT_ESTIMATED** 并关闭，不再缩减网格、不加尝试数、不放松匹配、不复用源。

## 1. 实现概要（全部为 CPU、确定性、outcome-free）

| 模块 | 内容 |
|---|---|
| `pilot/external/partv/allocator.py` | $A2 源-尝试契约 + $A3 元组约束匹配；ex-ante 角色指定（每 game 至多一个角色）；`SourceAttemptLedger`（每 (candidate,role) 全局 ≤8 尝试、attempt key `candidate\|role\|idx` 绝不重复执行、8 败永久失格、首次成功即合格、角色守卫：源永不得当 target/异角色源）；`match_allocation`（同 obj+同 recep 元组内匹配、容量=min(#targets,#合格R,#合格X)、校准/headroom 在同一次全池分配中先预留、确认池恰取 50+50 否则 NOT_ESTIMATED、一切 tie 按 sha256(canonical path) 升序）；v2 manifest builder |
| `pilot/external/partv/feasibility_sim.py` | $A5 冻结门槛：10,000 draws（seeds 20260811..20270811，逐 seed PCG64），p∈{0.17,0.20,0.30,0.50}；每 (candidate,role) 一次缓存一致的 ≤8 次 Bernoulli 尝试（合格=≤8 内 ≥1 胜，首次胜即停）；向量化计数与 `allocator.match_allocation` 逐 draw 交叉校验一致（M4，绝无理想化变体） |
| `pilot/external/partv/prepare_pools.py` | 新增 Part V-A 替代说明（C1–C5）与 `--build-v2`（委托 allocator）；v1 greedy 代码路径与 v1 `pools_manifest.json` 原样保留（provenance），未做任何行为修改 |
| `pilot/external/partv/freeze_manifest.py` | schema 升级 `partv.freeze.v2`；新模块 hash 入档；被替代语义的旧 hash 以 `superseded` 注记保留可见 |
| `outputs/.../pools_manifest_v2.json` | 分配器输出的 v2 派生状态（targets/candidates/designation stats） |
| `outputs/.../feasibility_gate_report.json` | 门槛完整输出（p × 分布统计 × 两种解读 + 裁决） |

冻结 pin 核验：builder SHA-256 `96ef23ea…` 与 prompt 包字节 `46da398a…`
在 manifest 再生成时复核一致（不符即 STOP，未触发）。

## 2. 冻结前确定的建模/解读选择（无一在见到结果后调整）

contract 未钉死的解读点，实现前一次定死并写入代码 docstring：

- **D1（主解读）** `候选槽 k=2/角色/目标` = 每目标每角色指定**两个完整候选**
  并以"原子 bundle"指定（target+2R+2X）；元组凑不齐整 bundle 的目标不予指定。
  这是 §A4 的平直读法。
- **D2** 匹配按元组汇集合格性（pooling within tuple），容量
  min(#targets,#合格R,#合格X) —— 即 §A3 的"元组约束匹配/流"。
- **D3** 指定顺序：calibration → headroom-A → headroom-B → confirmatory
  （heat/cool 交错各一 bundle，"同一次全池分配中预留"的落地；热先冷后的
  旧贪心正是 §A3 要废除的吞并源）。
- **D4** 指定规模（首跑前冻结）：confirm ≤60/型（沿旧 60 设计的遗产上限，
  实际受供给限制）；calibration 24/型（fill 20，+20% 镜像 50-of-60）；
  headroom 8/型/组（fill 6）。RNG 不进入分配器；目标/候选序=冻结筛查序复用，
  匹配内序=sha256 升序。
- **D5** 尝试 decode seed：`md5(candidate|role|idx)`，idx∈1..8（$3.5.6 字面
  规则的超集；common.py 的 1..4 helper 不动）。
- **M1–M6（模拟模型）** M1 每候选每 draw 只抽一次（缓存一致，与
  `candidate|role|idx` 确定性 seed 规则构造一致）；M2 模拟流与
  rng_screen/rng_rollout 完全分离；M3 首胜即停、尝试数只作预算参考；
  M4 匹配跑的就是真实 matcher 本体；M5 部分槽（partial-slot）宽松解读仅作
  信息性敏感度包络，绝不进入主裁决；M6 契约下元组内无尝试序效应
  （先确立合格性后匹配），故模拟对门槛计数是精确的而非近似的。

## 3. 结构性根因（判定前先可见）

真实 ALFWorld 供给（459 heat + 533 cool）按 (obj,recep) 元组：69 组中
仅 28 组两侧均有 ≥2 局；**双侧元组供给 = 319 heat / 238 cool**。
k=2 全槽语义下每个均衡确认目标消耗自身侧 3 局 + 对侧 2 局；
预留 headroom 后可用于确认的双侧 cool ≈ 190 →
均衡确认目标的**聚合上界 ≤ 38**（3T+2T ≤ 190），再经逐元组碎片化，
分配器实际指定 **28 heat + 26 cool** 确认目标；partial-slot 最宽解读也只有
**32 / 31**。天花板本身（与 p 无关）已低于 50。

## 4. 门槛结果（10,000 draws；计数 = 完成确认 cluster 数；要求两型 5th ≥ 50）

**主解读（allocator k=2 bundles，裁决口径）**

| p | heat 5th | heat med | heat mean(sd) | heat max | cool 5th | cool med | cool mean(sd) | cool max | P(≥50) 两型 | 总尝试数 mean |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.17 | **25.0** | 27 | 26.84 (1.06) | 28 | **23.0** | 25 | 24.93 (1.01) | 26 | 0.0000 | 1714 |
| 0.20 | 26.0 | 28 | 27.41 (0.76) | 28 | 24.0 | 26 | 25.44 (0.73) | 26 | 0.0000 | 1564 |
| 0.30 | 27.0 | 28 | 27.94 (0.25) | 28 | 25.0 | 26 | 25.95 (0.23) | 26 | 0.0000 | 1181 |
| 0.50 | 28.0 | 28 | 28.00 (0.00) | 28 | 26.0 | 26 | 26.00 (0.02) | 26 | 0.0000 | 749 |

max(=指定天花板) 随 p 收敛到 28/26；p=0.17 时 95th 仍仅 28/26。

**敏感度包络（partial slots，仅信息性，不进裁决）**

| p | heat 5th | heat med | cool 5th | cool med | P(≥50) 两型 |
|---|---|---|---|---|---|
| 0.17 | 28.0 | 31 | 26.0 | 29 | 0.0000 |
| 0.20 | 30.0 | 31 | 27.0 | 30 | 0.0000 |
| 0.30 | 31.0 | 32 | 29.0 | 31 | 0.0000 |
| 0.50 | 32.0 | 32 | 31.0 | 31 | 0.0000 |

强制池（calibration 20+20 / headroom 6+6×2）fill 达成率在 p=0.17 下
为 0.9959–0.9998（槽冗余有效），它们不是瓶颈；瓶颈唯一是确认池天花板。

## 5. 门槛裁决（$A5）

- **p = 0.17：heat 5th = 25，cool 5th = 23（要求 ≥ 50）→ FAIL。**
- 两种对 k 槽的解读、四个 p 值均 P(≥50)=0；失败为**结构性**
  （双侧元组 cool 供给 vs k=2 全槽语义），非实现所致，与 §A1 旧设计失败的
  诊断一致。
- 后果：按最终性条款，**Part V 全部端点建议 NOT_ESTIMATED 并关闭**；
  未做任何参数采购（所有常量在首跑前冻结；FAIL 未触发任何调整循环）。
- 治理后续（按治理规则 §1）：自分析（本文档）→ 与 GPT-5.6 讨论 →
  RESEARCH_LEDGER / DECISION 记录；appendix/limitations 须一句话披露
  Part V 未达可估计门槛及原因。

## 6. Freeze manifest 更新确认

`pilot/external/partv/FREEZE_MANIFEST.json`（schema `partv.freeze.v2`）：

- 新增模块 hash：`allocator.py`、`feasibility_sim.py`；变更模块：
  `prepare_pools.py`（docstring + `--build-v2`，v1 行为不变）、
  `freeze_manifest.py` 自身；
- `superseded` 注记保留旧 hash：`prepare_pools.py`
  `805162a2…`（v1 贪心保留语义）、`harvest.py` `1f506e9c…`
  （per-(target,candidate) 暴露账本）、`pools_manifest.json`（v1 文件原样保留）；
- builder `96ef23ea…`、prompt 包 `46da398a…`、protocol、power hash 复核一致；
  analyze_gate.py 未触碰（on 冻结）。

## 7. 悬而未决但与裁决无关的披露项

- `common.CONFIRMATORY_PER_TYPE = 60` 与 `analyze_gate.py` 的分层口径
  (60/60) 对应的是修正案前网格；若门槛通过，收割前需一项小修正把分析
  对齐到 50+50。**门槛 FAIL 后该事项失效**（无分析可跑），如实记录。
- `grid.py` docstring 的 "confirmatory-heat(60)+cool(60)" 字样同上，未改；
  harvest.py 的 v1 收割循环被契约账本替代（文件未动，hash 注记）。

## 8. 复算入口（全部 CPU）

```bash
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
export ALFWORLD_DATA=/work1/zixuan/data/agent_memory/alfworld
$PY -m pilot.external.partv.allocator --self-test        # 契约账本+匹配器
$PY -m pilot.external.partv.feasibility_sim --self-test  # 模拟/交叉校验
$PY -m pilot.external.partv.prepare_pools --build-v2     # v2 manifest
$PY -m pilot.external.partv.feasibility_sim --run        # 10,000-draw 门槛
$PY -m pilot.external.partv.freeze_manifest              # pin 核验+hash 入档
```

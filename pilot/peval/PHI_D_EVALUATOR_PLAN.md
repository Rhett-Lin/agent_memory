# φ+d P-估计评估器设计方案(v1,经 GPT-5.6 裁决修正)

> **状态:设计定稿(2026-08-09),GPT-5.6 裁决 GO with mandatory amendments(thread `019fe66c-7bb5-7560-bfb4-d8b787d4e5a5`),修正案已全部并入。性质:工程工具 +「inference not lookup」claim 的验证件,不是新论文贡献。动机:部署态不存在 P×S 正交真值,sealed oracle 只用于离线训练/评测。**

## 0. 已注册证据(同 640 对,这条线不得绕开)

- sim → P:AUC 0.606(全)/ 0.529(S=1 内 A11-vs-A01);
- vanilla LLM 整体等价判定(7B):判错率 100%;STITCH intent judge:0.508;
- 指纹判别器 P̂ v1:族 CV 0.966/0.935;**LOAO 0.636/0.590**(留一族即崩,conditional_write 0.408);
- **早期分解式 CoT 判定(`pilot/audit/results/equivalence.json`):16 对样本一致率仅 25%,A10 0%,A01 50%**——分解本身不等于修好;
- G-struct(ALFWorld 手工比较器):零学习、零泛化声称,构造检测近乎满分。

## 1. 架构(裁决定稿)

```
surface top-k 检索(不变)→ 两侧独立 φ 抽取(各自唯一文本缓存)
    → 确定性比较 d(φ(x), φ(m)):硬否决 → 评分/rerank → admit / abstain
```

- **两阶段容器**:比较器不是替代检索,而是嵌在 retrieval 之后的 admission 层;评估 top-1 admit/abstain 与固定 top-k rerank 两种策略。
- **抽取独立化**:x 与 m 各自单独抽取(杜绝 pair-conditioned 合理化);同一文本只抽一次并缓存:640 对 ≈ 160 唯一 instruction + 640 唯一 memory ≈ **800 次抽取**。
- 找不到结构 → abstain(绝不丢样本、绝不当 match)。

## 2. IR(中间表示)设计要点

- **角色归一(canonical roles)**:实体一律 α-renaming 到角色词表(`subject_row / policy_row / source / destination / child_set / audit_sink`…),因为 A10 跨域对实体名本就不同——按原名比会把真等价错杀。示意图中 "custoncil"→ child_set。
- **程序图而非线性序列**:typed op 节点 + read/write 依赖 + branch predicate/effect + 允许的顺序交换(独立写可对易)。
- **ABSENT ≠ UNKNOWN**:完整程序缺少应有操作 = contradiction(主动缺失);抽取含糊 = unknown → abstain。混在一起会漏掉 skip_archive 型 near-miss 或摧毁覆盖率。
- 每字段必须挂 **evidence span**(原文出处),供盲审。

## 3. 比较器(冻结规则集)

- **矛盾一票否决(non-compensatory)**:polarity/方向/child predicate/必需操作缺失,任一冲突 → contradict,禁止用分数补偿;
- 硬检查过后才有分数(连续 S 对齐度等),分数仅用于同 verdict 内 rerank;
- output:`{match, contradict, unknown}` × bounded score;uncalibrated 三值判定永远保留供审计;Platt 校准仅 secondary,且只能在外层训练折内拟合。
- 规则集的每一个条款必须**在跑分前冻结并 hash**(§6 清单),条款措辞只允许指向通用语义约束,禁止塞 benchmark 例子。

## 4. 分解式判定基线(固定诊断项,含入方案)

同一模型、同一解码设定,在全部 640 对上输出同一组原子字段 + `{match, contradict, unknown}`。只作 ablation,**不许用它的错误指导比较器迭代**:
- φ+d 成而分解判败 → 确定性语义在做功;
- 两者同字段同时败 → 瓶颈在抽取不在比较。

## 5. 评估协议(冻结口径)

- 主指标:**macro-avg of 4 个 held-out archetype 的 S=1 AUC**(不 pooled;v1 的 pooled 0.590 与 per-archetype 均值 0.647 不可比)。
- 不确定性:family-cluster bootstrap。
- 必报:cell 分列决策率、risk–coverage 曲线、**S=0 AUC 与 A10 保留率**(防止"只会抓明示 near-miss,却杀掉跨域真等价")、invalid→abstain 占比。
- 部署策略评估:复用既有 7B/3B rollout,对比 always-admit / never-admit / sim-gate / P̂ v1 / φ+d(top-1 与 top-k)/ oracle-P,family-cluster bootstrap。

## 6. 成功门(冻结,多门并列)

1. **迁移门**:macro ΔAUC(φ+d − v1)≥ +0.10,且 family-cluster bootstrap 95% LB > 0;
2. **灾难门**:无任何留出 archetype AUC ≤ 0.5,且最差 archetype ≥ 冻结下限(实现首日写值);
3. **准入门**:A01 接受率 ≤ α=0.10 且 A11 保留率 ≥ c=0.50,**整体且逐 archetype 同时满足**;
4. **跨表面门**:S=0 AUC 与 A10 保留率如实上报(不设死值,但与门 3 联合解释);
5. **策略门**:φ+d 策略 uplift 显著 > sim-gate 且不劣于 oracle-P 5pp(沿用 Part IV 式非劣口径)。

## 7. 诚实等级(裁决要点,写作时必须遵守)

- 这是 **locked evaluation**,不是严格预注册:标签与四种翻转机制设计者已知。AC 结果只能表述为"对已注册构造的覆盖",不能表述为"对未见机制的迁移";
- 真·未见迁移检验:规则冻结后,构造**第五种文本失配型 challenge set**(不需要新 rollout)再测;
- **可辩护声明(裁决原文锚)**:"在固定 CausalMemAgent benchmark 候选池上,冻结的结构化 parser-comparator 能以预设风险与覆盖率支持选择性 memory 准入,跨四个注册 archetype 与两域。"不声称任意部署泛化、不声称隐式指令场景、不声称未见失配机制;frontier 模型零样本若成功,不构成对 "inference not lookup" 的反驳(它本身即在做 inference),7B 失败的措辞限定到部署模型与所用 prompt。

## 8. 冻结清单(实现前必须 hash 入档)

输入(对文件 hash、字段白名单、排除 cell/P/S/family 元信息)| 抽取器(模型 revision、prompt 全文、解码参数、JSON schema、重试策略、失败→abstain)| IR 语义(角色词表、op 代数、依赖/可交换规则、谓词表示、严格/非严格算子、否定归一、source/destination 绑定、聚合目标、branch effect、终止、ABSENT/UNKNOWN)| 等价关系(允许的 α-renaming、良性安全附加项、完备性、对齐与 tie-break、矛盾真值表)| 分数与决策(否决字段、权重、coverage、阈值、top-k、fallback)| 校准(是否、组内内层折、degenerate fold 处理)| 评估(主指标、bootstrap 规程、cell 指标、风险覆盖目标、缺失处理、基线、成功/失败规则)| 机制审计(抽样规则:A11→A01 差异应定位到注册语义字段;A10/A11 应归一到兼容程序签名)| 复现(代码/配置/prompt hash、版本、token 账本、事后改动一律标 dev 版本)。

## 9. 阶段与成本

| 阶段 | 内容 | 成本 |
|---|---|---|
| S0 spec-freeze | 写全 §8 清单 + hash(commit) | 0.5 天,CPU |
| S1 φ 抽取 | 800 次抽取(Qwen-7B vllm,单卡) + 缓存 + JSON 校验重试 | ~1–2h GPU |
| S2 比较器 | 规则实现(纯 Python),人工规则**先冻结后跑分** | 0.5–1 天,CPU |
| S3 评测 | 640 对 × 门 1–4 + 分解判基线(再 640 次抽取) | 几小时,1 GPU |
| S4 策略评估 | 复用 GATE_EVAL 管线,门 5 | ~1h,CPU |
| S5(可选) | 第五种失配 challenge set | 无 rollout,构造+重跑评估 |

与 Part V 的关系:独立、可并行准备;GPU 只占 1 卡几小时,不与 Part V 的 harvest/网格冲突。G-struct 保留为 Part V 内 ALFWorld 专用版,φ+d 是其可泛化对应物。

## 10. 已知失败模式与缓解(裁决 top-3)

1. **表面锚定/有损抽取**(7B 输出域名实体、偷偷归一错 polarity、幻觉缺操作)→ 角色归一 IR + 每字段 evidence span + ABSENT/UNKNOWN + 盲审(对照 generator signature/params);
2. **人写规则成为第二代指纹**(设计者见过四种翻转)→ 规则先冻结后跑分 + 措辞限通用语义 + 表述限"已注册构造覆盖",真迁移靠第五构造 challenge;
3. **AUC 掩盖不安全准入**(高 AUC 可能仍放 20% A01 或杀光 A10)→ cell 分列 + risk-coverage + 逐 archetype 准入门 + 端到端策略门,invalid 一律 abstain 计数。

---

*参考裁决:Codex thread 019fe66c-7bb5-7560-bfb4-d8b787d4e5a5(gpt-5.6-sol,xhigh)。台账记录见 RESEARCH_LEDGER 外部讨论记录。*

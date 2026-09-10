# NEC 复现缺口与实现来源

审计日期：2026-09-09。实现版本：`0.1.0`。正式结果应使用完整名称 `NetEventCause-ODE-reimpl-Device-prior-calibrated-adapt`，不能省略适配后宣称为原作者完整复现。

## 核准的来源

- 原论文：Zhaolin Yuan 等，*NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topology*，IEEE TNNLS 36(10), 2025，DOI [10.1109/TNNLS.2025.3574316](https://doi.org/10.1109/TNNLS.2025.3574316)。使用仓库 `docs/papers/NetEventCause_ Event-Driven Root Cause Analysis for Large Network System Without Topology.txt`，§IV-A–D / Eq. (1)–(13) / Algorithm 1–2。
- 作者仓库：[yuanzhaolin/NetEventCause](https://github.com/yuanzhaolin/NetEventCause)，本地快照 `Baseline/NetEventCause/NetEventCause-main/`。本地快照缺少独立 git 修订记录，故锁定文件内容哈希，不伪造 commit。
- 本实现没有复制或调用作者 toy 因果规则。原 `Baseline/NetEventCause/NECAnalyzer.py` Hawkes 实现保留不变。

| 审计文件 | SHA-256 |
|---|---|
| 本地论文全文 | `4AD1B56672A2EF2AD318D2A4A191FD7130FD7C1F9B66B0D901723E78025D17FF` |
| 作者 README.md | `2E9EA5CBA421A99DF23C79777C65DB0C3218C8185ECEE23D4EAE7921A1341B67` |
| 作者 detect/attribution_rca.py | `F52306297C8EF4F70A895B50D798FBB90EA1631011643D4F728FFC9FCA5537F0` |
| 作者 cause/event/pkg/temp/ode_rnn.py | `7B35FFAEF9E3E7D00BE8002B9BF792C3521D6CE2376260D06279DC78A0E2828A` |

## 作者发布实现的障碍

README 明示部分源代码因保密协议被替换。训练及归因脚本引用的 `models/ode_rnn.py` 和 `models/spnpp.py` 缺失；toy 脚本默认 ERPP。另在 `pkg/temp/ode_rnn.py` 找到实验草稿，但其构造签名、线性层参数等有明显错误且不提供完整可运行 ODE 机制，不能当作缺失核心已补齐。

`detect/attribution_rca.py` 包含 `cause_score_modify`：将分数抬至至少 0.01，再按编号 0–4 写死候选类型；还有未知类型直接赋根概率 1 的逻辑。正式数据不会走这条调用链。

## 当前机制及明确偏离

1. **结构保留**：学习事件嵌入 V、连续隐藏态神经 ODE、GRU 事件跳变、query 与 phi(V) 点积得到对数强度；因果历史只含预测时可观察的严格过去。
2. **求解器**：使用完全可微固定步长 RK4，联合求解隐藏态与总强度积分。论文实验使用自适应 Dormand–Prince。当前有解析解收敛测试，但不能据此声称两实现数值等价。超每区间 ODE 步数预算明确报错，不偷偷加大步长。
3. **区间边界**：每事故采用公共 start/cutoff、空历史初始化，NLL 积分包含整个窗口（含末事件后的无事件尾区间）。论文 Eq. (3) 按序列相邻事件区间书写；显式观察截止时刻需要尾区间。此前历史缺失构成左截断，未加入伪造前史。
4. **正则**：零历史是零输入嵌入，不是直接跳过 GRU；事件时刻不变。Eq. (12) 对事件及全部类型的平方误差求和，训练默认权重 1，与 NLL 相加。训练报告分别保存 NLL 与正则。
5. **监督**：没有可核验事件级根告警标签，采用任务书允许的固定 rho 工程先验，默认 0.1。其数值只使用训练事件数与总观察时长，既不使用设备根标签，也不使用测试词频。不宣称它是 Eq. (7) 的人工标注先验估计。今后额外事件监督版必须另名另记协议。
6. **阈值与归因**：根阈值 0.2 取自论文 Algorithm 2，未采用公开检测脚本 0.5。目标为 log intensity；IG 基线与空历史正则一致，保留原始 signed contribution。原因候选仅保留严格正贡献，再取 Top-K；这是对抑制关系的明确工程处理，不能解释为论文规定的唯一方式。
7. **未知类型**：训练词表外组合为 UNK，输入零嵌入，时间仍可影响历史的状态演化；本事件不评分。没有未知类型自动根概率 1，也没有把测试类型加入词表。UNK 输出通道仍进入似然总强度且先验为零。
8. **同时性**：同时间事件在更新隐藏态前同时计强度，不互相归因；之后按 event_id 顺序做 GRU 跳变。此顺序可能影响之后的强度，尚未完成所有并列事件置换敏感性实验。无需随机抖动、设备 ID 定方向或人为补传播顺序。
9. **根比值**：保留原始 `mu/lambda`，大于 1 时记录模型/先验不匹配。没有剪裁成伪概率。无正向归因的衍生事件仍保持衍生判定并记录原因，不擅自改成根。
10. **设备映射**：设备 score 是其可评分事件分数的最大值；静默/不可评分设备保留 null 排名。原始事件图允许 A→B→A 的不同事件关系；设备折叠可能成环，必须由 A0 公共适配器记录并处理。物理拓扑不是该模型的输入特征。
11. **模型规模与训练**：默认 32 隐藏维、16 事件嵌入维、30 epoch、Adam、固定种子、梯度裁剪属于本项目冻结候选配置；不是从缺失作者权重反推的设置。训练只做 NLL/正则优化，验证只按 NLL 选择 epoch。
12. **覆盖与时间**：告警/日志输入不能补齐缺失 KPI、记录时间或覆盖信息。缺少记录时间会被显式计数；当前可见告警流不代表全量真实事件。CPU 上逐事件 IG 为二次历史开销，未给出大规模时延承诺。

## 交付状态

- 可执行：Python API、独立 CLI、训练检查点、原生事件图与设备根排序；公共适配、分组和评测由 A0 提供。
- 已做：本目录模型的解析积分/梯度、IG 完整性、事件时间方向、标签隔离、训练下降和 checkpoint 验收。
- 未做：作者完整程序等价性、作者 IMOC/合成数据 benchmark 数字、真实故障数据的多折 Root/Graph 质量实验、NPU/GPU 运行与大规模性能验证。
- 没有生成或报告真实数据准确率。训练的数值下降与合成机制测试只证明实现可执行并符合这些检查，不证明已学得可泛化的网络传播机制。

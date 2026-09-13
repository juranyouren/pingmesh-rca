# www24-inart — InArt: In-Network Aggregation with Route Selection for Accelerating Distributed Training

| 字段 | 值 |
| --- | --- |
| 年份 / 轨道 | 2024 / WWW Research Track |
| 正式题名 | InArt: In-Network Aggregation with Route Selection for Accelerating Distributed Training |
| DOI | 10.1145/3589334.3645394 |
| 原始 PDF | www24-inart.pdf（来源：作者主页副本 fangjin.site；版本：WWW '24 camera-ready，11 页，与 ACM Reference Format 所述 "11 pages" 一致；本地元数据未记录精确 URL） |
| 抽取文本 | tmp/www-web-relevance/txt/www24-inart.txt |
| Introduction 定位 | www24-inart.intro.md，PDF 第 1–2 页，P1–P15（P15 实为贡献 bullet 的末行，非独立段落） |
| 深读状态 | 已深读（含 §2–§6、附录 A.1/A.2/B、参考文献页）。注意：抽取文本中部分子节标题错位或缺行（§2.1、§3.1、§4.1、§4.3 标题未被抽出），正文对 §2.1 有交叉引用，但抽取文本将第 2 节整体标为 "2 MOTIVATION"。 |

## 1. 问题定义

研究对象是数据中心内**多参数服务器（multi-PS）架构下的分布式训练（DT）通信瓶颈**，具体问题是"带路由选择的网内聚合（INA）"（§1 贡献 1，PDF p.2；Abstract，PDF p.1）。（【作者陈述】）

- **输入**：DT 集群图 G=(W,S,V,E)（worker 集、PS 集、可编程交换机集、链路集）；每台交换机的总/已用处理能力 C(v),c(v)；每个 PS 的总/已用入口带宽 B(s),b(s)；每条链路的总/已用带宽 B(e),b(e)；各节点对的可行路径集合 P（§3 PROBLEM DEFINITION，PDF p.3，Table 1 为记号表）。
- **输出**：三组决策——(a) 每个 PS 负责的模型比例 x_s；(b) 每条梯度分片在何处聚合（PS 上或某台交换机上，变量 y）；(c) 每条梯度分片走哪条路径 q（§3.2，PDF p.3–4）。
- **目标**：最大化 worker 的梯度发送速率 f，形式化为 Eq.(1)（§3.2，PDF p.4）。
- **使用者／受益者**：作者声称受益者是运行 DL 训练作业的 web 基础设施运营方（【作者陈述】，P1，PDF p.1）。但论文实际能支持的受益者范围窄得多：**单一 DT 作业**、同步 SGD、由中心控制器预计算并下发 P4 流表（【本次推断】）。全文没有任何运维人员、服务方或用户侧参与，也没有真实生产集群。

## 2. Web 关联

Web 关联只出现在 Introduction 的两处，均为**领域命名/背景数据级**：

- P1（PDF p.1）："deep learning has become an essential component of many web applications"，列举电商 [13]、社交媒体 [14]、在线广告 [43]，并把 DT 称为 "widespread in web infrastructure"。（【作者陈述】）
- P3（PDF p.2）："DL models employed in web applications often possess a substantial number of parameters"（以 BERT 为例）。（【作者陈述】）
- 关键词表列出 "Web Infrastructure"；但 CCS Concepts 只有 Networks 下的 In-network processing 与 Computing methodologies 下的 Machine learning（PDF p.1），**没有任何 Web 相关 CCS 分类**。
- 评价部分（§5，PDF p.6–8；附录 A，PDF p.10）**完全没有** Web 请求、服务依赖、微服务、SLO、用户侧时延等任何 Web 指标。全部负载是 Cifar-10 上的 ResNet50/VGG19（testbed）与 LSTM/VGG19/ResNet-50（仿真）。

**2026-09-12 T006-R 更正（验收 R1，覆盖本节原判）**：本节原有"这是一个 venue-driven
（会议驱动）的 Web 关联，不是实质关联"一句，**判断过强，已撤回**。
- 把 Web 术语替换掉论证仍成立，说明的是**适用范围**（该链不限于 Web），
  **不能**据此判定"没有实质联系"。
- 准确的表述：**Web 进入了动机层并支撑了通信瓶颈的前提**（P3 再次点名 Web 应用所用模型的规模），
  **没有进入问题设定、方法与评价**；实验负载与引言点名的行业不对应。

**去掉 Web 术语后，论文的技术主张完全成立**——把"web applications"换成"AI 应用"、
把"web infrastructure"换成"训练集群"，全文论证不变。（【本次推断】）

## 3. 段落作用

以下段落功能判定均为【本次推断】（依据各段实际承担的论证角色）：

- **P1**：背景 + 重要性。DL→web 应用→训练成本高→DT 是必需的基础设施。功能是**把训练效率挂到 Web 价值链上**，为后续的纯网络优化争取合法性。
- **P2**：背景机制。介绍 PS 架构与 gradient computation / gradient aggregation 两阶段。为 P3 的瓶颈论证铺垫。
- **P3**：缺口证据。硬件加速使瓶颈从计算转向通信，引用 BERT 具体数字（110M 参数、10Gbps 链路下通信占一半以上），并再次绑定 web applications。
- **P4**：现有路线批评 + 新工具引入。指出梯度压缩损害精度、通信调度不减少流量；引出可编程网络硬件与 INA。
- **P5**：对 INA 现有工作的**具体批评**（SwitchML 单 rack 规模；ATP 跨 rack 多租户但仍单 PS；GRID 只选聚合点）→ 核心缺口：INA 单独无法解决 PS 入口带宽瓶颈。
- **P6**：洞察 + 挑战 + 贡献预告。multi-PS 与 INA 互补互益；列出三个非平凡挑战（路由目的地不确定、INA 使转发流量大小可变、多维资源约束）。同一段内既做洞察又做挑战陈述，未分开。
- **P7–P15**：贡献 bullet 列表（抽取工具把换行当成了独立段）。三条贡献：multi-PS 下 INA + 路由选择（自称 first-of-its-kind）、两阶段算法（L-InArt / R-InArt）、双平台实现与实验。

## 4. 现有工作与缺口

作者实际批评的内容（【作者陈述】，P4–P5，PDF p.2）：

1. 梯度压缩 [10,11,15] "will inevitably lead to training accuracy degradation"。
2. 通信调度 [24,28,41] "does not reduce the traffic volume"，链路/PS 上仍可能遭遇瓶颈。
3. SwitchML [37] 只在**单 rack 规模**做 ToR 交换机聚合。
4. ATP [29] 支持跨 rack 多租户 INA，但**仍在传统单 PS 架构**下。
5. GRID [20] 只解决"为每个 worker 选聚合点"，不解决 PS 入口带宽。

缺口推导方式：前三项指出通用替代路线不可行，后两项指出同类 INA 工作共享同一个未被触碰的前提（单 PS）。因为训练规模扩大时单个 PS 的**入口带宽**无法支撑参数同步，所以"INA 本身不够"。由此推出本方法：**multi-PS 切分 + 路由选择**必须联合求解；而联合求解又因为路由目的地不确定、流量大小可变、多维资源约束，落成 NP-hard 的 NMIP（§3.2，PDF p.4），所以需要两阶段分解（§4，PDF p.4）。

## 5. 核心洞察与贡献

以下分类为【本次推断】；括号内为论文自述的出处。

- **任务定义贡献【作者陈述】**：首次把 INA 与路由选择放入 multi-PS 架构（Abstract / §1 贡献 1 / §6，PDF p.1–2、p.8）。这是论文的**主要自我定位**，也是"新颖性"的全部来源。
- **方法贡献【作者陈述】**：两阶段分解——L-InArt（广义拉格朗日乘子 + KKT + 高斯消元求 x_s，§4.2 / Alg.1 / Eq.2–4，PDF p.4–5）与 R-InArt（线性规划松弛 + 随机舍入，§4.3 / Alg.2 / Eq.5，PDF p.5–6）。其中 LP 松弛解被明确声明为原问题的**上界**（§4.3，PDF p.6）。
- **系统实现贡献【作者陈述】**：Tofino 硬件 testbed（P4-16/TNA，BRI 下发流表）与 bmv2 软件仿真（§5.2.1，PDF p.6；§5.3.1，PDF p.7）。
- **工程规模贡献【本次推断】：弱**。硬件 testbed 仅 8 台服务器 + 2 台 Wedge100BF-32x，拓扑**照抄 §2 的玩具例子 Fig.1**（2 PS / 6 worker / 2 switch）。仿真 fat-tree 也只有 9 core + 18 agg + 18 ToR + 54 servers，且流量缩小 1000 倍（§5.3.1）。
- **评价贡献【本次推断】：弱**。无新数据集、无新 benchmark；评价只有 3 个 baseline（等分模型 + R-InArt、LBMM、ATP），且都需作者为其补假设（§5.1.2，PDF p.6）。

**真正的立身之本**是"任务定义 + 两阶段算法"这一组合；实现与实验是支撑材料。作者在附录 B 末段（PDF p.11）自述："the primary contribution of this paper lies in presenting the problem of INA with route selection in multi-PS architectures and designing two algorithms for solving this problem, and the P4 implementation of InArt is similar to that of existing works, **relevant evaluation has been omitted**"——这是作者**主动承认实现层评估被省略**，与 §5.2 / §5.3 中大量实现细节形成张力。（【作者陈述】）

## 6. 证据强度

**摘要中 48%~57% 的通信时间下降**：由 §5.3.2 与 Fig. 10（PDF p.8）支撑——异构场景下 10/20/30/40/50 workers 分别降低 48%/54%/57%/53%/49%。来源是 **Mininet + bmv2 仿真**，且实验设置明确 "shrink the experimental setup by a factor of 1000"（§5.3.1，PDF p.7）。摘要未披露该折算。（【实验支持】+【本次推断：摘要未披露折算条件】）

其他数字及其归属：

| 声明 | 出处 | 类型 |
| --- | --- | --- |
| Fig.1 算例：LBMM 4/3、ATP 2、InArt 2.5 | §2 + Fig.1，PDF p.2–3 | 【作者陈述】构造性算例（非实测数据） |
| 6 workers VGG19：InArt 26.2Gbps vs ATP 19.25 / LBMM 15.4 | §5.2.2 + Fig.2，PDF p.6–7 | 【实验支持】硬件 testbed 实测 |
| 每迭代时间 0.69s vs 0.85s(ATP) | §5.2.2 + Fig.4，PDF p.7 | 【实验支持】testbed 实测 |
| 通信用时 0.31s vs 0.45s(ATP) | §5.2.2 + Fig.5，PDF p.7 | 【实验支持】testbed 实测 |
| 2000 迭代 1380s vs 1775s(ATP) | §5.2.2 + Fig.6，PDF p.7 | 【实验支持】testbed 实测 |
| 达目标精度快 1.2×/1.38×/1.84× | 附录 A.1.1 + Fig.11，PDF p.10 | 【实验支持】testbed 实测 |
| 发送速率随 PS 数 2.37× 提升 | 附录 A.2.1 + Fig.12，PDF p.10 | 【实验支持】仿真（1000× 缩小） |
| 网络吞吐约 1.6× | §5.3.2 第三组 + 附录 A.2.2 + Fig.13，PDF p.8、p.10 | 【实验支持】仿真（1000× 缩小） |
| PS 负载降低 53% | 附录 A.2.3 + Fig.14，PDF p.10 | 【实验支持】仿真（1000× 缩小） |

**只是动机陈述或推断的部分**：

- P6 "multi-PS 架构和 INA 是互补互利的两种方法，可以有效缓解通信瓶颈"——作者陈述，指向 §5，但 §5 中并没有分离出"multi-PS 单独"与"INA 单独"的消融，因此该"互补性"论断没有被独立证实。（【本次推断】）
- Abstract / §1 的 "first work / first-of-its-kind" 是新颖性声明，不可由实验检验。
- multi-DT job 场景（附录 B 首段，PDF p.10）只是"可顺序处理其他 job 视作背景流量"的论述，**无实验**；而 §3 正文明确说"For simplicity, we focus on accelerating the training time of a single DT job"。
- 附录 B 末段（PDF p.11）承认 INA 会带来精度损失，并给出 LSTM/VGG19/ResNet50 的 1.54%/1.60%/1.05%。原文紧接引用 [37]（SwitchML），措辞含糊，**未能判定这三个数字是本文实测还是引自 [37]**（未找到明确归属说明）。

**"只测了 X 却声称 Y"的具体风险点**：

1. 摘要的 48–57% 宣传数字来自缩小 1000 倍的软件仿真，而非硬件 testbed；testbed 与仿真给出的量级完全不同（Gbps vs Mbps），摘要未区分。
2. 核心动机是"大规模集群下 PS 入口带宽瓶颈"，但硬件 testbed 上限仅 6 workers / 2 PS，规模与动机不匹配。
3. 大量结果以 "due to space limitations" 推到附录（§5.2.2 精度、§5.3.2 第三组、§4.2 模型切分细节、§4.3 RR 细节），正文只给一句结论式断言。
4. 模型切分被作者自述"不可在训练中频繁修改"（§4 首段，PDF p.4），因此"适应流量动态"的能力实际只属于第二阶段的路由更新；两阶段标题对读者有过度概括之嫌。（【本次推断】）

## 7. 与本项目（RPG-Recon）的关系

### 可借鉴的论证步骤

1. **"领域需求 → 受限优化问题 → NP-hard → 可分解近似算法"**（§3→§4）。InArt 把工程直觉写成一个带六类约束的 NMIP（Eq.1），再论证其非线性混合整数性、引 NP-hard，然后用松弛 + KKT / 舍入求解。RPG-Recon 的对应链条是"事件传播 DAG 重建 → 受限 DAG 选择 → 组合难度 → 条件化两阶段组装"；InArt 提醒我们把这个链条**显式写出来**，而不是只描述流程。
2. **玩具算例作为论证锚点**（§2 + Fig.1，PDF p.2–3）：2 PS + 6 workers + 2 switches，容量 6/4/6，三个数字 4/3（LBMM）、2（ATP）、2.5（InArt）并排。这个小算例完全可复算，比任何大规模图都便于 reviewer 复核。我们在 P0 与 baseline 对比中可以低成本复用这一动作：同一份输入、三种方法的输出 DAG 并排。
3. **两阶段"慢变量 / 快变量"分离**（§4 首段）：模型切分按小时级更新，路由按拥塞事件更新。这与我们"Top-K root 排序（相对稳定）+ root 条件图组装"的分解在**结构上同构**，但注意差异：InArt 的第二阶段是同一目标函数在固定 x_s 后的精确松弛，具有上界保证；我们的条件组装不是同一目标的松弛，而是引入了更强的建模限制。
4. **明确声明松弛上界**（§4.3，PDF p.6：LP 松弛解是 Eq.(1) 的上界）。对照：我们的 P0 解码器**不保证全局最优**（项目 CLAUDE.md 已写）。InArt 提示我们可以主动给出一条上界或近似比论证，或明确标注为启发式——我们现在选的是后者。

### 不能迁移的前提

- **InArt 的收益函数是可测、可解析、可直接优化的**（梯度发送速率 f）。RPG-Recon 的输出价值是"工程师诊断效率"，**没有对应的可测代理目标**，因此不能套用"优化目标 → 数值收益"的论证模板。
- **InArt 需要可编程数据面才能兑现**（Tofino + P4 流表下发）。我们是离线/近线分析，数据是 Pingmesh 异常 + 原始拓扑 + 部分告警/日志，不控制任何转发行为。
- **InArt 从未接触真实 Web 服务或生产集群**：它的全部实验是 Cifar-10 训练 + Mininet 合成流量 + 一个照抄玩具例的 8 机 testbed。也就是说，**它发表 WWW 时并不需要生产部署数据、真实服务依赖或实测运维收益**。这与我们的约束形成直接对照：我们被明确禁止编造生产案例、手工处置动作或 SLO/MTTR 收益，而 InArt 根本不需要这类数据——它只需要一个可信的仿真/小 testbed 与一个可形式化的问题。**这是本卡片最有信息量的一条可迁移性判断**。（【本次推断】）
- 但反过来，InArt 也因此把代理指标（发送速率、通信用时）**直接当成收益**，没有验证"使用者是否感知到改善"。RPG-Recon 若要做 Web 定位，这条捷径不可用——我们的评审压力恰恰在"诊断价值是否被验证"。
- 评价条件不可迁移：InArt 有 3 个可比的 baseline 与两个可复现平台；RPG-Recon 的 baseline 适配（SkyNetVoting / BiAnAdapt / NEC / PCMCI+ / DYNOTEARS）与图指标协议仍在统一中。

### 潜在重合与差异

- "松弛 + 舍入/投影"的算法形态与我们 P0 的"局部方向支撑 + 路径选择"相近：都是把一般 DAG 搜索退化为一个可解结构。**差异**：InArt 的退化有最优性上界，我们的退化（严格递增最短跳距离规则）是更强的建模限制，可能排除标注边——这是必须主动披露的，而不是像 InArt 那样把局限放进附录。
- "多 PS"与"多 root（Top-K）"表面相似（都是"目的地不确定"），但**不确定性性质根本不同**：InArt 的不确定是决策变量的不确定，优化后即消失；RPG-Recon 的 root 不确定是**数据固有缺失**，只能排序 + 条件组装，不能"解出来"。把 InArt 的"解出即正确"叙事搬到我们的 root 不确定性上会是实质性误导。

## 8. Reviewer 视角

（本节为【本次推断】的评审判断，非论文陈述。）

- **去掉 Web 术语后论证完全成立**，甚至更顺——它本质上是一篇数据中心网络 / NSDI 风格的系统论文，被放进 WWW 的 "Web Infrastructure" 关键词下。Web 关联是 venue-driven。
- **最可能被质疑的缺口**：(i) 48–57% 的核心卖点来自 1000× 缩小的 bmv2 仿真而非硬件 testbed，摘要未披露；(ii) 硬件 testbed 规模（6 workers / 2 PS）不足以支撑"大规模集群 PS 入口带宽瓶颈"的动机；(iii) INA 自身精度损失用"可接受"一笔带过，归属含糊；(iv) "multi-PS 与 INA 互补"没有消融；(v) 模型切分不可频繁变更，削弱"适应流量动态"的覆盖范围；(vi) 作者自承 P4 实现评估被省略，而"首次实现"是贡献之一。
- **值得我们避免的做法**：
  1. 摘要报最优数字而不披露其评估条件（仿真 vs 实测、缩放倍数）。我们的 CLAUDE.md 已要求每个指标附分母与评估条件——InArt 正是一个反面教材。
  2. 把动机陈述（"两种方法互补互利"）写成已验证结论。
  3. 用 "due to space limitations" 把关键实验细节整体推入附录，正文只留结论句。
  4. 把 "first-of-its-kind" 当作贡献条目——这类声明不可检验，且一旦已有工作被找出即成为软肋。
- **值得学习的做法**：用一个完全可复算的小算例承载核心论证；用两阶段分解来正当化"不频繁改动慢变量"的工程妥协。

## 9. 原文定位索引

| 内容 | 位置 |
| --- | --- |
| Web/电商/社交媒体/在线广告背景（P1） | §1，PDF p.1 |
| BERT 参数与通信占比（P3） | §1，PDF p.2 |
| 对梯度压缩/通信调度的批评（P4） | §1，PDF p.2 |
| 对 SwitchML / ATP / GRID 的具体批评（P5） | §1，PDF p.2 |
| multi-PS 洞察 + 三个挑战（P6） | §1，PDF p.2 |
| 三条贡献 bullet | §1，PDF p.2 |
| 玩具算例 Fig.1（4/3、2、2.5） | §2 + Fig.1，PDF p.2–3 |
| 系统模型、记号 Table 1、六类约束、Eq.(1)、NP-hard | §3 / §3.2，PDF p.3–4 |
| 两阶段动机（切分不频繁、路由随事件更新） | §4 首段，PDF p.4 |
| L-InArt（Alg.1、Eq.2–4、KKT、高斯消元） | §4.2，PDF p.4–5 |
| R-InArt（Alg.2、Eq.5、LP 上界） | §4.3，PDF p.5–6 |
| 八个评价指标 | §5.1.1，PDF p.6 |
| 三个 benchmark（等分+R-InArt / LBMM / ATP） | §5.1.2，PDF p.6 |
| Testbed 设置（8 服务器、2×Wedge100BF-32x Tofino、100Gbps、Cifar-10、ResNet50 97MB / VGG19 548MB） | §5.2.1，PDF p.6 |
| Testbed 结果（Figs.2–6，Gbps 量级） | §5.2.2，PDF p.6–7 |
| 仿真设置（Mininet fat-tree 9/18/18/54、4 PS、缩小 1000×、20Mbps 及 10–30Mbps、PS 20Mbps、交换机 9Mbps） | §5.3.1，PDF p.7 |
| 仿真结果（Figs.7–10；Fig.10 的 48/54/57/53/49%） | §5.3.2，PDF p.7–8 |
| PS 负载降 53% 的正文断言 | §5.3.2 第三组，PDF p.8 |
| 结论与未来工作（异步 DT） | §6，PDF p.8 |
| 精度实验 Fig.11（1.2×/1.38×/1.84×） | 附录 A.1.1，PDF p.10 |
| 发送速率 vs PS 数 Fig.12（2.37×） | 附录 A.2.1，PDF p.10 |
| 网络吞吐 Fig.13（1.6×） | 附录 A.2.2，PDF p.10 |
| PS 入流量 Fig.14（53%） | 附录 A.2.3，PDF p.10 |
| multi-DT job 可扩展性论述（无实验） | 附录 B 首段，PDF p.10 |
| 模型切分细节 + VGG16 算例 | 附录 B.2，PDF p.11 |
| RR 舍入细节算例 | 附录 B.3，PDF p.11 |
| INA 精度损失讨论 + "relevant evaluation has been omitted" | 附录 B 末段，PDF p.11 |

## 10. T006 复核补记（2026-09-12）

本篇是本轮**唯一可完整复核的 DCN / 云内部网络论文**，因此也是
[argument_chains.md](../../argument_chains.md) §2 的主样例。

### 10.1 Intro 段落号精确化

本卡第 10 行记"P1–P15（P15 实为贡献 bullet 的末行，非独立段落）"。本轮更正为：
**正文段落为 P1–P6；P7–P15 全部是三条 contribution bullet 被换行切断的碎片**，
其中 P7 首词为 "• We design InArt"，并在 P6 与 P7 之间混入作者页眉 "Jiawei Liu, et al."。
此外 P2 末尾混入行眉 "WWW '24, May 13–17, 2024, Singapore, Singapore"。
**引用 Introduction 时应写"引言 P1–P6"，不要写"P1–P15"。**

### 10.2 论证链的结构性发现（本卡 §2、§7 的重要补充）

> **⚠️ 2026-09-12 T006-R 更正（验收 R1）：本节初稿写"链条在第 2→3 步分叉、之后不再回来"、
> "作者没有让 Web 需求生成他的问题"—— 该判断**过强，已撤回**。
> 原文 P3 明确**再次点名** "DL models employed in **web applications**"，
> 把通信瓶颈直接挂在 Web 应用所用模型的规模上，**链条是连续写的**。
> 更正后的表述见下。**

本轮把引言逐句还原成 6 节点链条后，得到的结论是：

> **InArt 建立了"面向 Web 应用组件"的技术依赖链，且是连续写出的；
> 该链也适用于其他分布式训练；评测未验证具名 Web 服务与服务侧收益。**

- 引言 P1 用**三个行业名**（电商 [13]、社交媒体 [14]、在线广告 [43]）建立 Web 侧对象；
  **P3 再次点名** Web 应用的大模型带来 GB 级传输，从而把"传输量大"变成
  "Web 应用带来的传输量大"。**这两处都不是空话。**
- **需要限定的是走到哪一层为止**：P5 之后的前提是**架构属性**
  （单 PS 架构、路由目的地不确定、多维资源约束），换成任何大规模分布式训练都成立。
  这是该链的**适用范围**，**不是断裂**——把"还适用于别的应用"当作链断的理由，是错的
  （[argument_chains.md](../../argument_chains.md) §6.3）。
- 因此对 [argument_chains.md](../../argument_chains.md) §6.3 替换检查的正确用法是
  **界定适用范围**：把 "web applications" 换成 "AI applications"，论证逐字存活，
  说明该链**不是 Web 专用**；这**不**说明作者没有建立联系。

**因此本卡 §2 的判断需要收窄**：本卡写"这是一个 venue-driven（会议驱动）的 Web 关联，
不是实质关联"——方向正确，但**说法过宽**。更精确的表述是：

> Web 在 InArt 中**只在动机层承重**（它回答了"分布式训练为什么值得研究"），
> **没有进入问题设定、方法设计与评价**。它比 sota 的空白背景句强
> （有三行业具名 + 一条真实传递路径），但比 `www24-wise-start` 弱
> （后者让 Web 指标进入了评价单位）。

本卡 §2 另有一处**需要澄清而非更正**：原文 KEYWORDS 明确包含
"**Web Infrastructure**"，而 CCS CONCEPTS 只有 `Networks→In-network processing`
与 `Computing methodologies→Machine learning`。两者都是作者自填，**不能只取其一**；
[synthesis.md](../../synthesis.md) 曾据 CCS 推断作者未做 Web 定位，该推断过强，已在
[argument_chains.md](../../argument_chains.md) §1.3 更正。

### 10.3 本卡 §7 中一条判断的确认

本卡 §7"不能迁移的前提"末条写：*"InArt 从未接触真实 Web 服务或生产集群……
它发表 WWW 时并不需要生产部署数据、真实服务依赖或实测运维收益。"*
本轮独立复核确认该判断成立，并在
[argument_chains.md](../../argument_chains.md) §2.1.3 补充了支撑细节：
硬件 testbed 仅 6 workers / 2 PS（拓扑照抄 §2 玩具算例），
仿真流量缩小 1000×，实验负载是 Cifar-10 图像分类。
**这是本轮最有信息量的一条可迁移性判断，也是 `rpg_recon_argument_transfer.md`
候选链 3 必须绕开的坑。**

### 10.4 本轮引用的锚点

Intro P1（电商/社交/在线广告 → DL → DT）、P3（硬件加速 + 通信占比）、P4（排除压缩与调度）、
P5（对 SwitchML/ATP/GRID 的批评）、P6（multi-PS 洞察 + 三挑战）——均 PDF p.1–2。
§5.2.1 testbed 设置 PDF p.6；§5.3.1 仿真设置与 1000× PDF p.7；
附录 B 末段 "relevant evaluation has been omitted" PDF p.11。

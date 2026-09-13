# 跨论文综合：WWW 2024–2026 网络论文如何建立 Web relevance

> ## ⚠️ 本文件已于 2026-09-12 被取代（T006）
>
> **历史文件。正文保留原样，但下列结论不再作为当前依据：**
>
> | 本文件的结论 | 现状 |
> | --- | --- |
> | §2 的"四种强弱论证方式"框架 | **被取代**。该框架把"作者怎么写"与"研究对象是什么"混在一根强弱轴上；当前归纳见 [argument_chains.md](argument_chains.md) §6 的**六种桥接动作**（不排强弱阶梯） |
> | §2 对 InArt"CCS 无 Web 类别 ⇒ 作者未做 Web 定位"的推断 | **更正**：InArt 的 KEYWORDS 明确含 "Web Infrastructure"，只有 CCS 无 Web 类别；两者不能只取其一 |
> | §2 对 MULAN"只剩会议归属" | **更正**：字频只测量"作者怎么写"；MULAN 的 Web 联系由**评测工作负载**提供（Online Boutique 等三个 Web 应用系统），属另一维度 |
> | §3 的"DCN/骨干网没有公开观测面，只能靠领域命名" | **收窄**：观测面缺失是**本项目资产缺口**，不是 DCN 研究的固有限制（JitterSketch 用的正是公开骨干 trace）；补到 DCN 全文前不得写成定论 |
> | §1 矩阵中 WiseStart 行"生产部署 + First AFT 降 25.43%"的并列 | **更正**：生产测的是 RCT；First AFT 只在 §4.3 仿真中测过 |
> | §5"11 篇 Research" | 内部计数复核为 13 Research + 1 Industry/Companion（不替代逐篇官方身份验证） |
> | §1 矩阵 `www25-odns` 行末"方法—评价自证" | **撤回**（T006 验收 R4）：受控 ADNS 与唯一 A 记录首先是它的**测量机制**；仅因测量由作者构造就断定循环论证，依据不足。正确记录：**标签生成与独立验证的关系待查** |
> | §1 矩阵 `www24-mulan` / `www24-gamma` 的"可借鉴方式/迁移限制" | **更正**（T006 验收 R5）：不能把"用排名指标"当作"效果与 Web 无关"；两篇都是在 **Web 应用系统**上验证了效果，只是**未测用户/业务收益** |
>
> **当前入口**：[argument_chains.md](argument_chains.md)（论证链复盘）与
> [rpg_recon_argument_transfer.md](rpg_recon_argument_transfer.md)（迁移分析）。
> 本文件在需要追溯 T005 原始推理时仍有价值——**特别是 §4 的"哪些适合 RPG-Recon"
> 与 §6.1 的最近邻能力边界表，本轮未重做，仍可参考**。

---

> 依据 14 篇已深读论文（见 [paper_manifest.md](paper_manifest.md) §2–§4）与各分析卡。
> 本文件只归纳**在原文中实际观察到**的论证方式，不预设分类。
> 标注规则同分析卡：`【作者陈述】` / `【实验支持】` / `【本次推断】`。

## 1. 横向对照矩阵

「Web 关联落点」一行是全表的关键：它区分**论文说了什么**与**论文测了什么**。

| 论文 | 年/轨道 | 网络层次 | 研究任务 | Web 关联落点 | 关联出现位置 | 支撑证据 | 技术贡献 | 可借鉴方式 | 迁移限制 |
|---|---|---|---|---|---|---|---|---|---|
| `www26-starlink-cd` | 2026 R | 接入网 + CDN/DNS | 测量 | **测量对象即 Web 交付栈**（TTFB、整页取回、`CF-Cache-Status`、DNS 缓存命中） | Intro P1 首句 | 2 年、145 国、6.1M traceroute、10.8M DNS 查询、运营商自发 PoP 迁移自然实验 | 三层分解框架 + 三类 regime | 首段宏观数字→具名机制；用**第三方已发生的变更**当自然实验 | 需 Cloudflare AIM/M-Lab 平台数据与跨洲自建终端；我们都没有 |
| `www24-starlink-multi` | 2024 R | 接入网 | 测量 | 应用层（Zoom、Amazon Luna）对比 5G/光纤 | Intro 贡献 (2) | 19.2M M-Lab 众包测速、34 国、98 RIPE 探针 | 低轨接入性能刻画 | 用**具名消费级应用**充当 Web 关联 | 众包平台 + 探针部署能力 |
| `www24-wise-start` | 2024 R | 传输层 | 系统/算法 | **标题级限定词 + 指标绑定**：First AFT（首屏可见内容加载时间） | 题名 + Intro P1 | **生产部署于美团**；First AFT 降 25.43% | 自适应慢启动 | 把网络指标直接定义成 Web 语义指标 | 需真实移动 Web 服务生产环境 |
| `www24-quic-fast` | 2024 R | 传输层 | 测量+系统 | 指标绑定到 HTTP/3 栈（QUIC vs TCP/TLS） | Intro | 100 站点中 16 个启用 HTTP/3；HTTP/3 反而更慢 | 大规模 QUIC 测量 | 用协议栈位置本身建立 Web 关联 | 需自有测量基础设施 |
| `www24-inart` | 2024 R | DCN | 系统 | **领域命名**：电商/社交/广告依赖深度学习 → 分布式训练通信瓶颈 | Intro | 仿真实验（附录 B 自述 "relevant evaluation has been omitted"） | 网内聚合 + 路由选择 | "底层网络支撑 Web 工作负载"这条路径 | CCS 无 Web 类别；实验被作者自己缩到 1/1000 |
| `www25-adnpm` | 2025 R | 接入网 | 测量 | **Web 作为测量渠道**（广告位里跑测速代码）；测得的是接入带宽 | Intro P1 + §3 | 生产 DSP（Sonata/TAPTAP）、15 国、418K 样本、IRB | 广告投递式测量方法 | "测量机制本身与应用体验双重相关" | 需真实广告投放平台与用户基数 |
| `www25-odns` | 2025 R | DNS | 测量 | **一句背景钩子**："DNS serves as a foundational infrastructure for the web"，随后不再出现 | Intro P1 | 972 383 个解析器完成流水线；§4.4 有少量 HTTP 探测 | 开放 DNS 转发依赖聚类 | 从**观测行为**反推有向依赖关系 | 自造 ground truth（受控 ADNS + 唯一 A 记录），方法—评价自证 |
| `www24-encdns` | 2024 R | DNS | 测量 | 对象在 Web 栈上（DoH 跑在 HTTP/2、443），但分析从未离开 DNS 层 | Intro | 1302 个 AS、5031 个解析器；**无任何页面加载/性能/SLO 指标** | DoH 可达性全球测量 | 说明"协议在 Web 栈上"不等于"回答了 Web 问题" | 同上；受益者被作者写成 "DNS community" |
| `www24-cdn-fronting` | 2024 R | CDN | 测量 | **对象即 Web 交付栈**（CDN 共享托管、CNAME、SNI vs Host） | Intro | IRB 批准的**两个大型学术网络被动 DNS** + ActiveDNS；124 585 域名 | 域前置脆弱性测量 | 把"负担不起的前提"重述为"已有公开观测面即可"——并写成贡献 #1 | 需机构级被动 DNS 观测点 |
| `www26-jittersketch` | 2026 R | 骨干网 | 测量+系统 | **装饰性**：QoS/视频/游戏作动机，数据是 MAWI/CAIDA 骨干网流量 | Intro P1 | 骨干网 trace；三个用例中 APT 用例**零实验**，QoS 仅仿真 | 草图式抖动流检测 | **反例**：弱 Web 论证仍被 Research Track 录用 | 不可作为安全垫，见 §5 |
| `www24-gamma` | 2024 R | 微服务（非网络） | 诊断 | **领域命名**：P1 "large-scale web applications"、P2 "customer experience and revenue" | Intro P1–P2、§4.2、结论 | 自建注入：17 VM、100–800 RPS、约 40M trace | 多瓶颈定位 | 领域级命名 + 指标（客户体验、营收）挂钩 | 无具名 Web 依赖；调用图是**输入**不是输出 |
| `www24-mulan` | 2024 R | 微服务（非网络） | 诊断 | **正文不含 Web 论证**："web" 仅出现在参考文献 | — | Online Boutique / Train Ticket 第三方基准 | 多模态因果结构学习 | 无（该论证方式不可借鉴） | 输出是根因排名，图只是中间产物 |
| `www26-metakube` | 2026 R | 容器编排（非网络） | 诊断 | **正文不含 Web 论证**："web" 仅出现在版权行与 "admission webhooks" | — | StackOverflow/GitHub + 合成增强；在被自己标注的集合上评测 | 经验感知 LLM 诊断 | 无（该论证方式不可借鉴） | 输出是自然语言方案 + 对象类型图 |
| `comp25-flow-of-action` | 2025 **Industry/Companion** | 微服务（非网络） | 诊断 | 领域命名 + SRE 流程 | Intro | Google Online Boutique + ChaosMesh 注入 90 个事件 | SOP 约束的多智能体 RCA | 用**流程/规程**支撑"工程师已有诊断步骤" | **不能**作为 Research Track 先例 |

## 2. 归纳出的引言组织方式（真实存在的四种）

以下分类来自矩阵的实际分布，不是预设框架。

### 方式 A：测量对象即 Web（关联最强，成本最高）
代表：`www26-starlink-cd`、`www24-cdn-fronting`、`www25-adnpm`、`www24-starlink-multi`。
首段给带引文的宏观 Web 规模数字 → 一句落到具体机制（CDN 请求映射 / 广告投递 / 应用体验）→
后续所有量度都是 Web 量度。**去掉 Web 术语，技术主张不成立。**
代价：需要大规模第三方平台数据、机构观测点或真实生产渠道。

### 方式 B：指标绑定（关联中等，成本集中在部署）
代表：`www24-wise-start`（First AFT）、`www24-quic-fast`（HTTP/3 栈位置）。
技术问题本身是传输层的，但**评价指标被定义成 Web 语义**（首屏加载时间）。
`www24-wise-start` 有一项方式 A 的论文都没有的东西：**生产环境部署**（美团）。
去掉 Web 术语后，方法仍成立，但**收益叙事失去单位**。

### 方式 C：领域命名（关联弱，成本最低）
代表：`www24-gamma`（"large-scale web applications"）、`www24-inart`（电商/社交/广告依赖深度学习）。
只在引言用"Web 应用"作背景，不具名任何 Web 系统、服务、CDN 或 SLO。
`www24-inart` 的 CCS Concepts **不含任何 Web 类别**（`【本次推断】`：说明作者自己也没把它定位成 Web 论文）。

### 方式 D：背景钩子，之后不再出现（关联最弱）
代表：`www25-odns`（"DNS serves as a foundational infrastructure for the web" 一句）、
`www24-encdns`（对象在 Web 栈上但分析不涉及 Web）、
`www24-mulan` / `www26-metakube`（正文根本不含 Web 论证）。
`www25-odns` 与 `www24-mulan` / `www26-metakube` 被录用，说明**当年没有因 relevance 不足被 desk-reject**，
但**不能推出** relevance 论证可以省略（见 §5）。

## 3. DCN／骨干网 与 接入网／DNS 的前提差异

任务书要求回答"哪些论证对 DCN 和骨干网分别适用"。深读结果支持如下区分：

| 维度 | 接入网 / CDN / DNS 类论文 | DCN / 骨干网类论文 |
|---|---|---|
| 观测面 | 有**公开或半公开的观测面**：RIPE Atlas、M-Lab、被动 DNS、Tranco 域名表、公共解析器 | **没有公开观测面**；DCN 内部拓扑与流量是企业私有资产 |
| 关联建立方式 | 可直接测量用户侧或 Web 侧对象，方式 A 可行 | 只能靠**领域命名**（方式 C）："Web 工作负载跑在这张网上" |
| 典型代表 | `www26-starlink-cd`、`www24-cdn-fronting`、`www25-adnpm` | `www24-inart`、`www26-jittersketch` |
| 代价 | 数据获取门槛高，但一旦拿到，关联天然成立 | 数据容易自持，但 Web 关联系**声称的**而非测得的 |
| 录用现实 | 方式 A/C/D 均有录用 | **方式 C/D 均有录用**（`www24-inart`、`www26-jittersketch`） |

**对本项目最重要的推论**：我们所处的正是"**没有公开观测面**"的一侧。
因此**照搬方式 A 不可行**；可行区间是方式 B（把指标定义成 Web 语义）与方式 C（领域命名）。
`www26-jittersketch` 证明方式 C 甚至方式 D 在 Research Track 有录用先例，
但**先例不等于安全**（§5）。

## 4. 哪些适合 RPG-Recon，哪些只是主题相近

| 论文 | 对 RPG-Recon 的价值 | 判断依据 |
|---|---|---|
| `www26-starlink-cd` | **论证结构最佳模板**：首段宏观数字→具名机制→具名案例→窄缺口→贡献列表 | 但其数据前提（平台级测量 + 自建终端 + 用户侧指标）我们完全没有，只能借结构不能借证据 |
| `www24-cdn-fronting` | **最可迁移的一招**：把"负担不起的前提"重述为"已有公开观测面即可"，并写成贡献 #1 | 我们没有生产事故数据，但有 `task_topo` + 告警/日志作为现成观测面，可类比重述 |
| `www24-wise-start` | **指标绑定**的示范；且是唯一有生产部署的一篇 | 我们**没有**生产部署与业务指标，不能声称同类收益 |
| `www25-odns` | 机制上最接近：从观测行为反推**有向**依赖关系 | 但它的 ground truth 是自己造的控制实验（自证循环），正是 `graph-eval-v2` 要避免的模式 |
| `www26-jittersketch` | **反例价值**：说明弱 Web 论证也可能过审 | 同时其"廉价筛查→昂贵验证"两阶段与我们的 Top-K→条件组装同构 |
| `www24-gamma` | 领域命名的措辞样本 | 输出是 0/1 瓶颈向量，调用图是**输入**，与我们的输出语义不同 |
| `www24-mulan`、`www26-metakube` | 只能作为**最近邻能力边界**的比较对象 | 正文无 Web 论证，不可作为论证模板 |
| `comp25-flow-of-action` | 支撑"工程师已有诊断流程"的引用 | Industry/Companion 轨道，**不能**作为 Research 先例 |

## 5. 对既有 9/10 调研结论的确认、收窄与更正（逐项）

**说明**：依据为本次 14 篇深读结果。既有调研见
[WWW近三年网络相关论文检索与投稿契合分析](../WWW近三年网络相关论文检索与投稿契合分析.md)。

| # | 既有结论 | 本次判定 | 依据 |
|---|---|---|---|
| 1 | "网络、云基础设施与运维诊断可以进入 WWW Research Track" | **确认** | 14 篇中 11 篇为 Research Track 正式录用 |
| 2 | "最有说服力的结合方式是把基础设施技术问题与它支撑的 Web 服务要求连起来，并让实验测到这条关系" | **收窄** | 该说法只对方式 A/B 成立。14 篇中方式 C/D（无实测 Web 关系）占 8 篇且均被录用——**不是唯一可行路径，也不是必要条件** |
| 3 | 建议维持 `Web Infrastructure and Agentic Systems` | **确认** | 官方 CFP 范围含 "the Web as a technical infrastructure" |
| 4 | "轨道名中的 Agentic Systems 不意味着必须添加 LLM 或 agent" | **确认** | 官方文本无此要求 |
| 5 | WiseStart "第一页直接把慢启动和移动 Web 首屏可见内容加载时间相连" | **确认** | 分析卡 §2：题名 + P1 + First AFT 指标 |
| 6 | InArt "证明底层网络支撑 Web 工作负载是可用路径" | **收窄** | 成立但很弱：仅领域命名；CCS 无 Web 类别；附录 B 自述相关评测被省略，实验规模被缩至 1/1000 |
| 7 | MULAN 是"与本项目最直接的 WWW RCA 先例" | **确认并加强** | 输出是根因排名，图只是中间产物（仅 PR@K/MAP@K/MRR），**从不做逐边评价**——与我们输出语义不同 |
| 8 | MetaKube "第一页对具体 Web 工作负载的关联较 WiseStart 间接" | **更正** | 不是"较间接"，而是**基本不存在**：正文 "web" 仅出现在版权行与 K8s 术语 "admission webhooks" |
| 9 | Smart Eye 作为 Industry 叙事参考 | **确认**（轨道无误） | 但须注意 netman.aiops.org 的 "Paper" 链接指向同组另一篇 ViTs 论文 |
| 10 | 旧调研未提及 | **新增发现** | `www26-jittersketch`（骨干网流量、弱 Web 论证、Research Track 录用）；`www25-odns`；`www24-cdn-fronting`；`www26-starlink-cd`（本批 Web 关联最强） |
| 11 | "目前最需要补的是实际支撑哪些 Web 服务、异常探测端点对应什么服务依赖、图恢复怎样改变工程师的判断" | **确认** | 与本次结论一致，且本次进一步指出：这三项属于方式 A 的前提，若不补则只能走方式 B/C |

**明确否定的一条**：不能用"某篇弱 relevance 论文被录用"推出"我们也可以弱 relevance"。
理由：① 我们看不到审稿意见与落选稿件；② 各年度 pool 不同；③ 官方 relevance 条款是硬性 desk-reject 规则。
`【本次推断】`

## 6. 最近邻工作的能力边界 vs 我们的问题定义

任务书要求"文献先例、写作技巧与科学创新分别讨论"。

### 6.1 能力边界（文献先例）

| 最近邻 | 输出对象 | 监督/数据 | 是否输出可逐边核验的图 |
|---|---|---|---|
| `www24-mulan` | 根因排名（top-k） | 第三方基准，日志标签由外部异常检测器产生；故障注入方式未在文中说明 | **否**（图仅中间产物） |
| `www24-gamma` | 0/1 瓶颈向量 + 排序 | 自建注入（17 VM、100–800 RPS、约 40M trace）；调用图来自 trace，是**输入** | **否** |
| `www26-metakube` | 自然语言方案 + K8s 对象类型知识图谱路径 | StackOverflow/GitHub + 合成增强，在被自己标注的集合上评测 | **否**（对象类型级，非设备级） |
| `www25-odns` | 解析器聚类 + 有向转发依赖 | 受控 ADNS + 唯一 A 记录自造 ground truth | 部分（依赖关系有向，但自证） |
| `comp25-flow-of-action` | 受 SOP 约束的工具调用与根因结论 | Google Online Boutique + ChaosMesh 注入 90 事件 | **否** |

### 6.2 写作技巧（可借鉴）

1. 首段：带引文的宏观 Web 规模数字 → 一句话落到具体机制（`www26-starlink-cd`）。
2. 缺口要**窄**：把缺口定义成"缺少某一维度的测量/分解"，而不是"已有工作不够好"。
3. 用具名案例把抽象错配变成可测链条（`www26-starlink-cd` P6 的 ZW→FRA 案例）。
4. 用**当事方自己已发生的变更**替代自建部署（运营商迁移 PoP）。
5. 把"负担不起的前提"重述为"已有观测面即可"，并写成贡献 #1（`www24-cdn-fronting`）。
6. 每个分析段末尾写 Takeaway，把观察收敛成可被引用的短句。

### 6.3 科学创新（我们的差异在哪）

**不能主张的**（文献先例已经占据）：
- "结合拓扑与时间做根因定位"——`www24-gamma`、`comp25-flow-of-action` 已做。
- "多源数据 + 图 + 根因定位"——`www24-mulan` 已做。
- "只有根排名、没有图"——不成立：`www24-mulan` 有中间图，`www26-metakube` 有对象类型图，
  `www25-odns` 输出有向依赖。

**可以主张的差异**（须由实验支撑，当前为待验证主张）：
1. **输出语义**：现有工作输出排名/瓶颈集合/自然语言方案；我们输出**每条边必须已存在于原始
   `task_topo`** 的设备级解释 DAG，并逐边给出证据与未决标注。
2. **起点不确定性**：`www24-mulan` 等手段通常假定根因唯一或直接输出排名；我们保留
   Top-K 竞争起点，并**以起点为条件**重建图（C1）。
3. **未知与否定分离**：现有手段多把未观测关系当作负例；我们掩码 unknown、allowed 中性（C2）。
4. **局部支持与全局组装分离**：`www25-odns` 的依赖关系自证；我们把邻接对的局部方向支持
   与根条件 DAG 组装分开，并暴露两者冲突。

**风险**：第 2、4 条与 `www25-odns`、`www26-jittersketch` 的两阶段结构存在**形式相似性**
（廉价筛查 → 昂贵验证）。必须在 Related Work 中显式区分，不能靠措辞回避。

## 7. 剩余不确定性

1. **13 篇核心候选未取得全文**（见 [manifest](paper_manifest.md) §6.2），其中
   `www26-meteor`、`www26-beeqos`、`www26-wiseswap`、`www25-x-clusterlink`、`www25-miresga`
   属核心 DCN/云网络，可能改变 §3 的"无公开观测面"判断。**在取得前不得把该判断写成定论。**
2. **2025 年 track 归属**依赖 IW3C2 存档的 front matter，未逐篇核对 ACM DOI 页。
3. **`www26-starlink-cd` 的 "PoP 距离解释 50% 方差"在正文中找不到支撑**（分析卡 §6），
   若引用该数字须先解决。
4. **`www24-inart` 的实验规模**：附录 B 自述相关评测被省略、实验缩至 1/1000，
   其性能数字不应当作可比基线。
5. **未做穷尽目录**：三年目录已逐条解析，但核心集外的条目只看题名；未检出不等于不存在。

## 8. 一句话结论

**WWW 网络论文的 Web relevance 存在四种强弱不同的建立方式；最强的方式（A）需要我们没有的
平台级观测数据，最弱的方式（D）虽有录用先例但不足以作为安全垫。对本项目可行的是
方式 B（把评价指标定义成 Web 语义）与方式 C（领域命名 + 机制差异），
具体取舍见 [positioning_options.md](positioning_options.md)。**

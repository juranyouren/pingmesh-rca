# T009 来源与核验边界

日期：2026-09-15。与 [report](report.md)、[指标矩阵](evaluation_metrics_matrix.md) 配套。
旧来源记录保存在 [sources.T007_snapshot](sources.T007_snapshot.md)，其中旧判断不再生效。
证据分为：本轮一手定点阅读（F）、复用独立验收的一手定位（V）、仅身份/摘要（A）、本文建议（P）。
未核实不是“原文绝对没有”；没有给出公式的条目不据名称补造定义。

## 1. 论文身份与承重证据

| ID | 论文 / 正式身份与一手入口 | 核验范围与位置 | 可核实内容；剩余未知 |
| --- | --- | --- | --- |
| A1 | Chakraborty 等，CausIL: Causal Graph for Instance Level Microservice Data；WWW 2023，2905–2915；[DOI](https://doi.org/10.1145/3543507.3583274)，[作者稿](https://arxiv.org/pdf/2303.00554) | F：复读既有 tmp/t007/causil.txt §5.3、§6.3、附录 B；V：T007 R2 的 PDF p.7/8/10 定位 | Adj 忽略方向；AH 考虑正确邻接的定向；SHD 为结构编辑。真实 Table 2 也报结构分数，图按 §4.1 假设构造。AH 全部混淆计数、反向代价和事故宏平均未核准 |
| A2 | Pu 等，ErrorPrism: Reconstructing Error Propagation Paths in Cloud Service Systems；ASE 2025，3534–3545；[DOI](https://doi.org/10.1109/ASE63991.2025.00292)，[v1](https://arxiv.org/html/2509.26463v1) | F：§III-B/D、§IV-A1/A3、IV-E；V：Fig.4 的 8/31/42 | 函数路径 exact-match Eq.(2)；静态候选 Precision Eq.(3)；Table I 按 hop，Fig.5 为推理时间。参考来自复盘/源码核验；盲标未知 |
| A3 | Fukuda 等，Semi-Supervised and Disentangled Causal Discovery for Analyzing Fault Propagation in Microservices；IEEE Access 14，30613–30626，2026；[DOI](https://doi.org/10.1109/ACCESS.2026.3667143) | V：[T007 独立验收](../../../../.ai/T007_acceptance.md) 对作者接受稿 Eq.(16)(17)、§V-B-1、§VI-C-1 的核验 | nSHD=(E_extra+M+R_rev)/T；方向和位置均匹配才为 TP。trace 派生参考；正式版页码未重新对齐，不能沿用“本轮取得出版社 PDF”的旧自述 |
| A4 | Landau 等，Retrofitting Service Dependency Discovery in Distributed Systems；2025 arXiv 预印本；[v1](https://arxiv.org/html/2510.15490v1#S6.SS1) | F：§VI-A/Table I | 架构依赖作为参考；运行期未发生流量的依赖降低召回。docker-proxy 的等价处理不是 unknown mask；方向匹配细则未知 |
| B1 | Tsamardinos、Brown、Aliferis，The Max-Min Hill-Climbing Bayesian Network Structure Learning Algorithm；Machine Learning 65(1):31–78，2006；[DOI](https://doi.org/10.1007/s10994-006-6889-7)，[作者稿](https://pages.mtu.edu/~lebrown/supplements/mmhc_paper/paper_online.pdf) | V：T007 验收 §9.1.4、Algorithm 4，作者稿 p.22–23 | PDAG 增删、增删方向和反转；反转一次。DAG 特例可引用；未逐页比对出版社版，不称本轮重读 |
| B11 | Zheng 等，DAGs with NO TEARS: Continuous Optimization for Structure Learning；NeurIPS 2018；[正式论文](https://proceedings.neurips.cc/paper_files/paper/2018/file/e347c51419ffb23ca3fd5050202f9c3d-Paper.pdf) | V：[本轮前置结论](../指标与相关工作缺陷_验收结论.md) 的 §5 定点核验 | 通用结构学习实际用 SHD；不把工具默认细则自动归给论文 |
| C1 | Yuan 等，NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topology；IEEE TNNLS 36(10)，2025；[DOI](https://doi.org/10.1109/TNNLS.2025.3574316) | V：T007 R1，§III、§V-A、§V-C Eq.(16)、Fig.7；[现有卡](../related_work_catalog/papers/RW0103.md) | 每告警原因集合由专家标注，ACC@k 评价候选局部集合命中；不是全局设备根 Top-k。Eq.(16) 的完整集合判定/归一化细则本轮未重获，不给臆造公式 |
| C2 | Yang 等，SkyNet: Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures；SIGCOMM 2025；[DOI](https://doi.org/10.1145/3718958.3750536)，[作者稿](https://ennanzhai.github.io/pub/sigcomm25-skynet.pdf) | F：§6.4（PDF p.11）及 Fig.10c（p.12）、§7.1/7.3 | 上线前后 mitigation time；中位数 736s→147s，图无详细轴数。是整体系统观测，非固定其他条件的图收益试验；时间戳顺序也可误导根判断 |
| N1 | EvoCause: LLM-Guided Evolution of Causal Graphs for Root Cause Analysis；2026 预印本 [v1](https://arxiv.org/html/2607.27290v1) | F：§3.1、§4.1 Eq.(18)(19)、§4.2 Table 1、§4.3 | 类型级 DAG；Graph F1=2交集/(两边数和)，nSHD=单位增删反转/真边数；仅合成图，10 图均值/标准差。TeleRCA 无图真值；不继承会议等级 |
| N2 | Wu、Zhao、Tang、Kato，PropLLM: Propagation-Aware Scene Reconstruction for Network Fault Diagnosis；2026 预印本 [HTML v1](https://arxiv.org/html/2606.00582v1)，[PDF v1](https://arxiv.org/pdf/2606.00582v1) | F：§III、§IV-D、§V-A/B/D、Tables II/III/VII、Fig.4（PDF p.9） | 实际输出自然语言回溯链、根设备、类型；RC@1/RC@3 确认。Fig.4 有 1-CCED；定义、参考链、编辑代价、归一化边界未核准，见 §3 |
| W1 | Li、Zhu、d’Amorim、Orso，Enlightened Debugging；ICSE 2018；[作者出版列表](https://damorim.github.io/publications.html)，[作者稿](https://damorim.github.io/publications/li-etal-icse2018.pdf) | F：§3.1–3.2，PDF p.5–9，Tables 1–7 | 模拟查询数和不同 invocation 数分开；反馈由正确程序提供，100 次预算。另有真人研究；协议及限制详见排查说明 |
| W2 | Haeberlen 等，NetReview: Detecting when interdomain routing goes wrong；NSDI 2009；[USENIX 正文](https://www.usenix.org/legacy/event/nsdi09/tech/full_papers/haeberlen/haeberlen_html/index.html) | F：§6.5、Fig.5 | CAIDA AS 拓扑、不同部署规模下各 10,000 次模拟，随机端点路径及路径内故障 AS，报告候选数均值；非实际检查数 |

A1 合成/半合成分别见 §5.2、Table 1；真实代理参考图见 §6.3、Table 2、附录 B。
不能用“合成生成图”掩盖真实代理分支的有效性问题。A1 Table 2 一组 AdjR=0.876、AHR=0.960
（V：T007 R2），不符合通常方向 TP 必为邻接 TP 子集且同分母的解释，故 AH 细则保持 UNKNOWN。
A2 Fig.4：0–1 hop=(8+31)/102=38.2%；0–2 hop=(8+31+42)/102=79.4%。
这是对旧比例的更正，不据此弱化完整路径匹配难度。

## 2. SHD 实现证据：锁定版本

本表是**实现/文档证据，不是新增代表论文**。2026-09-15 通过 GitHub commits API
取得各文件最近修改 commit；只读源码，未安装或执行任何库。下列链接锁定 commit，避免 main 漂移。

| 来源、版本与接口 | 输入/端点规则 | 反向代价与限制 |
| --- | --- | --- |
| [causal-learn SHD.py @1ea1183](https://github.com/py-why/causal-learn/blob/1ea11831264cecec1b5397cd6093dc0958bdc362/causallearn/graph/SHD.py)，SHD(truth,est) | Graph；按节点名对齐，遍历无序节点对（含对角），比较双端点状态 | 不一致加 1；DAG 反向=1。ArrowConfusion 的 FP+FN 不是此接口 |
| [CDT metrics.py @55b6b2d](https://github.com/FenTechSolutions/CausalDiscoveryToolbox/blob/55b6b2de81fc8eac7e4a298a96225412280334af/cdt/metrics.py)，SHD | 邻接矩阵/图经 retrieve_adjacency_matrix；对应节点顺序需固定 | double_for_anticausal=True 默认反向=2；False 把对称差合并，反向=1 |
| 同一 CDT 文件，SHD_CPDAG | 先转 CPDAG，再 SHD(...,False) | 比较等价类、反向按一次；原 DAG 反向可能在转换后消失。目标改变，不是库自相矛盾 |
| [gCastle evaluation.py @a873bd5](https://github.com/huawei-noah/trustworthyAI/blob/a873bd540d0a4299f1eb6a8394409c8805c5cf3f/gcastle/castle/metrics/evaluation.py)，MetricsDAG._count_accuracy | 预测矩阵允许 -1 无向编码；骨架多余＋缺失＋反向 | 有向反转=1；同骨架无向预测可能不增加该 SHD，不能称反向=0；DAG/混合图分开 |
| [dodiscover metrics.py @ade4e48](https://github.com/py-why/dodiscover/blob/ade4e48f0ecfe8ac26f3ddf69e8eead095e4b2d4/dodiscover/metrics.py)，structure_hamming_dist | 单一有向或无向图；邻接差 | double_for_anticausal=True 默认 2、False 为 1；不推广到混合端点图 |
| [bnlearn 5.3-20260901 文档](https://www.bnlearn.com/documentation/man/compare.html)，shd(...,cpdag=TRUE) | bn 图；默认 CPDAG；cpdag=FALSE 可比较网络自身 | 参数存在已核实；正文 Details 保留无条件转换旧描述，版本文档有表述张力。未读内部实现，不给 FALSE 分支反转代价作额外背书 |
| [历史 CRAN 5.0 文档](https://search.r-project.org/CRAN/refmans/bnlearn/html/compare.html) | V：T007 R4 原引用先转 CPDAG | 原引用并非伪造；历史版本说明不能推广到整个 bnlearn |

纯 DAG 固定节点的 raw SHD 在空边集上有定义；混合端点、等价类及归一化必须单列。
CDT/dodiscover/gCastle 的完整边界条件未作运行验证，以上只描述源码阅读结果。

## 3. PropLLM U3 定点补核

已检查 HTML 的输出、数据设置、整体评价、消融/冷启动/延迟段，以及 14 页 PDF 中的
Fig.4/邻文、Table III、后部章节与参考文献边界；PDF 页面请求成功，工具未向本会话返回可见栅格，
图轴依据 PDF 文本抽取和 HTML 邻文交叉核实，**不宣称完成逐页视觉 QA**。

- Table III 明列 RC@1、RC@3。它们不能推出“显式保留竞争根假设”，也推翻不了排名评价存在的事实。
- §IV-D 输出为自然语言描述的逐跳回溯链，终点是根设备；不是已验证的完整设备边表。
- Fig.4 邻文明确有 1-CCED 并描述 min-max 映射；本轮未核准 CCED 全称、基本距离、参考对象、
  标注来源、节点/序列匹配、增删反向代价、空链规则、归一化样本范围和聚合。
- 检查的 v1 PDF 没有定位到独立附录及可复用 CCED 定义；未获得独立补充材料。
  因而结论为“已有链质量展示，但口径未核准”，不是“没有任何链结构评价”。
- §III 的知识来源区分静态拓扑先验与训练集案例；不能仅因使用 KG 判泄漏。
  §V-D Table VI 缩小故障 KG 时保留全部 SFT 数据，作者承认这不是联合冷启动。
- Table VII 是单例推理延迟；参考对象为计算运行，不是工程师排查时间。

需作者定义或公开评测实现才能把 CCED 纳为可复用指标；本轮不展开缩写、不补造公式。

## 4. 身份更正、背景与排除项

| 原 ID | 更正与证据深度 | 在本包的作用 |
| --- | --- | --- |
| B8 | F：[JMLR 正式页](https://jmlr.org/papers/v14/mahdi13a.html)：Rami Mahdi、Jason Mezey；Sub-Local Constraint-Based Learning of Bayesian Networks Using A Joint Dependence Criterion；JMLR 14(49):1563–1603，2013 | 清除旧 Mahdi & Meek 及虚构题名；不再以未定点重读正文的命题作指标论证 |
| B9 | F/A：[PMLR](https://proceedings.mlr.press/v206/shang23a.html)，首作者 Hongwei Shang，Precision/Recall on Imbalanced Test Data，AISTATS 2023，206:9879–9891 | 仅身份/摘要，不再为 mask 或抽样方案背书 |
| B10 | F/A：[IJCAI](https://www.ijcai.org/proceedings/2021/277)，Maxime Peyrard、Robert West，A Ladder of Causal Distances，2021，2012–2018 | 背景，正文未逐节核验；不承载本文指标主论证 |
| B7 | A：[SID 摘要](https://arxiv.org/abs/1306.1043)，Peters、Bühlmann | 背景；当前无干预识别主张，不选 SID 是本文任务判断，不以未读正文论证细则 |
| C8 | A：[APGNN DOI](https://doi.org/10.1016/j.comnet.2022.109485)；仅摘要 | 全文图评价/能力 UNKNOWN；不能归“确定无图指标” |
| C3–C7 | 旧表的 Hawkeye、FaultInsight、RCD、MULAN、Eadro 为 RCA/下游评价背景线索 | 未重新全面核验，不以“无任何图评价”统一排除；旧身份和检索细节仅作历史追溯 |

不重做 CCF 大全。Neural Computation 的自相矛盾旧条目已从现行表删除，B7 仅作背景，
本包以正式会议/期刊身份区分预印本，不拿未复验等级支持指标共识。目录全量等级/著录复验仍是 T008 待办。

## 5. 获取记录与缺口

- 复用最小输入、T007/T008 验收、现有卡片和 CausIL 文本；没有全库重搜。
- 首选 Enlightened 的 cin.ufpe.br 地址返回 Internal Error；经作者现行出版列表找到
  damorim.github.io 上的同名作者稿并成功读取。只为填此缺口进行了题名检索。
- NEC DOI 本轮访问返回 Internal Error；docs/papers 已不存在，保留 T007 验收的位置和 V 状态。
- PropLLM/EvoCause/ErrorPrism/Retrofitting 读取固定 v1；SkyNet 与 NetReview 使用作者/会议信息。
- GitHub API 只读 commit 元数据并读实现；原报告错误的 SHD 类路径已更正。
- 未重新下载转换 PDF、未调用外部 LLM API、未运行模型/标签审计/评分/模拟器/目录生成器。
- 未确认事项保留在矩阵；“未核准”不会阻塞阅读包交付，也不等于已关闭原文信息缺口。

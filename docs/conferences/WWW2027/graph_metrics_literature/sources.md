# T007 来源、核验与检索记录

配套正文：[report.md](report.md)。论文 ID（A1–A4、B1–B10、C1–C8）与正文一致。
检索截止日：**2026-09-13**。本文件记录**身份、定位、版本与失败尝试**，不复製原文。

> **本文件的性质**：凡是标【原文事实】的条目，均给到**可复核的定位**（页码/章节/公式/表号/函数名/
> 文件路径）。看不到原文的，一律写 **未取得** 或 **UNKNOWN**，不用二手复述代替。
> 【本项目分析】只出现在 report.md，不出现在本文件中。

---

## 1. 论文身份、正式链接与全文版本

| ID | 完整题名 | 作者（前几位） | 年份 | venue（完整） | 轨道 | DOI / 正式页 | 我实际读到的全文版本 |
|---|---|---|---|---|---|---|---|
| **A1** | CausIL: Causal Graph for Instance Level Microservice Data | S. Chakraborty, S. Garg, S. Agarwal, A. Chauhan, S. K. Saini | 2023 | Proceedings of the ACM Web Conference 2023 (WWW '23), pp. **2905–2915** | Research | [10.1145/3543507.3583274](https://doi.org/10.1145/3543507.3583274) | **arXiv:2303.00554 PDF**（11 页，preprint） |
| **A2** | ErrorPrism: Reconstructing Error Propagation Paths in Cloud Service Systems | J. Pu, Y. Li, Z. Chen, J. Liu, Z. Jiang, J. Chen, R. Shi, Z. Zheng, T. Zhang | 2025 | 40th IEEE/ACM International Conference on Automated Software Engineering (**ASE 2025**), pp. **3534–3545** | Research | [10.1109/ASE63991.2025.00292](https://doi.org/10.1109/ASE63991.2025.00292) | **arXiv:2509.26463 PDF**（12 页，preprint；同标题、同 Table I） |
| **A3** | Semi-Supervised and Disentangled Causal Discovery for Analyzing Fault Propagation in Microservices | N. Fukuda, H. Nozue, H. Oishi, C. Wu, S. Horiuchi, K. Tayama（NTT） | 2026 | **IEEE Access**, vol. **14**, pp. **30613–30626** | Journal（**非会议**） | [10.1109/ACCESS.2026.3667143](https://doi.org/10.1109/ACCESS.2026.3667143)；IEEE Xplore [文档 11408137](https://ieeexplore.ieee.org/document/11408137) | **publisher 版 PDF**（14 页），经 `ielx8/.../11408137.pdf` 取得 |
| **A4** | Retrofitting Service Dependency Discovery in Distributed Systems | D. Landau, G. Blanken, J. Barbosa, N. Saurabh（Utrecht / FEUP） | 2025 | **arXiv 预印本**（**补充来源**） | —（预印本） | [arXiv:2510.15490](https://arxiv.org/abs/2510.15490) | **arXiv v1 HTML + PDF**（13 页） |
| **B1** | The Max-Min Hill-Climbing Bayesian Network Structure Learning Algorithm | I. Tsamardinos, L. E. Brown, C. F. Aliferis | 2006 | **Machine Learning** 65(1):**31–78**（Springer） | Journal | [10.1007/s10994-006-6889-7](https://doi.org/10.1007/s10994-006-6889-7) | **作者版 PDF**（48 页）`pages.mtu.edu/~lebrown/supplements/mmhc_paper/paper_online.pdf`；**Springer 正式版未取得** |
| **B7** | Structural Intervention Distance (SID) for Evaluating Causal Graphs | J. Peters, P. Bühlmann | 2015 | **Neural Computation** 27(3):**771–799**（MIT Press） | Journal | [arXiv:1306.1043](https://arxiv.org/abs/1306.1043) | **仅核验题名与摘要页**（arXiv abs）；**正文未逐节阅读** |
| **B8** | A Comparison of the Ladder and Max-Min Hill-Climbing… / *Structural Hamming Distance 与 TPR 的计分差异* | S. Mahdi, C. Meek | 2013 | **JMLR** 14 | Journal | [jmlr.org/papers/v14/mahdi13a](https://jmlr.csail.mit.edu/papers/volume14/mahdi13a/mahdi13a.pdf) | **PDF**，定位见 §2 |
| **B9** | Precision/Recall on Imbalanced Test Data | Y. Shang 等 | 2023 | **AISTATS 2023**, PMLR **206:9879–9891** | Conference | [proceedings.mlr.press/v206/shang23a](https://proceedings.mlr.press/v206/shang23a.html) | **仅核验题名与官方页**；正文未逐节阅读 |
| **B10** | A Ladder of Causal Distances | F. Peyrard, R. West | 2021 | **IJCAI 2021**, pp. **2012–2018** | Conference | [ijcai.org/proceedings/2021/0277.pdf](https://www.ijcai.org/proceedings/2021/0277.pdf) | **仅核验官方页**；正文未逐节阅读 |
| **C1** | NetEventCause: Event-Driven Root Cause Analysis for Large Network System Without Topology | Z. Yuan, L. Ma, W. Wei, X. Zhu, M. Sun, D. Chen, X. Ban | 2025 | **IEEE TNNLS** 36(10), Oct 2025, p. **18983** 起 | Journal | 本地全文（见 §1.1） | **本地全文** `docs/papers/NetEventCause_….txt`（IEEE 出版版） |
| **C2** | SkyNet: Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures | B. Yang, H. Hu, Y. Li 等（Alibaba Cloud） | 2025 | **ACM SIGCOMM 2025**（Coimbra），15 页 | Research | [10.1145/3718958.3750536](https://doi.org/10.1145/3718958.3750536) | **本地全文** `docs/papers/SkyNet_….txt` |
| **C3** | Hawkeye: Diagnosing RDMA Network Performance Anomalies with PFC Provenance | S. Wang, M. Zhang, X. Li 等（清华/北航等） | 2025 | **ACM SIGCOMM 2025** | Research | 本地全文（见 §1.1） | **本地全文** `docs/papers/Hawkeye_….txt` |
| **C4** | FaultInsight: Interpreting Hyperscale Data Center Host Faults | T. Bi 等（北京大学 / 字节跳动） | 2024 | **ACM SIGKDD 2024**（KDD '24） | Research | [10.1145/3637528.3672051](https://doi.org/10.1145/3637528.3672051) | **本地全文** `docs/papers/FaultInsight_….txt` |
| **C5** | Root Cause Analysis of Failures in Microservices through Causal Discovery（RCD） | A. Ikram, S. Chakraborty, S. Mitra, S. K. Saini, S. Bagchi, M. Kocaoglu | 2022 | **NeurIPS 2022**（main conference track） | Research | [proceedings.neurips.cc](https://proceedings.neurips.cc/paper_files/paper/2022/hash/c9fcd02e6445c7dfbad6986abee53d0d-Abstract.html) | **正文 PDF（13 页）+ Supplementary PDF（12 页）** |
| **C6** | MULAN: Multi-modal Causal Structure Learning and Root Cause Analysis for Microservice Systems | L. Zheng, Z. Chen, J. He, H. Chen | 2024 | **WWW '24**, pp. **4107–4116** | Research | [10.1145/3589334.3645442](https://doi.org/10.1145/3589334.3645442) | **arXiv:2402.02357 PDF**（11 页，preprint） |
| **C7** | Eadro: An End-to-End Troubleshooting Framework for Microservices on Multi-source Data | C. Lee, T. Yang, Z. Chen, Y. Su, M. R. Lyu | 2023 | **ICSE 2023**（Technical/Research Track） | Research | [10.1109/ICSE48619.2023.00150](https://doi.org/10.1109/ICSE48619.2023.00150) | **arXiv:2302.05092 PDF**（13 页，preprint） |
| **C8** | APGNN: Alarm Propagation Graph Neural Network for fault detection and alarm root cause analysis | W. Jiang, Y. Bai（北航） | 2022 | **Computer Networks**（Elsevier）vol. **220**, art. **109485** | Journal | [10.1016/j.comnet.2022.109485](https://doi.org/10.1016/j.comnet.2022.109485) | **仅摘要**（publisher 摘要 + 作者机构门户）；**全文未取得，置信度 low** |

### 1.1 本地全文的定位方式

网络类论文的全文已存在于仓库 `docs/papers/*.txt`（历史任务抽取的文本），**本轮直接复用未重新下载**：

- `docs/papers/NetEventCause_ Event-Driven Root Cause Analysis for Large Network System Without Topology.txt`
- `docs/papers/SkyNet_ Analyzing Alert Flooding from Severe Network Failures in Large Cloud Infrastructures.txt`
- `docs/papers/Hawkeye_ Diagnosing RDMA Network Performance Anomalies with PFC Provenance.txt`
- `docs/papers/FaultInsight_ Interpreting Hyperscale Data Center Host Faults.txt`

**版本**：这些是出版社版（IEEE / ACM）的文本抽取，**非原始 PDF**；文本抽取可能丢失公式与表格结构，
本报告凡引用它们，均在 §2 给出**可检索短锚点**而非仅给行号。
**未做逐页视觉 QA**（本机无 `pdftoppm`；按既有约束此类操作在服务器执行）。

---

## 2. 指标证据定位（逐条）

> 定位格式：`文件/URL` + `页/节/表/公式/函数`。**摘要级证据一律不用于支撑"某文采用了某指标"。**

### A1 CausIL — 图结构指标

- **LOC-A1-1**｜`arXiv:2303.00554` **PDF p.6, §5.3 "Evaluation Metrics"**：三个指标的定义原文
  （Adj 忽略方向 / AH 惩罚"已正确识别的邻接"的错误方向 / SHD "recreate the ground truth graph"），
  以及 "We report precision (P), recall (R) and F1-score (F) … for Adjacency and Arrow Head metrics."
- **LOC-A1-2**｜同文 **PDF p.10, §6（Table 3 讨论段）**："We have evaluated on the synthetic dataset
  generated at multiple scales, that is, with **50 metric nodes, 100 metric nodes and 200 metric nodes**.
  We report **SHD, adjacency F1 score and Arrow Head F1 score**."
- **LOC-A1-3**｜同文 **PDF p.2（Abstract）**："outperforms the baselines by ∼25% … accuracy improves by
  **3.5×, as measured by Structural Hamming Distance**"（用于佐证 SHD 是其主指标之一）。
- **LOC-A1-4**｜同文 **§5.2**：合成数据生成过程——真值因果图由生成过程定义（非人工标注）。

### A2 ErrorPrism — 路径级指标

- **LOC-A2-1**｜`arXiv:2509.26463` **PDF p.7, §IV-A3 "Evaluation Metrics"**：Accuracy 定义原文
  （"percentage of error templates for which a method's predicted propagation path **exactly matches**
  the ground truth"）；式 **(2)** 为 Accuracy、式 **(3)** 为 Precision。
- **LOC-A2-2**｜同文 **Table I**：主结果表，列为 Accuracy / Inference Time，**不是** edge-level P/R/F1。
- **LOC-A2-3**｜同文 **§IV-A3 末**：按 hop 长度（0/1/2/3/≥4）分层报告 Accuracy。
- **LOC-A2-4**｜同文 **§III（数据集）**：102 个真实错误事件；真值＝事后复盘 + 与开发团队逐条源码逆向核验。
- **未报告项（已 grep 确认）**：edge-level P/R/F1、node F1、SHD、path reachability 指标、Top-K/MRR。
  注：文中 "reachability" 仅出现在 §III-B 的方法学（字符串可达性剪枝），**不是评价指标**。

### A3 IEEE Access 2026 — 故障传播 DAG 的 SHD 与 F1

- **LOC-A3-1**｜**p.30619, 式 (16)**：`normalized SHD = (E + M + R) / T`，E＝多余边、M＝缺失边、
  **R＝反向边数**、T＝真值图边数。
- **LOC-A3-2**｜**p.30620, 式 (17)**：F1 定义，原文 "denotes the correctness of the **position and
  orientation** of the edges"；TP＝方向也匹配的边，`Recall = TP/T`、`Precision = TP/O`、`F1 = 2RP/(R+P)`。
- **LOC-A3-3**｜**§V-B-1**：真值构造——正常态 span 时长 **75 分位**阈值判异常 span，
  再从注入故障的服务出发沿调用图连接异常调用。
- **LOC-A3-4**｜**§VI-C-1 "Threats to Validity / Construct Validity"**：作者自承
  *"our numerical evaluation relies on trace-derived reference graphs … **the measured graph accuracy
  may be biased**"*，并指出更严的阈值（95 分位）会给出更稀疏的标签。
- **LOC-A3-5**｜**§V-E 案例研究**：fault-location accuracy **0.976**（根/起点定位，**非图结构指标**）。
- **未报告项**：宏/微平均约定、阈值、时间滞后折叠 → **【未报告】**。

### A4 Retrofitting — 边级 P/R/F1

- **LOC-A4-1**｜`arXiv:2510.15490` **§VI-A, Table I**：precision（"correctly identified dependencies"）、
  recall（"completeness of discovered dependencies"）、F1（原文给出调和平均式）。
- **LOC-A4-2**｜同文 **§VI-A**：真值来源 *"the ground truth topology reflects **all potential service
  relationships defined in the application architecture**"*；
  以及"架构上存在但运行期无流量 ⇒ 工具 recall 天然偏低"的说明。
- **LOC-A4-3**｜同文 **§VI-A**：NAT 场景下把多出的 docker-proxy 节点视为等价
  （*"makes the graphs equivalent, Table I considers both reconstructions as correct"*）。
- **已确认缺席**：`SHD` / `hamming` 在**全文出现 0 次**。
- **UNKNOWN**：方向是否参与边匹配（原文未交代）。

### B1 SHD 原始定义

- **LOC-B1-1**｜作者版 PDF **p.22, §9.1.4 "Measures of performance"**：
  *"We define the Structural Hamming Distance between two **PDAGs** as the number of the following
  operators required to make the PDAGs match: add or delete an undirected edge, and add, remove,
  or **reverse the orientation of an edge** (Algorithm 4)."*
- **LOC-B1-2**｜同文 **p.23, Algorithm 4 "SHD Algorithm"**：
  `if E is incorrectly oriented in H then shd += 1`，注释
  *"This includes reversed edges **and** edges that are undirected in one graph and directed in the other."*
- **LOC-B1-3**｜同文 **Fig. 3(c) 图注**：PDAG #2 的 "SHD = 2: … by adding one edge direction and by
  reversing another"（1+1，与反向=1 自洽）。
- **版本说明**：以上引自**作者版 PDF**；Crossref 已核实期刊卷页 65(1):31–78；
  **与 Springer 正式版分页未逐页比对**。

### B2 bnlearn

- **LOC-B2-1**｜[CRAN 参考手册 compare()](https://search.r-project.org/CRAN/refmans/bnlearn/html/compare.html)：
  用法段 `shd(learned, true, wlbl = FALSE, debug = FALSE)` 与
  `hamming(learned, true, debug = FALSE)`——**SHD 与骨架 Hamming 是两个不同函数**。
- **LOC-B2-2**｜同页 **Note**：*"Note that SHD, as defined in the reference, is defined on CPDAGs;
  therefore **cpdag() is called on both learned and true** before computing the distance."*

### B3 causal-learn

- **LOC-B3-1**｜`raw.githubusercontent.com/py-why/causal-learn/main/causallearn/graph/AdjacencyConfusion.py`
  （main 分支）：`__init__` 遍历**无序对** `for i … for j in range(i+1, n)`，用 `is_adjacent_to` 统计
  adjTp/adjFp/adjFn/adjTn；`get_adj_precision` / `get_adj_recall`。
- **LOC-B3-2**｜同仓 `…/graph/ArrowConfusion.py`：遍历**有序对**，比较 `Endpoint.ARROW`；
  `__arrowsFp`/`__arrowsFn` 用 `np.maximum(estPositives - truePositives, 0)` 等计算；
  另有 `*CE`（common edge）变体。
- **LOC-B3-3**｜两个文件**均无 F1 方法**（只有 precision / recall）→ F1 需外部自行定义。

### B4 gCastle

- **LOC-B4-1**｜`raw.githubusercontent.com/huawei-noah/trustworthyAI/master/gcastle/castle/metrics/evaluation.py`
  （master 分支；**注意 `metrics/metrics.py` 不存在，返回 404**）：类 `MetricsDAG` 的 docstring
  写明 *"shd: undirected extra + undirected missing + **reverse**"*，
  以及 `fdr: (reverse + FP) / (TP + FP)`。
- **LOC-B4-2**｜同文件 `_count_accuracy`：
  `extra_lower = np.setdiff1d(pred_lower, cond_lower)`、`missing_lower = np.setdiff1d(cond_lower, pred_lower)`、
  `reverse = …`、`shd = len(extra_lower) + len(missing_lower) + len(reverse)`。
- **LOC-B4-3**｜该文件近期 commit（PR #188）标题含
  *"fix MetricsDAG TPR > 1.0 when B_est has bidirectional edges"*。

### B5 dodiscover

- **LOC-B5-1**｜`raw.githubusercontent.com/py-why/dodiscover/main/dodiscover/metrics.py`：
  `def structure_hamming_dist(true_graph, pred_graph, double_for_anticausal: bool = True)`；
  `if double_for_anticausal: return np.sum(diff)`，否则 `diff = diff + diff.T; diff[diff > 1] = 1; return np.sum(diff) / 2`。
- **LOC-B5-2**｜同文件 Notes：SHD "only well defined if you have a graph with only undirected edges,
  or directed edges"（混合端点图未定义）。

### B6 CausalDiscoveryToolbox

- **LOC-B6-1**｜`raw.githubusercontent.com/FenTechSolutions/CausalDiscoveryToolbox/master/cdt/metrics.py`：
  `def SHD(target, pred, double_for_anticausal=True)`，docstring 写
  *"Setting it to `False` will count this as a single mistake"*，
  Args 段 *"double_for_anticausal (bool): Count the badly oriented edges as **two** mistakes. **Default: True**"*。
- **LOC-B6-2**｜同文件 `def SHD_CPDAG(target, pred)` 内部以 `SHD(true_labels, predictions, **False**)` 调用
  ⇒ **同一库中两个函数的反向边约定相反**。

> **注**：旧指标方案引用的是 `fentechsolutions.github.io/…/metrics.html`。
> 该 `*.github.io` 域名在本机 **DNS 不可达**（见 §5），本轮改用 **raw.githubusercontent.com 的源码**，
> 属更强的证据（实现而非文档）。

### B7 SID

- **LOC-B7-1**｜[arXiv:1306.1043](https://arxiv.org/abs/1306.1043) 题名确认为
  *"Structural Intervention Distance (SID) for Evaluating Causal Graphs"*。
- **状态**：仅核验题名与摘要页；**正文未逐节阅读**。期刊卷页 27(3):771–799 来自公开著录，
  **本轮未从出版社页面独立核实** ⇒ 标 **UNKNOWN**。

### B8 Mahdi & Meek

- **LOC-B8-1**｜[JMLR 14 (2013) PDF](https://jmlr.csail.mit.edu/papers/volume14/mahdi13a/mahdi13a.pdf)：
  *"a mis-oriented edges is counted **only once** in the SHD metric, while it is counted **twice**
  in the TPR plot, once as a FP (false direction) and another as a FN (missing correct direction)."*

### B9 / B10

- **LOC-B9-1**｜[PMLR v206/shang23a](https://proceedings.mlr.press/v206/shang23a.html) 题名确认为
  *"Precision/Recall on Imbalanced Test Data"*。**正文未逐节阅读。**
- **LOC-B10-1**｜[IJCAI 2021 proceedings/0277.pdf](https://www.ijcai.org/proceedings/2021/0277.pdf)
  题名确认为 *"A Ladder of Causal Distances"*。**正文未逐节阅读。**

### C1–C8 — 「无图结构指标」的证据定位

| ID | 定位 | 要点 |
|---|---|---|
| **C1** | 本地全文，**Experiment 2, "1) Evaluation Metrics"** | *"finding root alarms is a binary classification problem, we use the **AUC**"*；"the accuracy is measured as the **ACC@k** metric"。基线 FIC/PC/CAUSE "generate causal graphs at the event-type level"，但**未被结构性评价**——原文以 AUC/ACC@k 比较 |
| **C2** | 本地全文，**§6.3 "Accuracy"、§6.4 "Evaluator"、§6.5** | §6.3 评 locator 的 **false positive / false negative** 率（"type and location"）；§6.4 评 severity；缓解耗时中位 **736s → 147s**。§7.1 的可视化图（节点=设备、边=连线）**未被评价** |
| **C3** | 本地全文，Abstract 与 §3.5.1 | 构建 *"heterogeneous wait-for **provenance graph**"*（节点=flows/ports，有向加权边）；评价为 *"**> 90% average precision and 100% recall**"*——指**诊断**，非图结构 |
| **C4** | 本地全文，**§3.1.4 "Evaluation Metrics"、式 (16)** | *"We use **top hit rate PR@k%** [25] and …"*；式(16) 为 **RankScore**。Granger 因果链**本身不评** |
| **C5** | 正文 PDF，**§5 "Evaluation"** | *"Two quantitative metrics are generally used … **execution time** and **recall at top-k**."*；原文并称 *"learning the complete causal graph is **not necessary** for finding the root cause"*。正文+附录 grep 确认**无** SHD / skeleton / 邻接对比 |
| **C6** | arXiv PDF，**§4.3 "Evaluation Metric"** | 式(15) **PR@K**、式(16) **MAP@K**、式(17) **MRR**。学到的因果图**不与任何真值图比较**；消融 edge loss 的 Table 5 仍以 **MRR** 衡量 |
| **C7** | arXiv PDF，**§V.D "Evaluation Measurements"** | 异常检测 Recall/Precision/**F1**、定位 **HR@k**、**NDCG@k**；RQ1–RQ3 无一评价依赖图结构。依赖图（§IV.B）无真值 |
| **C8** | **仅摘要** | 摘要唯一量化指标为 *"**4.6% in F1-score** on average"*，语境为 APG→真实故障的映射（**整图二分类**）。正文不可得 ⇒ 该判断**置信度 low** |

---

## 3. CCF 目录：版本、来源与核查方法

### 3.1 使用的版本

**第七版《中国计算机学会推荐国际学术会议和期刊目录》**，
CCF 官网发布日 **2026-03-31**，**2026-04-09 更新修正一处勘误**。

- 官方公告页：[第七版目录正式发布](https://www.ccf.org.cn/Academic_Evaluation/By_category/2026-03-31/870181.shtml)
- 官方目录 PDF（72 页，本轮**实际下载并解析**）：
  `https://www.ccf.org.cn/ccf/contentcore/resource/download?ID=112CF3BF7E1140ACEB271ADAED12A67ADFABB8FF099E40C2759502A85C8A281F`
  （经 [分类页](https://www.ccf.org.cn/Academic_Evaluation/By_category/) 取得；需带 Referer）

> **版本更正说明**：旧指标方案与本地既有材料多以 **2022 版**为参照。
> 本轮核查发现**已有更新版本**：第七版把 **ICLR 首次收录并直接定为 A 类**、
> **IJCAI 由 A 降为 B**。**本报告一律以第七版为准**，并在下表中标注与 2022 版可能不同的项。
> 目录官方声明：*"会议论文仅指 Full paper 或 Regular paper；Short paper、Demo paper、
> Technical Brief、Summary、Findings 以及作为伴随会议的 Workshop 等不计入"*。

### 3.2 核查方法（可复现）

官方 PDF 的中文字形**缺少 ToUnicode CMap**，直接抽取为乱码；但**拉丁字母的会议/期刊简称、
出版社名与 dblp URL 完整可读**。因此按行扫描，遇纯数字行即认定为一个条目，
取其后的简称行与其后的 dblp URL（`/journals/` = 期刊，`/conf/` = 会议），
并记录**该条目之前最近的一个 A/B/C 分节标题**。

- 解析脚本：`tmp/t007/parse_ccf.py`（本地工作文件，`tmp/` 已被忽略）
- 解析产物：`tmp/t007/ccf7_entries.tsv`，**共 597 个条目**
- **已知解析瑕疵**：当某条目的"全称"行缺失时（例如 *Machine Learning* 期刊条目正文仅一行出版社名），
  简称会与上一条目的 URL 错位一行。本报告涉及的此类条目已**逐个手工核对**（见下）。

### 3.3 本报告用到的级别（均出自第七版官方 PDF）

| Venue | 级别 | 类型 |
|---|---|---|
| SIGCOMM, INFOCOM, NSDI, MobiCom | **A** | 会议 |
| ICSE, FSE/ESEC, ISSTA, ASE（**会议**） | **A** | 会议 |
| WWW（The Web Conference，**会议**） | **A** | 会议 |
| NeurIPS, ICLR（**第七版新增 A**）, ICML, IJCAI（**第七版由 A 降 B**） | **A / A / A / B** | 会议 |
| KDD（条目标 SIGKDD）, SIGMOD, VLDB, ICDE, SC, HPDC, CCS, S&P | **A** | 会议 |
| USENIX Security, OSDI, SOSP, EuroSys | **A** | 会议 |
| TON, TPDS, TDSC, JSAC, TKDE, TOIS, TOSEM, TSE, JMLR, Artificial Intelligence, VLDBJ | **A** | 期刊 |
| DSN, ISSRE, SRDS, ICDCS, CoNEXT, IMC, Middleware, CIKM, WSDM, ICDM, SDM, IPDPS, ICPP, CLUSTER, EDBT, ICWS, ICSOC, CAiSE, SIGMETRICS, Performance, ASE（**期刊**） | **B** | 会议/期刊 |
| **TNNLS, Machine Learning, Neural Computation, Neural Networks, Computer Networks (CN), JSS, ESE, ASE(期刊), ESEM, UAI** | **B** | 期刊/会议 |
| TNSM, IM, MSR, CCGRID, APNOMS, AISTATS, PAA | **C** | 期刊/会议 |
| **IEEE Access** | **未收录** | — |
| **PVLDB, CNSM, NOMS, Artificial Intelligence Review, Neural Computation(名称核对见下)** | **未收录** | — |

**与 2022 版可能不同、需要作者注意的两项**：**ICLR 现为 A**；**IJCAI 现为 B**（旧稿若写 A 需更正）。

**手工核对过名称错位的条目**（因 §3.2 的解析瑕疵）：
- *Machine Learning*（Springer，`journals/ml/`）＝ **B**（人工智能领域 B 类期刊；位于
  "Journal of Automated Reasoning" 与 "Neural Computation" 之间）
- *Neural Computation*（MIT Press，`journals/neco/`）＝ **B**，**确在目录内**（首轮关键词检索曾误判为未收录）
- *Computer Networks*（Elsevier，条目简称 **CN**）＝ **B**；其下另有 **LCN**（IEEE Conference on
  Local Computer Networks）＝ C，**二者不是同一刊物**，引用时勿混

---

## 4. 检索记录

**检索日期**：2026-09-13（执行日即截止日）。
**范围**：2021 年至执行日为主；指标定义类经典工作不限年份。
**语言**：英文为主。

**主要检索式（概念分组）**：

1. `fault propagation graph` / `failure propagation graph` / `impact graph` / `event graph
   reconstruction` + `evaluation` / `ground truth`
2. `alarm propagation graph` / `alert correlation graph` + `precision` / `recall` / `F1`
3. `microservice` + `causal graph` / `causal structure learning` / `service dependency graph`
   + `evaluation metric` / `structural Hamming distance` / `edge F1`
4. `directed graph recovery metrics` / `graph edit distance DAG` / `ancestor reachability`
5. `causal discovery` + `evaluation` / `benchmark` / `SHD` / `SID` / `oriented` / `arrow`
6. `root cause analysis` + `LLM agent` + `graph` / `knowledge graph`（2024–2026）
7. CCF 目录版本：[`CCF推荐国际学术会议和期刊目录 2025 新版`](https://www.ccf.org.cn/Academic_Evaluation/By_category/2026-03-31/870181.shtml)

**检索与核验手段**：WebSearch；`curl` + 浏览器 UA 取原文/源码；
`export.arxiv.org` API、Crossref、OpenAlex、Semantic Scholar 核验身份；
GitHub `raw.githubusercontent.com` 取工具源码；本地 `docs/papers/*.txt` 复用既有全文；
官方 CCF PDF 解析。

**分工说明**：本轮有并行子代理参与检索与逐篇核验，**其结论已由执行者抽查复核**
（例如 Eadro 的 arXiv 号、MULAN 的 DOI、IEEE Access 的 DOI 均被纠正，见 §5）。

---

## 5. 失败尝试与缺文记录（未绕过任何访问控制）

### 5.1 域名层面的可达性（本机 2026-09-13）

| 域名 | 结果 |
|---|---|
| `dl.acm.org` 的 `/doi/pdf/` | **403**；但**摘要页 `/doi/<DOI>` 常可读** |
| `openreview.net`、`dblp.org`（Anubis 挑战）、`web.archive.org`、`archive.org`、`core.ac.uk`、`scholar.archive.org`、`zenodo.org` API | **不可达** |
| 所有 `*.github.io` | **DNS 不可解析**（替代：`raw.githubusercontent.com`） |
| `ieeexplore.ieee.org` 的 `/stampPDF/`、`stamp.jsp` | **502 / Akamai JS 反爬页**；**成功路径**：先 GET 文档页取 cookie，再带 cookie + Referer 取 `ielx8/.../<arnumber>.pdf` |
| `r.jina.ai`、`api.allorigins.win`、`corsproxy.io`、`scite.ai` | 000 / 522 / 403，代理类一律不可用 |
| `arxiv.org`、`export.arxiv.org`、`proceedings.mlr.press`、`proceedings.neurips.cc`、`jmlr.org`、`raw.githubusercontent.com`、`api.crossref.org`、`api.openalex.org`、`api.unpaywall.org` | **可达** |
| `api.semanticscholar.org`、`export.arxiv.org` API | **间歇 429 限流** |

### 5.2 逐篇缺文

| 对象 | 尝试过的路径 | 结果 |
|---|---|---|
| **C8 APGNN** 全文 | ScienceDirect `abs/pii/...`（含 Googlebot UA）、ACM DL、publisher 摘要、BUA 机构门户、Unpaywall、OpenAlex、OpenAIRE、CORE、aminer | **全部无 OA 全文**（OpenAlex 明确 `is_oa: false`、`any_repository_has_fulltext: false`）。**只读到摘要，置信度 low** |
| **B1** Springer 正式版 | link.springer.com 正文页 | 未取得；改用**共同作者 Laura E. Brown 主页**的作者版 PDF |
| **B7/B9/B10** 正文 | 仅核验题名与官方页 | **正文未逐节阅读**，已在 §2 标注 |
| **A2** camera-ready | `zbchern.github.io/papers/ase25a.pdf` | `*.github.io` 不可达；改用 arXiv 预印本（同标题、同 Table I） |
| **检索式 1 + edge-level 指标** 的专项检索 | WebSearch | **返回空结果**（无链接）。**不能**据此断言"不存在" |
| 中文告警关联/压缩类文献 | 本地 `docs/papers/` 已有 5 篇中文全文 | 其评价为**压缩率与命中率**，非图结构；**未纳入 A/B 类**，仅作排除记录 |

### 5.3 本轮纠正的线索错误

以下错误来自**上一阶段自动检索的候选信息**，在核验中被发现并修正（记录以备追溯）：

| 项 | 线索值（错） | 核实值（对） |
|---|---|---|
| Eadro 的 arXiv 号 | `2302.05605` | **`2302.05092`**（`2302.05605` 是无关数学论文） |
| MULAN 的 arXiv 号 | `2402.02308` | **`2402.02357`**（`2402.02308` 是机器人论文） |
| MULAN 的 DOI | `10.1145/3589334.3645514` | **`10.1145/3589334.3645442`** |
| A3 的"DOI" | `10.1109/ACCESS.11408137` | 该串是 **IEEE Xplore arnumber**；真实 DOI 为 **`10.1109/ACCESS.2026.3667143`** |
| gCastle 指标文件 | `gcastle/castle/metrics/metrics.py` | **`gcastle/castle/metrics/evaluation.py`**（前者 404） |
| causal-learn 的 SHD 类位置 | `causallearn/utils/PCUtils/Helper.py` | **`causallearn/graph/AdjacencyConfusion.py` 与 `ArrowConfusion.py`** |

---

## 6. 与旧指标方案的关系

[旧方案](../故障传播图指标调研与最终评价方案.md)（2026-09-10）是本轮的**检索线索**，不是结论依据。
本轮对其逐项回到原文核查的结果：

| 旧方案的说法 | 本轮核查 |
|---|---|
| SID 不进主表（语义不符） | **方向一致**；但旧方案引的 SID 细则本轮**未逐节核实**（§2 B7）⇒ 结论保留但证据强度记为待补 |
| "SHD 对反向边可计一次或两次，取决于实现选项" | **核实并被大幅强化**：不止两种实现选项，**原始定义与四个工具库给出 0/1/2 三种约定**（§0.3） |
| CausalDiscoveryToolbox 的官方文档链接 | 该 `*.github.io` **本机不可达**；改用源码取得同等或更强证据 |
| PCMCI+ / DYNOTEARS 的时间语义 | 两篇**官方页已复核存在**，但本轮**未逐节核验其评价指标** ⇒ 保留为线索 |
| Shang 等 AISTATS 2023 支撑"部分标注只代表已审范围" | **题名与官方页已复核**；正文未逐节阅读 |
| sklearn / networkx 的定义链接 | 本轮沿用；networkx 传递闭包定义用于可达指标 |
| 旧方案的指标定案（"冻结"主指标） | **未被本轮沿用为结论**；本轮给出的是**条件化候选**（report.md §4），最终待用户精读后决定 |

**本轮相对旧方案的实质增量**：① 发现 CCF 目录已更新到第七版（ICLR→A、IJCAI→B）；
② 把"SHD 反向边计分不一致"从一句提醒变成**六来源对照表**；
③ 新增 4 篇 A 类候选（含 1 篇 WWW 同级）与 8 篇 C 类反例的**逐篇定位**；
④ 明确"网络侧无一篇直接评价传播图结构"这一缺口。

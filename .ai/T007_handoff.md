# Handoff — T007 图评价指标的文献依据调研

> **Work 独立验收补记（2026-09-13）：部分通过，需按 [R1–R7](T007_acceptance.md) 返修。**
> 当前任务为 T007-R，尚未执行；下文保留执行者原交付记录，其中“文献工作完成”并未获完整验收。
> 已确认 NEC 的局部原因关系评价、CausIL 真实数据代理图、A4 的 mask 引用和 SHD 对照存在误读；
> ErrorPrism 比例/定位及部分文献身份也需修正。原“网络侧无先例”“SHD 反向=0/1/2”概括撤回。
> 两份核心报告尚未由本轮改写；最终指标仍待用户精读后决定，先完成定点返修再交付阅读包。

From：Claude Code（执行）。To：用户 / Work 审核。
日期：2026-09-13。状态：**调研已交付，待 Work 验收；最终指标待用户精读后决定。**

> **结论分层（请勿合并成一句话）**：
> **文献工作：完成** ｜ **网络侧直接证据：无（已如实说明）** ｜ **指标：候选已给，未定案** ｜
> **项目数据/标签缺口：未变，本任务不阻塞也不解决**。
>
> 上一轮 T006/T006-R 交接完整保留在 [T006_handoff.md](T006_handoff.md)（未删改）；
> 其证据摘要保留在 [T006_evidence.md](T006_evidence.md)。
> 本 T007 任务书原件：[T007_research_task.md](T007_research_task.md)。

---

## 1. 你应读哪几篇，能据此考虑哪些指标

产物：[report.md](../docs/conferences/WWW2027/graph_metrics_literature/report.md)（结论与建议）、
[sources.md](../docs/conferences/WWW2027/graph_metrics_literature/sources.md)（来源与定位）。
**本报告不替你选定指标，也不给推荐排序。**

### 1.1 最值得读的 5 篇

| # | 论文 | 为什么读它 | 先读哪里 |
|---|---|---|---|
| 1 | **CausIL**（WWW '23，CCF-A） | 唯一明确把图指标拆成**"忽略方向的邻接"与"考虑方向的箭头"两套 P/R/F1**，再配 SHD。与你"方向对不对"的核心问题同构，且 venue 同级。 | §5.3（p.6）→ Table 3（p.10） |
| 2 | **ErrorPrism**（ASE '25，CCF-A） | **生产环境 + 人工逐条逆向核验的真值路径**，按 hop 分层。是"真值怎样才能可信"的范本。 | §IV-A3 + 式(2)(3)（p.7）→ Table I |
| 3 | **Tsamardinos 等 2006**（Machine Learning，CCF-B） | **SHD 的原始定义**：定义在 PDAG 上，反向边**计 1**。不读它无法判断任何"SHD=几"的对错。 | §9.1.4 + Algorithm 4（作者版 PDF p.22–23） |
| 4 | **Semi-Supervised & Disentangled Causal Discovery**（IEEE Access 2026，**CCF 未收录**） | 唯一把**故障传播**建成服务级有向 DAG 并用**归一化 SHD（含反向边项）+ 方向敏感 F1** 评价的工作。但真值由启发式构造，**作者自承有偏**——反面教材。 | §V-B-1、§V-B-2（p.30619–30620）→ **§VI-C-1 Threats to Validity** |
| 5 | **Retrofitting Service Dependency Discovery**（arXiv 预印本，**补充来源**） | 边级 P/R/F1；**真值取自应用架构定义**，并**显式说明"运行期不可观测的依赖不该算错"**——与你的 unknown/allowed 语义直接相关。 | §VI-A + Table I |

**其余**：C1–C8（NetEventCause、SkyNet、Hawkeye、FaultInsight、RCD、MULAN、Eadro、APGNN）
建议**只看 report.md §1.3 的表格**即可——它们的价值在于"**建了图却不评图**"这一共同模式，
不必逐篇精读。

### 1.2 你据此可以考虑哪些指标

- **可直接采用的**：**有向边 P/R/F1 的案例宏平均**（CausIL 的 AH、A3 的式(17)、A4 的 Table I
  都用方向敏感的边级 P/R/F1）；**"邻接（忽略方向）与方向必须分开报"**这一分解（CausIL §5.3）。
- **需满足条件或适配的**：**`SHD-1`**（本项目建议命名）——形式可借 A3 的
  `normalized SHD = (E+M+R)/T`（含反向边项），但**只能在完整图标签子集上用**，
  且**必须显式声明反向边计 1、图类型为 DAG**。
- **仅作背景的**：SID（B7）、GED（B2 已说明需区分自由度）、单独 coverage。
- **不适合当前主张的**：邻接 F1 单独作为主指标（整条边反向时仍给满分，report.md §3.3 例 2）。

### 1.3 最该知道的一条硬发现

**"SHD"不是同一个指标。** 逐源码/原文核实：反向边计分在
**原始定义=1、gCastle=1、causal-learn ArrowConfusion=2、dodiscover 默认=2、CDT 默认=2
（同一库的 `SHD_CPDAG` 却是 1）** 之间不一致；bnlearn 的 `shd()` 更是**先把两张图转成 CPDAG** 再算。
⇒ 若不写明约定，SHD 数字**不可比**。报告 §0.3 有六来源对照表。

---

## 2. 核验范围

**已做**：

- 逐篇核到**可读一手全文/源码**：CausIL(arXiv PDF)、ErrorPrism(arXiv PDF)、
  A3(IEEE Access publisher PDF)、A4(arXiv)、Tsamardinos(作者版 PDF)、
  bnlearn(CRAN 手册)、CDT / causal-learn / gCastle / dodiscover（**GitHub 源码**）、
  Mahdi & Meek(JMLR PDF)、RCD(正文+附录 PDF)、MULAN(arXiv PDF)、Eadro(arXiv PDF)。
- 网络侧 4 篇复用**本地已有全文**（`docs/papers/*.txt`），给可检索短锚点。
- **CCF 目录改用官方第七版（2026-03-31）**：下载官方 72 页 PDF 并解析出 **597 个条目**，
  自查级别；`tmp/t007/parse_ccf.py`、`tmp/t007/ccf7_entries.tsv`（`tmp/` 已忽略）。
- 指标证据定位：sources.md §2 逐条给出**页/节/表/公式/函数名**。

**未做 / 缺口（如实记录）**：

| 缺口 | 影响 |
|---|---|
| **网络侧未找到任何"实验直接评价传播图结构"的论文** | 结论不可外推为"不存在"；检索以英文为主，专项检索曾**返回空结果** |
| **C8 APGNN 仅读到摘要**（无任何 OA 副本，OpenAlex 确认 `is_oa:false`） | 其"无图结构指标"判断**置信度 low** |
| **A4 为预印本**，未查到正式发表版本 | 仅作补充来源；其"方向是否参与匹配"未交代 |
| **B7 SID / B9 Shang / B10 Peyrard&West 正文未逐节阅读** | 只核到题名与官方页，已在 sources.md 标 UNKNOWN |
| **B1 Springer 正式版未取得** | SHD 定义引自作者版 PDF，与期刊分页未逐页比对 |
| 中文告警关联类文献未系统检索 | 本地已有 5 篇中文全文，评价均为**压缩率/命中率**，非图结构 |

---

## 3. 交付物

| 产物 | 说明 |
|---|---|
| [graph_metrics_literature/report.md](../docs/conferences/WWW2027/graph_metrics_literature/report.md) | **主产物。** §0 先读一页（5 篇 + 硬发现 + 候选前提）→ §1 论文对照表（A/B/C）→ §2 重点精读卡 ×5 → §3 指标比较与手算图例 → §4 两套条件化组合 + 选择理由草稿 → §5 不推荐的用法 → §6 局限 |
| [graph_metrics_literature/sources.md](../docs/conferences/WWW2027/graph_metrics_literature/sources.md) | 论文身份/链接/全文版本、**逐条指标证据定位**、CCF 版本与核查方法、检索记录、失败与缺文、**纠正的 6 处线索错误** |
| [WWW2027/README.md](../docs/conferences/WWW2027/README.md) | 新增 T007 专题入口 |
| [docs/README.md](../docs/README.md) | 「实验与评价」新增入口（并注明**不取代**现行协议） |
| [T007_research_task.md](T007_research_task.md) | 本任务书原件 |
| [T006_handoff.md](T006_handoff.md) / [T006_evidence.md](T006_evidence.md) | **新增存档**，T006 交接与证据的当时快照（逐字节一致，未删改） |

---

## 4. 命令与验证

| 项 | 结果 |
|---|---|
| 新增文档编码 | 全部 **UTF-8 无 BOM**（`report.md` 39,653 B；`sources.md` 29,350 B） |
| 新增文档相对链接 | **7 条，0 失效**（`tmp/t007/check_links.py`） |
| 索引改动后链接 | `docs/README.md`、`WWW2027/README.md` 新增链接均指向已存在文件（已复核路径） |
| 存档一致性 | `cmp` 逐一通过：T006_handoff / T006_evidence / T007_research_task **与原件逐字节相同** |
| 项目测试套件 | **未运行**（任务书 Acceptance #7 明确要求不运行） |
| 训练 / 推理 / 重评分 / 外部 LLM API | **未运行** |
| PDF 批量下载 / 复现 | **未运行**（按既有约束，此类程序在服务器执行） |

本机执行的程序仅为：文档链接与编码检查、CCF 官方目录 PDF 的解析（只读）、
以及为核验原文而做的**单篇**取文（PDF 转文本用 PyMuPDF）。**未绕过任何访问控制**。

---

## 5. 未改动的东西

算法、标签、评测代码、运行协议、正式论文、实验数字、baseline、`data/`、`tmp/` 下既有原始材料
均**未改动**。旧[指标方案](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)
**正文一字未改**，只在新产物中标注"它是检索线索、不是本轮结论依据"。
**`GPT_BRIEF` 未更新**——按任务书，其调研结论由 Work 验收后再写。
T001–T003、T006-R 的 U1–U5 收尾**均未启动**。**未提交、未推送。**

---

## 6. 待决问题（需你 / Work 决定）

1. **是否采用"有向边 P/R/F1 + `SHD-1`"这类组合？** 其中 `SHD-1` 依赖**完整图标签**，
   而本项目完整标签的比例与来源独立性仍是 **UNKNOWN**（PROJECT/STATUS B02）。
2. **是否把"区分邻接与方向"定为报告的强制项？**（CausIL 的 Adj/AH 分解）
3. **是否需要在论文中把"网络侧普遍不评价图结构"写成研究缺口？**——
   本轮证据支持这个观察，但**专项检索返回过空结果**，措辞需保留余地。
4. **是否需要补取 A4 的正式发表版本、C8 的全文？**（若补到，可能改变 §1 的取舍。）
5. **SID / PCMCI+ / DYNOTEARS 是否需要补做逐节核验？** 本轮只核到题名与官方页。

---

## 7. 建议的下一步

1. **你精读 §1.1 的 5 篇**，重点是 CausIL §5.3 与 A3 §V-B-2 两处的指标定义，
   以及 **A3 §VI-C-1** 的自承偏差段。
2. 精读后**确定 1–2 个主指标**，再交由 Work 决定是否更新 `GPT_BRIEF` 与
   [图评价协议](../docs/conferences/WWW2027/故障传播图指标调研与最终评价方案.md)
   （协议正文本轮**未改**，可在你定案后另开任务）。
3. 若倾向 `SHD-1`，**前置条件是 T001 的完整图标签审计**（STATUS B02）。

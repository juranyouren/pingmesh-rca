# Handoff — T005 WWW 2024–2026 网络论文原文调研与 Web relevance 方案

From：Claude Code（执行）。To：用户 / Work 审核。

> **2026-09-12 当前任务已改为 T006，READY、尚未执行。** 用户要求复盘作者如何把具体 Web
> 需求推进到网络问题；执行入口为 [CURRENT_TASK](CURRENT_TASK.md)。本文件保留 T005 交接，
> 原任务已存入 [T005_research_task.md](T005_research_task.md)，勿从下方旧方案排序恢复当前优先级。

> **2026-09-11 Codex 独立验收：部分通过，需返修。** 以下保留执行者原交接，
> 其中全部抽取 QA 通过、Web 相关性分类及推荐理由不能直接采纳。
> 具体证据、更正和返修任务见 [T005_acceptance.md](T005_acceptance.md)。
> 用户确认目前只知道数据来自华为云 DCN，具体承载业务未确认；正式定位仍未选定。

**先读什么**：[positioning_options.md](../docs/conferences/WWW2027/web_relevance/positioning_options.md)
——三套候选定位、对比表、首选/备选/暂不推荐，以及 5 个需要你决定的问题。
方案尚未选定；**本轮不重写正式论文，不宣布定位已定**。

上一轮 T004 的交接记录完整保留在 [T004_handoff.md](T004_handoff.md)（未删改）。

---

## 1. 数量对账

| 项 | 数量 | 说明 |
|---|---|---|
| 检索年份 | 3（2024/2025/2026）+ WWW 2027 CFP | 官方目录逐条解析：2024 405+51；2025 IW3C2 存档 TOC 443 条；2026 676+57 |
| 纳入深读 | **14 篇** | 核心集 8 + 相邻集 4 + 对照集重叠 2（按集合去重后 14） |
| PDF 取得并验签 | **14 / 14** | `%PDF` 头 + `%%EOF` + 首页题名核验，SHA-256 已记录 |
| 全文抽取成功、无需 OCR | **14 / 14** | 双栏阅读顺序正确；需 OCR 的页 = 0 |
| 独立 Introduction 材料 | **14 / 14** | 起止边界、P1..Pn、页码定位，逐篇目视核对 |
| 逐篇分析卡 | **14 / 14** | 结构一致，含页/节/表定位与三类证据标注 |
| **全文未取得** | **13 篇** | 见 H-1；均为 ACM 单一公开位置 + 机器人拦截 |
| 新增/修改的跟踪文件 | 1（`docs/conferences/WWW2027/README.md` 增加专题入口） | 其余为新增 |

**未运行**：训练、推理、重评分、项目测试套件、外部 LLM API。**未提交、未推送。**

## 2. 成功项

- 三年官方录用目录全部解析成功（含 2025 年——会议站点 TLS 已损坏，改用 IW3C2 官方存档）。
- WWW 2027 Research Track CFP 的 scope 与 relevance 条款按**原文引用**核验并注明抓取日期。
- 14 篇深读全部走完：PDF 验签 → 全文抽取 QA → Introduction 定位 → 逐篇论证拆解。
- 归纳出四类真实存在的 Web relevance 论证方式，并给出跨论文对照矩阵。
- 提出三套有实质差异的定位方案（差异在主要问题、服务对象、论证链与所需证据，非换标题）。
- 更正了旧调研的 3 处结论（见 H-3），原文档保留原样。

## 3. 失败项与获取限制

### H-1：13 篇仅有 ACM 单一公开位置，未能取得全文

`www24-ares`、`www24-satguard`、`www25-x-clusterlink`、`www25-miresga`、`www25-ipdb`、
`www25-merkury`、`www26-meteor`、`www26-beeqos`、`www26-wiseswap`、`www26-starlink-dns`、
`www26-tracellm`、`www26-dc-forecast`、`ind26-smart-eye`。

原因统一：Unpaywall / OpenAlex / Crossref / Semantic Scholar 四家一致报告 gold OA (CC-BY)，
但每篇 `locations[]` **只有一条**且均为 `dl.acm.org`；该站对本机自动化请求返回 403。
arXiv 按题名、系统名、作者名三路检索均无预印本。

**处置**：记为"身份已核验、全文未取得"，**未用摘要或第三方页面补成全文分析**，
**未绕过访问控制**（未编写 Anubis 工作量证明求解器、未用无头浏览器穿透 Cloudflare）。
这 13 篇不进入横向矩阵；其对结论的影响已在 [synthesis.md](../docs/conferences/WWW2027/web_relevance/synthesis.md) §7 说明。

**补全方式**：用普通浏览器下载后放入 `tmp/www-web-relevance/pdf/`，命名与
[manifest §6.2](../docs/conferences/WWW2027/web_relevance/paper_manifest.md) 的 `paper_id` 一致。
清单见 `tmp/www-web-relevance/DOWNLOAD_NEEDED.md`。

### H-2：检索入口不可达（记录在案，未绕过）

`dl.acm.org` / `dlnext.acm.org` 403；`dblp.org` Anubis 挑战；`openreview.net` 403；
`*.github.io` DNS 不解析（改用 `raw.githubusercontent.com` 取同一文件）；
`web.archive.org` / `archive.org` / `core.ac.uk` 超时或 403；`zenodo.org` API 403。

### H-3：对旧调研的更正（逐项依据见 synthesis §5）

1. **MULAN**：旧调研称其有"领域级 Web 关联"。核验后——正文 "web" 仅出现在参考文献。
2. **MetaKube**：旧调研称"对具体 Web 工作负载的关联较 WiseStart 间接"。核验后——
   正文 "web" 仅出现在版权行与 K8s 术语 "admission webhooks"，**基本不存在**。
3. **InArt**：旧调研称其"证明底层网络支撑 Web 工作负载是可用路径"。收窄——
   仅领域命名；CCS Concepts 不含 Web 类别；附录 B 自述相关评测被省略、实验规模缩至 1/1000。

### H-4：抽取 QA 的已知噪声

部分 arXiv 版式的图形坐标轴标签与作者块会混入 Introduction 区域。
已在 `extract_intro.py` 中按题注/邮箱/机构/脚注模式二次过滤，残余噪声在分析卡中按"非正文"处理。
**未因此把任何论文标为"已读完"而未核对**；14 篇的起止边界均逐篇目视核对过。

## 4. 核心结论

1. WWW 网络论文的 Web relevance 有**四种强弱不同的建立方式**：测量对象即 Web（最强，成本最高）／
   指标绑定（中）／领域命名（弱）／背景钩子（最弱）。**四种均有 Research Track 录用先例。**
2. 最强的一篇 `www26-starlink-cd` 的 Web 关联是**承重的**（去掉 "web" 技术主张不成立），
   但它需要平台级测量数据与跨洲自建终端——**本项目不具备这些前提**。
3. `www26-jittersketch`（骨干网流量、弱 Web 论证）被录用，说明 Research Track 不强制真实 Web 系统；
   但**先例 ≠ 安全垫**（看不到审稿意见与落选稿件；官方 relevance 是硬性 desk-reject 条款）。
4. **对本项目可行的是方式 B（评价指标定义成 Web 运维语义）与方式 C（领域命名 + 机制差异）。**

## 5. 方案排序与理由

| 排序 | 方案 | 理由 |
|---|---|---|
| **首选** | **A 基础设施定位** | 唯一在现有证据下**不虚构任何事实**即可成文；轨道归属有官方文本明文支持；补证成本最低（一份脱敏部署依赖说明）。弱点（关联仅到基础设施层）应如实承认 |
| **备选** | **C 结构不确定性** | 与现有资产匹配度最高，C1/C2/C3 是可证伪的科学主张，科学贡献最扎实。代价是 Web relevance 最弱。**A 与 C 可合并**：A 提供定位，C 提供科学问题 |
| **条件性** | B 可核验解释 | 仅在能获得 ≥1 个真实 incident 与工程师任务数据时可行；否则其评价主张无法成立 |
| **暂不推荐** | 面向 Agentic Systems 的 LLM 证据接口 | 项目约束禁止实验调用外部 LLM API；为贴题加 agent 补不上服务关联证据；属"仅替换术语" |

对比表与逐方案的证据表、审稿质疑见
[positioning_options.md](../docs/conferences/WWW2027/web_relevance/positioning_options.md)。

## 6. 待决问题（需用户 / Work 决定）

1. 是否补齐方案 A 所需的**部署依赖说明**？（A 与 B 的共同前提；不能补则 A 降级为纯背景。）
2. 是否接受**方案 C 的 Web relevance 风险**？（不接受则 C 只能作为 A 的科学内核。）
3. 是否有条件做**工程师任务实验**？（决定 B 是否可行。）
4. 是否进一步获取 **H-1 的 13 篇**？其中 Meteor / BeeQoS / Wiseswap / X-ClusterLink / Miresga
   属核心 DCN/云网络，可能改变 synthesis §3 的"无公开观测面"判断。
5. `www26-starlink-cd` 的 "PoP 距离解释 50% 方差" **在正文中找不到支撑**，
   若拟引用该论文作为模板须先澄清。

## 7. 本任务是否完成 vs 定位是否选定（分别记录）

- **T005 执行层面：已完成。** 检索、获取、抽取、Introduction 整理、逐篇分析、跨论文综合、
  三套方案均已交付，产物状态见 [专题 README](../docs/conferences/WWW2027/web_relevance/README.md)。
  唯一未完成的子项是 H-1 的 13 篇全文（外部访问限制，已如实记录）。
- **定位层面：未选定。** 方案排序是执行者建议，**最终由用户／Work 讨论后决定**。
  GPT_BRIEF 由 Work 验收后压缩更新。

## 8. 修改的文件

| 文件 | 变更 |
|---|---|
| `docs/conferences/WWW2027/README.md` | 增加 T005 专题入口段（含对旧结论的更正的提示） |
| `docs/conferences/WWW2027/web_relevance/` | **新增**专题目录：README、paper_manifest、cfp_www2027、synthesis、positioning_options、`papers/<id>/analysis.md` × 14、`papers/_TEMPLATE.md`、`tools/` × 3 |
| `.ai/HANDOFF.md` | 本文件（T005 交接） |
| `.ai/T004_handoff.md` | **新增**：原 HANDOFF.md 的 T004 内容原样保留 |
| `.ai/STATUS.md` | 更新当前优先项与 Next Actions |
| `.ai/CURRENT_TASK.md` | 仅更新 T005 状态行，指向 HANDOFF 与专题 README |

**未改动**：算法、标签、评价协议、实验数字、基线、`docs/conferences/WWW2027/` 下的既有文档
（原调研文档保留原样，更正逐项记录在 synthesis §5）。

## 9. 验证命令与结果

| 命令 | 结果 |
|---|---|
| 全库本地 Markdown 链接检查（`docs/` + `.ai/`） | **214 条链接，0 条失效** |
| 新增文档编码检查 | 全部 UTF-8，无 BOM |
| 14 份 PDF 验签 | `%PDF` 头 + `%%EOF` + 首页题名，全部通过 |
| 全文抽取 QA | 14/14 成功，`pages_needing_ocr` 均为空 |
| Introduction 边界核对 | 14/14 目视核对 PDF 首页、Introduction 首尾、下一节边界 |

**未运行**：项目测试套件（本任务不改代码，按任务书"不运行项目测试套件"），
训练/推理/评分，外部 LLM API。

## 10. 原始材料位置

`tmp/www-web-relevance/{raw,pdf,txt,meta,intro}/`（仓库忽略目录，不随摘要传递）。
共享文档一律用 `paper_id` 引用，不写入内部主机名或绝对路径。
`tmp/www-web-relevance/verify_pdfs.py` 为一次性验签脚本，保留在忽略目录。

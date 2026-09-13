# T005 / T006 — WWW 2024–2026 网络论文原文调研与 Web relevance 认知

> 执行日期：2026-09-11（T005 资料建设）、2026-09-12（T006 论证链复盘）。
> **状态：论文复盘已完成；证据有限；定位待讨论。**
> 定位**尚未选定**——"定位未选定"不等于研究未做。

> **2026-09-12 T006 更新：**当前结论入口是下面两份新产物。
> [synthesis.md](synthesis.md) 与 [positioning_options.md](positioning_options.md)
> **保留历史，其结论已被取代**：旧四类强弱框架不再作为归纳框架，
> 旧 A/B/C 方案排序不再作为当前推荐。两者正文未改，顶部已加被替代指针。

## 这个专题回答什么

RPG-Recon 投 WWW 2027 Research Track 时，"Web relevance" 该怎么建立？
本专题不靠转述摘要，而是把 WWW 近三年网络相关论文的 **PDF 取下来、全文抽出来、
Introduction 单独定位、逐篇拆解论证结构**，再从证据归纳出可迁移与不可迁移的部分。

## 按需阅读（建议顺序）

| 顺序 | 文件 | 读它解决什么问题 |
|---|---|---|
| 1 | [argument_chains.md](argument_chains.md) | **先读这个。** 直接回答"作者怎样把 Web 与这个具体网络问题连起来"：逐篇 4–7 节点论证链、关键句对照表、证据止点，末尾横向归纳 |
| 2 | [rpg_recon_argument_transfer.md](rpg_recon_argument_transfer.md) | 把上面的论证步骤接到 RPG-Recon：**2 条正式候选 + 1 条条件性补充**、中文草稿、最小补证表、最强反对意见、可写边界。**不排序、不给推荐** |
| 2b | [T006_R_response.md](T006_R_response.md) | T006 独立验收 R1–R8 的**逐项应答与核对依据**；想知道"哪一处改了、为什么改、哪一处没改"读这个 |
| 3 | [cfp_www2027.md](cfp_www2027.md) | 官方 CFP 的 scope 与 relevance 条款（原文引用），以及官方**没有**说什么 |
| 4 | [paper_manifest.md](paper_manifest.md) | 候选、去重、检索入口与失败记录、下载/抽取/阅读状态对账；§T006 为复用表与定向补取结果 |
| 5 | `papers/<paper_id>/analysis.md` | 单篇论证分析卡（14 篇），含页/节/表定位；本次复核更正见各卡末节 |
| 6 | [papers/_TEMPLATE.md](papers/_TEMPLATE.md) | 分析卡的结构与证据标注规则 |
| — | [synthesis.md](synthesis.md)、[positioning_options.md](positioning_options.md) | **历史文件，结论已被 1 取代。** 仅在需要追溯 T005 原始推理时阅读 |

## 核心发现（一句话版，T006 版）

> 以下取代旧的"四类强弱方式"结论；旧的五条一句话版保留在
> [synthesis.md](synthesis.md) §8 的原文中，不再作为当前结论。

1. **没有一篇论文写"网络是 Web 的基础"。** 它们把桥搭在**具体对象 × 具体失效条件**上
   （一条指标、一个交付机制、一份生产负载、一类终端行为），而不是"类别关系"。
2. 归纳出**六种桥接动作**（B1 假设破坏 / B2 指标绑定 / B3 具名生产负载 /
   B4 依赖链 / B5 对象即 Web / B6 应用类别命名），每种都有原文例句与锚点。
   **它们不是强弱阶梯**，且一篇论文可同时使用多个。
3. **作者怎么写（A）、工作负载提供了什么联系（B）、实验证明了什么（C）必须分开报**。
   三者可以完全不一致：`www24-inart` A 有链 B 无 Web 负载 C 停在训练通信；
   `www24-mulan` A 无 B 有 C 在 Web 系统上验证了排名。
   **C 栏问的是"在什么对象上证明了什么"，不是"是否测了页面指标"**（R5）。
4. **本轮唯一的坏消息**：可完整复核的 DCN 论文只有 `www24-inart` 1 篇，
   它给出的是**"Web 动机驱动、但非 Web 专用"**的链——
   P5 之后的前提是架构属性，且**未验证具名 Web 服务与服务侧收益**。
   **这一层是否还有别的写法，本轮的证据回答不了。**
5. **替换检查的用法被更正（R6）**：它**只用来说明适用范围**，
   **不能判定 Web 关联的强弱**。初稿用"换成地面 ISP 后整个问题消失"给
   `www26-starlink-cd` 判"承重"——该反事实**被原文自身否定**
   （Benin / Madagascar 的地面 ISP 用户同样被送到欧洲服务器）。
   承重与否改用"对象是否就是 Web 交付机制"判定。
   **"未测服务收益"、"非 Web 专用"、"没有实质联系"是三个不同结论**，
   不能互相替代。

## T006 的三条结论分层

| 层面 | 状态 |
| --- | --- |
| **论文复盘** | **已完成**：所选论文的关键句、承接、证据止点已按原文还原（[argument_chains.md](argument_chains.md)） |
| **证据范围** | **有限**：DCN 只有 1 篇可复核；补取结果见 [manifest](paper_manifest.md) §T006 |
| **定位** | **待讨论**：迁移报告只说明每条候选链"现在能写到哪里"，不给推荐排序 |

## 产物状态

| 产物 | 状态 |
|---|---|
| 三年官方目录解析 | 完成（2024: 405+51；2025: 443 条 TOC；2026: 676+57） |
| WWW 2027 CFP 核验 | 完成，官方原文已引用并注明抓取日期 |
| 深读论文 | **14 篇**：PDF 齐全、全文抽取、Introduction 定位**均已逐篇完成**。**T006-R 更正**：抽取 QA 的实际状态是——**页码标记与段落边界可用，但 Intro 段落编号存在已知污染**（见 `argument_chains.md` §1.2），且**未做逐页视觉 QA**（本机无 `pdftoppm`）。"文件可读"与"逐页版面核对过"是两件事 |
| 单篇分析卡 | 14 篇，结构一致，含页/节/表定位与三类证据标注；**4 篇**已追加 T006 复核更正 |
| 跨论文综合 | **已被取代**（T005 版：矩阵 + 四类论证方式）；当前版见 `argument_chains.md` §6 |
| 定位方案 | **已被取代**（T005 版：3 套 + 1 套暂不推荐）；当前版见 `rpg_recon_argument_transfer.md`（**条件性候选，不排序**） |
| **T006 论证链复盘** | **已交付，验收为"部分通过、需返修"**；已按 R1–R8 修正（2026-09-12）。6 篇逐篇还原 + 纵向六种桥接动作，见 `argument_chains.md` |
| **T006 迁移分析** | **已交付并重写**（2026-09-12）：**2 条正式候选 + 1 条条件性补充**（原"3 条候选链 + 首选"的写法已撤销，见 `T006_R_response.md` R8） |
| **T006 分析卡复核** | 4 篇就地更正（inart / wise-start / jittersketch / mulan），其余篇目保留未决状态 |
| **未取得全文** | **13 篇**。**T006-R 更正**：不能说"原因统一为 ACM 机器人拦截"——应逐篇记录实际失败点。T006 复核到的差异：`dl.acm.org` 的**摘要页**本次可访问而 `/doi/pdf/` 仍不可用；`www24-ares` 的 `download_batchA.tsv` 记 CLOSED/is_oa=false 与 gold OA 记录**冲突且未解决**；机构仓库在本机被网络策略拦截（非站点问题）。逐篇记录见 manifest §T006.2。**未绕过访问控制** |

## 复跑命令

> **执行环境（T006-R 更正）**：本任务书要求**批量下载、PDF 转换与相关程序在服务器执行**，
> **本地仅做任务、文档与摘要协作**。下面的命令**记录的是工具用法**，
> **不代表本轮在本机执行过**——T006 / T006-R 两轮**未运行任何 PDF 转换或批量下载**。
> 上一版 README 写"在仓库根目录（Windows，使用现有 Anaconda Python + PyMuPDF）复跑"，
> 与任务书的服务器约束不一致，已更正。

```bash
# 1) 解析官方录用目录 HTML → TSV
python docs/conferences/WWW2027/web_relevance/tools/parse_accepted_listings.py \
       tmp/www-web-relevance/raw/www2026_research.html \
       tmp/www-web-relevance/meta/www2026_research.tsv

# 2) PDF → 带页码标记的 UTF-8 文本（双栏阅读顺序 + 段落重建）
python docs/conferences/WWW2027/web_relevance/tools/pdf_to_text.py \
       tmp/www-web-relevance/pdf/www26-starlink-cd.pdf \
       tmp/www-web-relevance/txt/www26-starlink-cd.txt

# 3) 定位 Introduction 并编号 P1..Pn
python docs/conferences/WWW2027/web_relevance/tools/extract_intro.py \
       tmp/www-web-relevance/txt/www26-starlink-cd.txt \
       tmp/www-web-relevance/intro/www26-starlink-cd.intro.md \
       --title www26-starlink-cd
```

**工具说明**

| 工具 | 作用 | 已知限制 |
|---|---|---|
| `tools/parse_accepted_listings.py` | 解析 2024 / 2026 两种会议站点标记结构 | 只读本地快照，不联网 |
| `tools/pdf_to_text.py` | 双栏阅读顺序、段落重建、去除表格/坐标轴噪声、页码标记 | 部分 arXiv 版式的图形标签与作者块仍可能混入正文；已在 `extract_intro.py` 中按题注/邮箱/机构/脚注模式二次过滤 |
| `tools/extract_intro.py` | 定位 Introduction 起止、编号段落、给页码定位 | **已知会产生污染**：贡献 bullet 的换行被计为段落、作者块/页眉混入正文、部分论文的 §2 被整节并入（14 篇中至少 4 篇受影响，见 `argument_chains.md` §1.2）。上一版 README 写"起止边界逐篇目视核对过"，**该声明不成立，已撤回**。**引用 Intro 段落前必须按 PDF 或抽取文本页码标记复核**；若换用其他会议模板需重调 |

**原始材料位置**（仓库忽略目录，不随摘要传递）：
`tmp/www-web-relevance/{raw,pdf,txt,meta,intro}/`。
共享文档一律用 `paper_id` 引用，不写入内部主机名或绝对路径。

## 边界与提醒

- **ACM DL 403**：`dl.acm.org` 与 `dlnext.acm.org` 对本机自动化请求返回 403（机器人校验）。
  本专题**没有绕过**该机制；13 篇仅有 ACM 单一位置的论文因此未取得全文。
  若需补全，请**用普通浏览器**下载后放入 `tmp/www-web-relevance/pdf/`，
  命名与 [manifest §6.2](paper_manifest.md) 的 `paper_id` 一致。
- **页码版本**：多数深读使用 arXiv 预印本或作者稿，**其页码 ≠ ACM 正式版页码**。
  每张分析卡记录版本；引用页码时须注明。
- **未取得全文的 13 篇不进入横向矩阵**，其对结论的影响在 [synthesis.md](synthesis.md) §7 说明。
- 本专题**不含**任何性能实验、模型训练或评分；**未修改**实验数据、标签或既有评价协议。
- 历史调研文档
  [WWW近三年网络相关论文检索与投稿契合分析](../WWW近三年网络相关论文检索与投稿契合分析.md)
  **保留原样**，其结论的确认与更正逐项记录在 [synthesis.md](synthesis.md) §5。

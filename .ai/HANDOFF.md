# HANDOFF — T008 相关工作全面检索与可核验文献目录

任务：[T008](CURRENT_TASK.md)　执行：Claude Code　日期：**2026-09-15**
状态：**主要交付已完成**；覆盖缺口已在产物中如实标注（见 §6、§7），**未标为全部完成**。
分支：`graphrebuild`（未提交、未推送）

> T007 的 HANDOFF / EVIDENCE 已按要求**原样存为**
> [T007_handoff.md](T007_handoff.md)、[T007_evidence.md](T007_evidence.md)，本文件为 T008 版本。

---

## 1. 交付物

全部位于 `docs/conferences/WWW2027/related_work_catalog/`：

| 文件 | 内容 | 状态 |
|---|---|---|
| `README.md` | 入口、三层范围、字段与状态说明、维护方式 | ✅ |
| `catalog.xlsx` | `Papers`(306) / `Pending`(13) / `Coverage`(204) / `Venues`(204)；冻结表头、自动筛选、可点击链接 | ✅ |
| `catalog.csv` | 与 Papers 一致的 UTF-8(BOM) 主表，29 列 | ✅ |
| `index.md` | 按层次→主题组织的索引，306 条 | ✅ |
| `search_log.md` | 实际执行的通道、查询、引文轮次、更正记录 | ✅ |
| `coverage_report.md` | 分层/年份/等级统计、覆盖矩阵、缺口 G1–G11、停止依据 | ✅ |
| `evidence.md` | 逐条身份来源、等级出处、19 条题名更正 | ✅ |
| `screening.csv` | 13 条待核实线索及具体理由 | ✅ |
| `papers/*.md` | **16 张**核心近邻阅读卡 | ✅ |

## 2. 结果摘要

| 指标 | 数值 |
|---|---|
| 候选线索 | 319 |
| **身份已核实** | **306** |
| 待核实 | 13 |
| 含 DOI | 241 |
| 取得摘要 | 47 |
| 题名与旧线索冲突并更正 | **19** |
| 分层 | L1 195 / L2 64 / L3 47 |
| CCF | A 108 / B 40 / C 11 / 预印本 36 / 非正式轨道 11 / 未收录 91 / 待核实 9 |

## 3. 做法（可复现）

解析流水线（脚本在 `tmp/t008/`，`tmp/` 已被忽略）：

1. `merge.py` — 合并 8 个并行检索主题的 TSV + 既有种子 → `candidates_all.tsv`（327 条）
2. `resolve.py` — DOI 直取 / Crossref 题名检索 / OpenAlex 检索
3. `verify_url.py` — 出版方页面 `citation_*` 元数据
4. `resolve2.py` — arXiv ID 恢复 + Crossref `query.title`
5. `resolve3.py` — 改用 curl（Python SSL 在 usenix/arxiv 上失败）+ 短题名前缀匹配
6. `adjudicate.py` — 8 条具名论文人工裁定
7. `abstracts.py` / `abstracts2.py` — 摘要获取（严格题名匹配）
8. `ccf_map.py` — CCF 第七版等级映射（解析自官方 PDF，597 条）
9. `build.py` → `emit.py` → `check.py`

**关键设计**：所有元数据由提供方记录产生，**不手抄**。系统名与正式题名混淆、
短题名存缴、轨道继承等问题均由流水线显式处理并记录，而不是静默覆盖。

## 4. 命令

```powershell
& tmp/baselines-venv/Scripts/python.exe tmp/t008/merge.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/resolve.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/verify_url.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/resolve2.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/resolve3.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/adjudicate.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/abstracts.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/abstracts2.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/ccf_lookup.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/coverage.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/build.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/emit.py
& tmp/baselines-venv/Scripts/python.exe tmp/t008/check.py
```

## 5. 验证

`check.py` **29 项全部 PASS**，0 失败：

- 8 个顶层文件 + 16 张阅读卡存在
- 全部 Markdown/CSV 严格 UTF-8 解码通过
- `catalog.csv` 306 行；`paper_id` 唯一且非空；241 个 DOI **无重复**
- 必填字段（题名/venue/年份/等级/链接/层次/主题）无静默缺失（venue 空 6 条，已标待核实）
- 每行都有身份核验来源
- `screening.csv` 13 行，全部标「待核实」且有处置理由；与 Papers 的 ID **不相交**
- `catalog.xlsx` 四表齐全；Papers 306 行、冻结 `A2`、自动筛选生效、链接列 306 条可点击
- **xlsx / csv / index.md / evidence.md 的 paper_id 集合完全一致**
- 目录内 Markdown 本地相对链接 **0 失效**
- 阅读卡 paper_id 与题名均能对上 catalog

**未运行项目测试**（按任务要求只做产物检查）；未运行训练/实验/评分/数据审计。

## 6. 重要事实性发现（需 Work 决策是否采纳）

1. **必须撤回的旧概括**：「网络侧没有传播关系评价」。
   NetEventCause 已有事件级局部原因关系的 ACC@k 与参考关系对照（T007 R1 已认定），
   APGNN 的题名本身就是「告警传播图」。
   正确表述：未查到与本项目**同粒度、同输出对象**的完整设备 DAG 指标先例。
   **这不自动构成 novelty。**
2. **最强的直接近邻是两篇 2026 预印本**，不在数据库老论文中：
   - **PropLLM**（arXiv:2606.00582）逐跳回溯传播路径 + 拓扑因果先验 —— 输出是链不是图
   - **EvoCause**（arXiv:2607.27290）LLM 演化因果图，用 **Node F1 / Case EM / Graph F1 / nSHD**
     评价，并发布 **TeleRCA**（485,681 告警事件，专家标注）
3. **三处系统名 ≠ 正式题名**（旧材料误作题名）：COLA、REASON、CORAL。
   其中 REASON 与 CORAL 的正式题名与旧记录**完全不同**；
   COLA 与另存条目**实为同一篇**，已合并。
4. **跨领域已有可对照的图评价实践**：CausIL(WWW'23) 报 Adj/AH/SHD；
   ProAlert(PACMSE'25) 用传播路径做告警摘要；ErrorPrism(ASE'25) 以路径 exact-match 评价。
   本文图指标应引用这些**同类输出**的工作。
5. **一条对我方评测设计有利的独立依据**：*Complexity at Scale*（arXiv:2504.13141）
   用阿里生产追踪数据证明**调用图高度时变、依赖长尾**，直接挑战「依赖图固定」的假设。

## 7. 问题与风险

| ID | 问题 | 影响 |
|---|---|---|
| P01 | **APGNN 全文未取得**（`is_oa: false`，无任何 OA 副本）。该文题名与本文最接近 | 无法判断其是否评价图结构；只能说 UNKNOWN |
| P02 | 259/306 条仅核验元数据，**未读正文** | `论文自身输出对象` 与 `与本文关系` 是检索线索，已在列名与 README 中明确标注 |
| P03 | `coverage.py` 的 Crossref 探测是**相关性排序而非精确过滤**，`n_records` 不是出版量 | 已在 `Coverage` 表与覆盖报告中标注局限，**不据此做覆盖率声明** |
| P04 | OpenAlex source 级逐年统计**未完成**（配额耗尽） | 真实逐年覆盖仍缺；缺口 G4 |
| P05 | NSDI 在 Crossref 探测中 12 年零命中，**实为来源未收录**而非无结果 | 已在覆盖报告中纠正该失真 |
| P06 | ACM Computing Surveys 未在官方目录解析结果中定位 | 3 条记「待核实」；缺口 G3 |
| P07 | 中文期刊系统性检索未完成（无可自动化通道） | 仅 4 条，其中 1 条置信度低；缺口 G5 |
| P08 | 本地全文缓存 `docs/papers/*.txt`（48 个）已从工作区删除，**按任务要求未恢复** | 本轮内容核验只能依赖一手页面；T007 轮次的定位已按验收更正后带入阅读卡 |
| P09 | **既有失效链接（非本轮引入）**：`docs/PC-STGR设计方案.md` 已被删除（未提交的工作区删除），但 **7 个文件**仍链接到它，包括 `docs/conferences/WWW2027/README.md`、`.ai/PROJECT.md`、根 `README.md`、`docs/README.md` 等 | 本目录内链接 0 失效；该失效在 `HEAD` 中已存在。**未擅自改指向**——如何处置属用户/Work 决定 |

## 8. 未修改的内容

- **未改动** T007 的 `graph_metrics_literature/report.md` 与 `sources.md`（其 R1–R7 返修仍属 T007-R）
- **未改动** 任何算法、标签、评分协议、实验数字、baseline 选型结论
- **未改动** 正式论文 related work；只在 WWW2027 索引添加入口

## 9. 建议的下一步

1. **Work 验收 T008**：重点看 `coverage_report.md` §4 缺口与 §6 发现，
   判断「撤回旧概括」与「两篇 2026 预印本构成直接威胁」是否成立。
2. **最高优先补全文**：APGNN（缺口 G1）与 PropLLM / EvoCause 全文。
   后者直接决定本文 novelty 的表述边界。
3. **恢复 T007-R**：其指标返修与本目录**不冲突**，可并行；本目录已把 T007 的更正带入阅读卡。
4. **配额重置后**重跑 `coverage2.py` 补 OpenAlex source 级逐年覆盖（缺口 G4）。
5. 本任务未提交、未推送；是否提交由用户决定。

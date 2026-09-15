# Evidence Pack

更新：2026-09-13。范围：T006-R 二次验收；来源行号对应 [复验快照](T006_R_acceptance.md) 的版本。
此包压缩已完成的定点核查，不复制论文原文。当前结论：部分通过，U1–U5 待收尾。

## C001 — 多数原文纠错已落实，R5/R8 可以关闭

- **Priority:** P2
- **Claim:** 连续依赖链、数据来源及效果层次的主要更正已经落在正文，推荐排序已撤销。
- **Source / Locator:** [主报告](../docs/conferences/WWW2027/web_relevance/argument_chains.md) 207–210、233、298–302、559–570、660–669 行；[迁移稿](../docs/conferences/WWW2027/web_relevance/rpg_recon_argument_transfer.md) 29–30、273–287 行。
- **Finding:** InArt 恢复连续链；JitterSketch 恢复缓冲控制；CDN 数据分两来源；MULAN/GAMMA 保留诊断效果、未测业务收益；无首选排序。
- **Interpretation:** 接受对应修改，不把未解决的迁移问题扩大成所有交付失败。
- **Confidence:** HIGH
- **Verification Need:** NONE（本快照已定点核查；版本变化后只查相关段落）
- **Ambiguity:** 卡片及入口摘要尚有旧句，见 C004；并非全部原文逐页视觉 QA。

## C002 — 双指标报告仍被错误用作评价效度质疑的答案

- **Priority:** P1
- **Claim:** 原 R3 仍有实质残留。
- **Source / Locator:** [迁移稿](../docs/conferences/WWW2027/web_relevance/rpg_recon_argument_transfer.md) 216、238–239、308 行。
- **Finding:** 前文称双指标都报告后才回应自证质疑，后文又承认重评不能证明指标对应真实任务。
- **Interpretation:** 内部冲突；双指标只描述输出维度，不能替代独立关系标注、匹配比较或任务测量。
- **Confidence:** HIGH
- **Verification Need:** TARGETED（收尾后复核这些段落）
- **Ambiguity:** 图质量/可追溯性分列和使用者实验控制已改善，无须回退；见复验 U1。

## C003 — 共同原因限制被倒置，部分未知仍被升级为事实

- **Priority:** P1
- **Claim:** 多症状不推出多传播的限制无需先排除共同原因；场景与标注状态仍需收窄。
- **Source / Locator:** [迁移稿](../docs/conferences/WWW2027/web_relevance/rpg_recon_argument_transfer.md) 67、81–93、145、199–200 行；[PROJECT](PROJECT.md) Dataset；[STATUS](STATUS.md) 本地数据摘要。
- **Finding:** 正确限制被附加排除共同原因的前置条件；未知覆盖仍标已有；标注独立性未核实被写成标注不存在。
- **Interpretation:** 共同原因的可能性正是不能直接推出传播的理由；UNKNOWN 不等于不存在。草稿须直接修正，不能只靠后文限定。
- **Confidence:** HIGH
- **Verification Need:** TARGETED（收尾后复核 U2/U3 对应段落）
- **Ambiguity:** 本轮不判断具体案例属于哪种原因，也不审定现有标注独立性。

## C004 — 卡片、摘要和新增定位仍未完全同步

- **Priority:** P2
- **Claim:** 原 R1/R6/R7 的摘要同步和少量事实定位尚未关闭。
- **Source / Locator:** InArt 卡 135 行、JitterSketch 卡 90 行；主报告 234、310–311、397、502、641 行；专题 README 120–123 行，文件链接见 [复验 U4/U5](T006_R_acceptance.md)。
- **Finding:** 卡片留已撤回的无实质关联结论；InArt 问题设定归纳前后冲突；Starlink 将非洲大陆 PoP 误写欧洲；README 留统一 403 归因；新增页段与原顺序仍有偏差。
- **Interpretation:** 定点纠正即可，不需要全量重读。Starlink 地理事实已只用既有 TXT 第 166、617 行核对。
- **Confidence:** HIGH
- **Verification Need:** TARGETED（仅查 U4/U5 清单）
- **Ambiguity:** 全量 PDF 版面 QA、上游引用和下载历史未独立重验；这些不作为本轮收尾前置。

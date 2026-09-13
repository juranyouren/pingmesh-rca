# www24-encdns — A Worldwide View on the Reachability of Encrypted DNS Services

| 字段 | 值 |
| --- | --- |
| 年份 / 轨道 | 2024 / WWW Research Track |
| 正式题名 | A Worldwide View on the Reachability of Encrypted DNS Services |
| DOI | 10.1145/3589334.3645539 |
| 原始 PDF | www24-encdns.pdf（来源：author copy，ruixuanli.com；版本：author copy，PDF 第 1 页页脚含 "Corrected Version of Record. V.1.1. Published July 29, 2024."） |
| 抽取文本 | tmp/www-web-relevance/txt/www24-encdns.txt |
| Introduction 定位 | www24-encdns.intro.md，PDF 第 1–2 页，P1–P14（P4 版本声明，P14 脚注） |
| 深读状态 | 已深读（全文 535 行、PDF 10 页，含附录 A、B） |

## 1. 问题定义

研究对象是加密 DNS（论文统称 DoE，含 DoT/DoH/DoQ/DoH3）服务的全球可达性。输入＝15 个月全网扫描筛出的 1302 个 DoEv4 / 448 个 DoEv6 域名；输出＝5K+ VPs、102 国/地区的 10M DoEv4 与 560K DoEv6 查询的阻断率与七类阻断分布。【作者陈述】理由：可达性是客户端取得 DoE 服务的前提，而 DoE 可被滥用或绕过 DNS 监管，招致 ISP 阻断（P2，p.1）；作者点名的使用者是 DNS community（摘要 p.1）与 Internet community（第 6 节 p.8）。【本次推断】实际能支撑的是 DNS 提供商、客户端/OS 开发者与审查测量社区，无一条面向 Web 生态的建议。

## 2. Web 关联

判断：被测对象本身位于 Web 交付栈上，但分析完全停在 DNS 层。
- 对象 Web 相邻：DoH/DoH3 跑在 HTTP/2、HTTP/3 与 TCP/443、UDP/443 上（Table 1，p.2），DNS 解析是任何 Web 请求的第一步。
- 但无 Web 层指标：检索 web / page load / latency / performance，"performance" 只命中 2.1 节一句 DoT/DoH 因 TCP+TLS 开销受损（p.2，纯动机句，未测量）与两条参考文献标题。
- 命名实体只有 DNS 解析器/提供商（dns.google、8.8.8.8、Cloudflare、OpenDNS）与浏览器/OS（Chrome、Firefox、Android、Windows，P1，p.1），无任何 Web 服务名。
- 题名与正文不含 "Web" 字样；去掉 Web 术语，方法与结论一字不改。故属"对象维度"关联，非"用户可见 Web 体验"关联。

## 3. 段落作用（按 P1、P2……）

P1 背景+重要性；P2 缺口与挑战引入（可达性是前提；滥用与监管冲突致阻断；既有工作只测少量域或受限 VP，未系统评估阻断类型与 IPv6）；P3 两个挑战（缺全面 DoE 域名清单；阻断分布于协议栈多阶段）；P4 版本声明；P5–P8 方法三步；P9 RQ 列表，六问逐条锚定 Section 4.1–4.6，是全文骨架；P10–P12 主要发现；P13 影响与数据开源；P14 脚注界定 "China" 指中国大陆。属标准模板，特色是把贡献前移成 RQ 索引。

## 4. 现有工作与缺口

作者具体批评（P2，p.1；2.1 节末，p.2）：Lu et al. 只测 3 台公共服务器；Basso et al. 只分析 3 国 123 台；Hoang et al. 只测 12 个 DoT + 59 个 DoH、85 国/地区；Jin et al. 仅 DoT/DoH IP。缺口被限定为：(a) 样本小且未筛"可运营"服务器（引 [33,34]：大量开放服务器只是产物）；(b) VP 覆盖受限（本文 102 国 vs. 85 国，p.5）；(c) 未做阻断类型学、未测 IPv6。方法逐条对冲：(a)→15 个月扫描 + 四条可运营判据（正确响应/可用域名/有效证书/持续服务，p.3）；(b)→8 家商用 VPN + 大陆 2 台 EC2，5031 VPs；(c)→七类阻断与双栈并行。

## 5. 核心洞察与贡献

任务定义贡献：把 DoE 可达性重定义为"全域规模 × 从解析到响应全阶段 × 双栈 × 阻断类型学"，显式给出七类阻断（p.4，Figure 2/3）。方法实现贡献：可运营 DoE 服务器自动筛选（ZMap 扫描 + 证书 SAN 抽域名 + GTas/GTtitle/GTprompt 三重一致性检验，p.4–5），并剔除伪造 IP 与 VPN DNS 劫持节点（移除 324 个，p.4）。工程规模贡献：15 个月、10M + 560K 查询、5K+ VPs、102 国/地区。评价贡献弱：未同口径对齐、无召回评估，作者自认只得下界（附录 B，p.10）。立身之本＝测量规模 + 域名清单 + 阻断类型学，而非任何 Web 发现。

## 6. 证据强度

引言数字均有后文支撑：1302/448 域→Table 2（p.6）；5031/473 VPs→Table 3（p.6）；5.92%/4.91% 阻断率→4.2 节（p.6）与 4.4 节（p.7）；27.18%/19.73% 审查迹象→4.5 节（p.7）；"96/120"→4.6 节 Figure 8（p.8，正文为 25.53%/27.70%）。仅属动机：2.1 节"DoQ/DoH3 改善性能"（p.2）无任何测量。只测 X 却称 Y 的风险：4.5 节用五条判据推断审查，作者自认"未必等于审查、可能夸大"（p.7）；附录 B（p.10）承认无法区分阻断来自服务器还是中间件，且 VPN 多在数据中心故只得下界。阻断判定要求三次全中（p.5）会低估间歇性阻断且未量化。另一处不一致：摘要写 570K DoEv6 查询（p.1），正文 P7 与 4.4 节写 560K（p.2、p.7）。

## 7. 与本项目（RPG-Recon）的关系

可迁移的论证动作：把 Web 相关性挂在一个公共可观测的基础设施对象上，而非自有部署。本文的 vantage point 是 8 家商用 VPN + 5 台云控制节点，全是公开可买/可租的资源，不需要生产系统权限或用户群——它的 Web 相关性是廉价获得的（被测对象本身在 Web 栈上，观测点公网可得）。对我们的启示：若被测对象本身是公共基础设施（如 Pingmesh 异常与设备拓扑），就不必先拥有生产事故数据。
不可迁移的前提：(1) 它不需要标注——阻断与否由三源一致性自动判定；我们的传播 DAG 需要确认的根与边，而项目恰无现场调查记录与真实事故。(2) 贡献建立在 15 个月全网扫描 + 5K VP 的测量规模上，我们既无该基础设施也不做测量类贡献。(3) 数据是"域–IP–VP"阻断标签，与我们的"设备–告警–拓扑"合成 DEMO_001 无共享结构。
潜在重合：机制上几乎无重合；唯一同构的是证据纪律——GTas/GTtitle/GTprompt 与我们"每条边必须存在于原始 task_topo、unknown 关系 mask 而非转负例"同属"证据不足不下结论"；差异是它的判据为外部三源交叉可复现，我们为单源拓扑 + 标签不可见。

## 8. Reviewer 视角

去掉 Web 术语后论证完全不损失（题名与正文本就无 Web 框架词），而这正是风险：它是互联网测量/审查研究，与 WWW 的 Web 中心叙事只是对象相邻，坚持页面级口径的审稿人会认为它更适合 IMC/PAM。最可能被质疑的关联缺口：无任何 Web 层后果（阻断率升高对应 Web 发生了什么，全篇不答）；受益者写成 DNS community 而非 Web 生态。值得避免：把下界/相关性当结论而不量化偏差；用 VPN/数据中心节点代表普通用户位置（作者自认，附录 B）；讨论节建议只有自有 VP 上的一次实验，却在摘要里像可落地方案。

## 9. 原文定位索引

注：PDF 页码 + 1192 = 印刷页码。
- 摘要、P1–P3、版本声明：p.1；RQ→4.1–4.6 锚定：P9，p.2
- 2.1 节 + Table 1：p.2；第 3 节 + Figure 1：p.2–3；3.1 四判据：p.3；3.2 VP 与七类阻断（Figure 2）：p.3–4；阻断检测（Figure 3）+ 三重 ground truth：p.4–5
- 第 4 节 + Figure 4 + Table 2/3：p.5–6；4.2 Figure 5 与 AS 级阻断：p.6（Figure 9 见附录 A，p.9）；4.3 Figure 6：p.6–7；4.4 IPv6：p.7；4.5 审查五判据：p.7；4.6 Figure 7/8：p.7–8
- 第 5/6 节：p.8；附录 B：p.10

未找到：Section 3.1、4.1、4.2 的编号标题行在抽取文本中未作为独立行出现（已检索 `^4\.`、`^3\.` 与 "Section 4"），其编号仅由 P9（p.2）RQ 指针与 p.5/p.6 的 run-in 小标题确定。全文未找到任何 Web 页面加载/Web 性能/SLO 指标（已检索 web、page load、latency、performance、SLO、user experience）。

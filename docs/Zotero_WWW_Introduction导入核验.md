# Zotero：WWW Introduction 文献导入核验

> 核验日期：2026-08-25  
> 目标集合：`aiops/00_待分类`（collection key: `YATU543E`）  
> 写入原则：add-only，不移动既有成员关系，不修改元数据，不合并重复项。

## 1. 已完成：条目导入与集合核验

以下 11 篇论文已在本地 Zotero 中检索到，且均属于 `aiops/00_待分类`：

| Zotero key | 论文 | DOI | 状态 |
|---|---|---|---|
| `RLPXIZZ3` | GraphMAE2 | `10.1145/3543507.3583379` | 已导入并核验集合 |
| `T4GVT6PA` | MULAN | `10.1145/3589334.3645442` | 已导入并核验集合 |
| `RYRG5GKK` | GAMMA | `10.1145/3589334.3645665` | 已导入并核验集合 |
| `VZRKZHAZ` | MicroRank | `10.1145/3442381.3449905` | 已导入并核验集合 |
| `HU9DZG9V` | Adversarial Mask Explainer | `10.1145/3589334.3645608` | 已导入并核验集合 |
| `N967XNIH` | SEHG | `10.1145/3696410.3714661` | 已导入并核验集合 |
| `AIWMTB7B` | Eadro | `10.1109/ICSE48619.2023.00150` | 已导入并核验集合 |
| `IQGWL2YP` | Nezha | `10.1145/3611643.3616249` | 已导入并核验集合 |
| `MBW57TAV` | DiagFusion / Robust Failure Diagnosis | `10.1109/TSC.2023.3290018` | 已导入并核验集合 |
| `7AMA4K3C` | DejaVu / Actionable and Interpretable Fault Localization | `10.1145/3540250.3549092` | 已导入并核验集合 |
| `AEZQNXRH` | ShapleyIQ | `10.1145/3623278.3624771` | 已导入并核验集合 |

## 2. 尚未写入：标签与综述笔记

Zotero Local API 当前可读，但 `writeAuthorized=false`。授权请求曾等待 30 秒后超时，因此以下内容只是**待写清单**，不能视为已应用：

### 所有 11 篇

- `status/to-read`

### 技术前人工作

对象：MULAN、GAMMA、MicroRank、Eadro、Nezha、DiagFusion、DejaVu、ShapleyIQ。

- `role/related-work`
- `work/pc-stgr/related`

### WWW 写作样本

对象：GraphMAE2、MULAN、GAMMA、MicroRank、Adversarial Mask Explainer、SEHG。

- `role/writing-model`
- `work/pc-stgr/style`

### 方法参考

对象：GraphMAE2、Adversarial Mask Explainer、SEHG。

- `role/method-reference`

### 内容标签

- GraphMAE2：`method/self-supervised`、`method/graph`、`method/deep-learning`
- MULAN：`data/multimodal`、`method/causal`、`method/graph`、`method/deep-learning`
- GAMMA：`data/metrics`、`method/graph`、`method/deep-learning`
- MicroRank：`data/traces`、`method/statistical`
- Adversarial Mask Explainer、SEHG：`method/graph`、`method/deep-learning`
- Eadro、DiagFusion、Nezha：`data/multimodal`、`data/logs`、`data/metrics`、`data/traces`、`method/graph`、`method/deep-learning`
- DejaVu：`data/metrics`、`method/graph`、`method/deep-learning`
- ShapleyIQ：`data/traces`、`method/statistical`

### 待创建 standalone note

目标集合：`aiops/00_待分类`。  
内容来源：`docs/前人工作证据矩阵_WWW_Introduction.md` 的核心结论、方法分组、已支持局限、未验证缺口和检索盲区。  
建议标签：`work/pc-stgr/related`、`work/pc-stgr/style`、`status/to-review`。

## 3. 明确不执行

- 不把任何论文标记为 `status/core` 或 `status/excluded`；
- 不删除已有 `/unread` 等标签；
- 不将条目从 `00_待分类` 移出；
- 不合并 SkyNet 或其他重复条目；
- 不修改题名、作者、年份、DOI、URL 或附件。


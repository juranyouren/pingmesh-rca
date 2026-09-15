# Handoff — T004 仓库清理与文档索引

From：Claude Code（执行）。To：下一轮 Agent / 工程师。

任务书 [CURRENT_TASK.md](CURRENT_TASK.md)（T004）已执行完毕。本轮只做文档与缓存处置；
没有改动算法、评分语义、标签或实验数字，没有运行训练，没有提交或推送。

## 实际删除（53 个目录，约 10 MB，全部可自动再生）

| 类别 | 数量 | 依据 | 恢复路径 |
|---|---|---|---|
| `__pycache__/` | 51 | 仅含 `.pyc`；`.gitignore` 第 2 行 | 下次 import 自动重建 |
| `.pytest_cache/`（根 + labeler） | 2 | 仅含 pytest 记账（`lastfailed`/`nodeids`） | 下次 `pytest` 自动重建 |

依据与安全校验：每个目录都经过解析，确认 (a) 绝对路径位于本仓库内，(b) 未被 Git 跟踪，
(c) 内容只有 `.pyc` 或 pytest 自身文件。删除使用 PowerShell `Remove-Item -LiteralPath`，
逐项复核。`tmp/baselines-venv/` 内的 878 个缓存目录**未处理**（现有虚拟环境不属于清理目标）。

一次性辅助脚本保留在忽略目录：`tmp/t004_verify_cache_dirs.py`（枚举 + 校验，写清单）、
`tmp/t004_delete_caches.ps1`（复核后 `Remove-Item -LiteralPath`）。`tmp/t004_del.txt` 是
辅助脚本每次运行重新生成的清单，当前保存的是**最后一批**的路径。

上述 53 个目录是首批处置。随后为验证清理未破坏代码，执行了测试套件，测试运行按预期重建了
25 个缓存目录；这 25 个已用同一校验流程再次清除（当前工作区缓存目录数为 0）。
合计处置 78 个目录，全部为可自动再生的缓存。

## 实际保留（有明确依据，未删）

- 所有被跟踪文件：264 个 tracked 文件中**零删除、零移动**。全库内容去重扫描
  （MD5）显示没有内容重复的跟踪文件。
- `docs/f0.png`、`f1.png`、`f2.png`、`fig1.png` 及 2026-09-09 生成图：WWW 索引明确
  记录「本次保留并提交」，属旧示意素材，继续保留并从当前阅读路径分离。
- `Baseline/BiAn/`、`NetEventCause/`、`TraceRCA/`：`Baseline/README.md` 声明「保持原用途」，
  且被 `scripts/run_rca_baselines.sh` 引用。
- `pingmesh-propagation-labeler/.local/`：含 QA 截图与重建案例，唯一证据。
- `.ai/`、`data/`、`tmp/`、`output/`、`archive/`、未跟踪个人工作簿：全部保留。

## 新增索引

- **根 `README.md`（80 行）**：项目与两阶段方法、输入输出边界、主要目录表、
  文档入口表、Windows/Linux 运行入口、重要边界。关键资料至多两级可达。
- **`docs/README.md`（66 行）**：按「当前论文 / 方法实现 / 实验与评价 / 历史与参考」
  分类，链接到已有 WWW 索引与权威原文，不枚举单篇论文、不复制正文。

## 修复的失效引用

1. `docs/PC-STGR设计方案.md` — 指向已删除 `./论文方案.md` 的链接改为 WWW 索引 + 项目概览。
2. `docs/papers/相关工作_三类方法与缺口_INFOCOM版.md` — `../论文方案.md` 改为 WWW 索引。
3. `scripts/README.md` — 正文提到的 `docs/论文方案.md` 改为 WWW 索引。
4. `docs/project_overview.md` — 过时的 5 条 Immediate Priorities 替换为指向
   2026-09-10 执行记录的说明，并明确 **Oracle 已在 2026-09-08 运行过**，下一步是重评不是首跑。
5. `scripts/README.md` — 补充旧 evaluator（`evaluate_propagation.py`）语义尚未与新协议统一的提示。
6. `AGENT.md`、`CLAUDE.md` — 仅最小增量：补根 README / docs 索引入口，修正
   「项目概览仍含历史优先级」的表述。用户原有未提交修改完整保留。

`docs/论文方案.md` 是用户已删除文件，**未恢复**；相关入口已改指现存材料。

## 验证命令与结果

| 命令 | 结果 |
|---|---|
| `git diff --check` | 退出 0，无空白错误 |
| 本地链接检查（60 个 Markdown，含 `.ai/`） | **0 条失效** |
| `python -m pytest tests -q` | **206 passed**（与既有记录一致） |
| `python -m pytest pingmesh-propagation-labeler/tests -q` | **22 passed** |
| `python -m Baseline.common --help` | 退出 0 |

`git status --short` 显示 6 个已修改跟踪文件（本轮 4 个 + 用户原有 2 个）、3 个新增
未跟踪项（`README.md`、`docs/README.md`、`.ai/`）与个人工作簿。测试运行会重建
`__pycache__`/`.pytest_cache`，属预期。

## 待定文件（本轮保留，需用户决定）

1. **`.codex-tmp/`（22 MB）** 与 **`output/codex_intro_revision_tmp/node_modules`**：
   PPT 制作临时目录与依赖缓存。两者都没有 `package.json`/`package-lock.json`，
   无法保证可重建，因此**未删除**。若确认不再需要，可整体移除。
2. **`Baseline/RCAcopilot/`**：完整的 baseline 实现与自测，但不出现在
   `Baseline/README.md` 方法表、也不被任何 runner 引用。未确认冗余，保留。
3. **`.gitignore` 的 `/tests/*` 规则**：16 个真实测试文件（如
   `test_evaluate_propagation.py`、`test_stage2_m1_hypothesis_graph.py`）因此处于
   未跟踪状态，干净 checkout 无法复现本机 206 项测试集合。CLAUDE.md 已记录该现象。
   修复需要语义决策（是否全部纳入版本控制），本轮未改动。
4. **`.gitignore` 中 `agent/` 相关条目**：对应目录不存在，属无害的陈旧规则。

（`.ai/` 已于本次提交纳入版本控制，跟踪前已扫描确认无内部路径、主机名或 IP；
根 README 与本文档对它的链接因此在干净 checkout 下同样有效。）

## Recommendation

T004 的交付目标（简洁入口 + 已核实的冗余清理 + 引用修复）已达成，变更已提交到
`graphrebuild`（未推送）。研究侧证据缺口与 UNKNOWN 清单**不因本次清理而改变**：
T001 证据审计仍是下一步，按 STATUS 顺序推进。`/tests/*` 忽略规则建议由用户决定。

## 2026-09-11 独立验收补记（Codex）

验收对象：提交 `3c6c564`。结论：**主体交付通过，交接记录待补正；不作无保留关闭。**

- 提交差异仅涉及 Markdown；没有被跟踪文件删除或移动。两个 README 分别为 80 / 66 行，
  共 48 个链接目标均在本地存在，并可从 Git 跟踪文件到达。
- 本轮实际复验：主测试 **206 passed / 25.90s**；labeler **22 项成功、退出 0**；
  `Baseline.common --help` 退出 0。使用现有 CPU 环境，设置
  `PYTHONDONTWRITEBYTECODE=1`，pytest 加 `-p no:cacheprovider`；没有真实数据实验。
- 缓存盘点为 0（排除既有虚拟环境和 node_modules）。首批 53 个目录及约 10 MB 的删除
  属执行者报告：逐项清单未完整留存，不能独立重建历史处置或证明所有未跟踪文件原样保留；
  本次没有发现误删证据。
- 待修订：本文提交前后状态、两个 README 的“.ai 尚未入库”、STATUS 的未提交描述；
  `docs/README.md` 的 Pingmesh 链接须包裹含空格路径；根 README 的现有环境说明须限定
  为维护者工作区。主目录实际有 26 个测试文件，其中 9 个已跟踪、**17 个被忽略且未跟踪**，
  上文的 16 个需更正。完整测试集合仍不能通过干净 checkout 复现。
- 提交级 `git diff HEAD^ HEAD --check` 检出 GPT_BRIEF:47、STATUS:105 的末尾空白行；
  原先的工作树 `git diff --check` 通过不足以验证整个已提交交付。

用户在验收讨论中明确：**后续审计、重评分与实验在服务器执行，不在本地电脑执行。**
本地测试已在该回复前完成。下一任务建议为 T001-A：服务器只读证据清点与待签认审计包；
这是讨论建议，尚未启动或替换 CURRENT_TASK。完整源数据、逐例清单留在服务器，回传脱敏摘要。
标签语义、真实事故组和标注独立性需工程师确认，自动清点完成不等于证据已冻结。

> T004 历史任务书快照；2026-09-11 当前优先项已切换为 [T005](CURRENT_TASK.md)。

# Objective

**T004 — 清理仓库内不必要文件，建立简洁的文档索引。**

更新：2026-09-11。Owner：Claude Code。状态：**已完成（DONE）**，执行记录见文末。

验收状态（2026-09-11，Codex）：**主体交付通过，交接记录待补正**，详见 HANDOFF 的独立验收补记。

用户已将本任务设为当前优先项。原 T001 证据审计保留在 STATUS 的研究待办，不因调整优先级而标记完成。

# Motivation

仓库缺少根 README，入口分散在 AGENT.md、CLAUDE.md、项目概览及 WWW 索引；同时存在旧材料、生成物、失效引用和过时待办。需要让新成员或 Agent 快速找到当前方法、论文、实验及任务，减少误读历史方案。

# Hypothesis

维护性假设：清理有明确依据的冗余文件，并建立“根入口 → 分类索引 → 权威原文”的导航，可以降低查找成本和上下文冲突。此任务不产生新的科学结论或性能指标。

# Scope

1. 先盘点 Git 跟踪状态、未提交修改、文件用途和引用，形成具体的保留/删除/归档候选；执行后将处置及依据简要写入 HANDOFF，不另建庞大清单体系。
2. 清理已确认可再生且无依赖的缓存、临时副本和无用生成物；删除已确认冗余、无活跃依赖且可从 Git 恢复的旧文件。不能只凭文件名、修改时间或“没有被 import”认定无用。
3. 有研究追溯价值的旧论文材料、负结果和实验记录继续保留，但从当前阅读路径中分离；优先利用现有 archive 和专题索引，避免无必要搬迁。
4. 新建根 `README.md`：简述项目、当前两阶段方法、主要目录、文档入口与运行说明入口。目标不超过 80 行，避免复制配置和整套实验命令。
5. 新建 `docs/README.md`：按“当前论文 / 方法实现 / 实验与评价 / 历史与参考”组织精选链接，目标不超过 120 行；链接到已有 WWW 索引及权威材料，不枚举每篇论文。
6. 修复受影响的本地链接及活跃入口中的已确认过时引用；同步 `scripts/README.md`、项目概览等入口里的冲突待办，明确已做 Oracle 与当前 P0 主线。尽量链接现有说明，不重写论文内容。
7. 更新 `.ai/STATUS.md`、`.ai/HANDOFF.md`、`.ai/GPT_BRIEF.md` 和本任务状态。AGENT.md/CLAUDE.md 如需补入口，只作保留原有用户修改的最小增量。

# Constraints

- 保留数据、标签、预测、checkpoints、唯一实验依据、负结果、许可证、依赖锁定文件及当前代码/测试。`data/`、现有虚拟环境和模型缓存不属于默认清理目标。
- 不整目录删除 `tmp/`、`output/` 或 `archive/`；其中可能有唯一产物与验收证据。忽略规则不能作为文件无用的证据。
- 保留用户未提交修改、未跟踪的个人工作簿和来源不明的唯一文件。无法确认用途的文件标为待定，本轮保留；不添加反复确认流程来阻塞其余可执行工作。
- 不修改算法、评分语义、标签或实验数字；不恢复用户已经删除的过期方案；不启动模型、训练或真实数据重评分。
- 清理前核对引用及恢复路径；移动或删除 Windows 文件前验证解析后的绝对路径在本仓库允许范围内，使用 PowerShell 原生命令和 LiteralPath。禁止笼统 git clean、reset --hard 或跨 shell 批量删除。
- 内部数据及个人路径不进入新 README 或被跟踪摘要。未确认的事实继续标 UNKNOWN。

# Acceptance Criteria

1. 根 README 可直接找到当前任务、论文索引、方法概览、实验评价和运行入口；关键资料至多经过两级索引到达。
2. 根 README 与 docs README 简短、职责不同，当前材料与历史参考清晰分开；不重复复制大段正文。
3. 每个实际删除/移动都有文件级依据和恢复路径；没有删掉被运行入口、测试或当前文档依赖的文件。
4. 新增/改动索引的本地链接全部存在；受清理影响的引用已修复，无新失效入口。
5. 原始用户修改和唯一研究证据保留；Git 差异只包含有说明的清理与文档改动。
6. HANDOFF 报告实际清理/保留项、索引入口、验证命令与结果、待定文件；未执行的清理不得写成已完成。

# Verification

从仓库根目录执行，先记录初始状态，完成后再次对比：

```powershell
git status --short
rg --files --hidden -g '!.git' -g '!tmp/baselines-venv' -g '!__pycache__'
git diff --stat
git diff --check
```

对每个拟删除/移动文件，使用 `rg -n --fixed-strings` 检索其路径、文件名及可能的入口引用，再作决定。使用一次性 Python 标准库检查新增/改动 Markdown 的本地链接、编码及 README 行数，无需新增永久验证工具。

纯文档与无依赖缓存清理不新增测试、不运行长实验；若清理触及代码资产或可执行入口，运行对应现有测试/CLI help，并记录退出状态。验收后更新共享记忆，不自动开始 T001 或提交/推送。

# Execution Record (2026-09-11, Claude Code)

实际处置、依据与验证结果见 [HANDOFF.md](HANDOFF.md)。要点：

- **删除**：53 个纯缓存目录（51 个 `__pycache__` + 2 个 `.pytest_cache`），约 10 MB。
  全部未跟踪、内容仅 `.pyc` 与 pytest 记账文件、路径经解析确认位于仓库内。
  `tmp/baselines-venv/` 内 878 个缓存目录**未动**。无任何被跟踪文件被删除或移动。
- **新增**：根 `README.md`（80 行）、`docs/README.md`（66 行）。
- **修复**：3 处已确认失效的 `docs/论文方案.md` 引用；同步 `docs/project_overview.md`
  的过时 Immediate Priorities 与 `scripts/README.md` 的旧 evaluator 说明。
- **未删除（标为待定）**：`.codex-tmp/`、`output/codex_intro_revision_tmp/` 的
  `node_modules`（无 manifest，恢复路径不确定）；`Baseline/RCAcopilot/`（无活跃引用
  但为完整实现，未确认冗余）。见 HANDOFF「待定文件」。
- **不含**：未提交用户修改（AGENT.md/CLAUDE.md）、未跟踪个人工作簿、唯一研究证据均保留。
- **验证**：`git diff --check` 退出 0；60 个 Markdown 文件本地链接 0 失效；
  `python -m pytest tests -q` 206 passed；labeler 22 passed；`Baseline.common --help` 退出 0。

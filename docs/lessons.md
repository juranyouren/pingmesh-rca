# 开发过程中的关键教训

整理自 2026-06-10 至 2026-06-17 的调试过程。

---

## 1. 数据泄漏：永远不要让评分代码碰 label.json

**发现**：`temporal_score.py` 中的 `_read_label_timestamps()` 从 `label.json`（标注文件）读取根因设备的告警时间。非根因设备保持为空 → 算法天然区分了根因和非根因 → 76% 是泄漏，不是信号。

**教训**：任何一个读 `label.json` 的函数，只要它被用在**推理路径**（非评测路径），就是在泄漏。评测代码（Scorer、diagnose）读 label 是合法的；Skill、scoring、prompt 构建读 label 是不合法的。

**排查方法**：`grep -r "label.json" --include="*.py"` 然后逐个判断是否在推理路径上。

---

## 2. pycache 会让已修复的泄漏继续生效

**发现**：修改了 `temporal_score.py` 源码后，`skill_pipeline.py` 通过 `_load_skills()` 动态 import Skill 模块。如果 `__pycache__` 里有旧版本 `.pyc`，Python 会优先加载缓存的字节码——修复不生效。

**教训**：修改任何 SkillBank/skills/*.py 后，必须删除 `__pycache__`。可以在脚本开头加 `sys.dont_write_bytecode = True` 或每次 `git pull` 后清缓存。

**排查方法**：`tmp/check_cache_leak.py`

---

## 3. 两条路径用不同评分函数 → 数字对不上

**发现**：消融脚本用 `skill_pipeline._score_topo()`（归一化到 [0,1]），LLM 推理用 `evidence_fusion._run_topo()`（调用 Skill executor 获原始分 4.07 这种 ×100 的值）。PageRank ~4 的量级碾压时序 ~0.8 → "融合"退化为"PR-only"。

**教训**：评分函数必须**同一份代码、同一个调用路径**。`evidence_fusion` 现在直接用 `skill_pipeline._score_topo` / `_score_temporal`。任何改动要同步两处。

**排查方法**：`tmp/compare_all.py` — 同 case 走两条路径，输出 Top-5 diff。

---

## 4. prompt 让 LLM "重排" → LLM 会强行重排

**发现**：prompt 写"审核并重排"，LLM 觉得必须动手。80% case 告警全空 → 综合分 99.8 vs 50.0 的强信号被 LLM 翻掉 → Top-1 从 87% 降到 80%。

**教训**：LLM 的默认行为是"做点事"。prompt 里要说"默认信任算法排名，仅在告警名称提供明确相反证据时调整"。"默认信任"四个字必须在 prompt 最前面。

---

## 5. LLM 没有语义信号时做不了有效重排

**发现**：80% case 所有设备的 alarms/logs 完全为空。LLM 收到的 `high_severity_alarms: []` → 除综合分外没有任何决策依据 → 不管 prompt 怎么写都无意义。

**教训**：在投入 LLM 推理之前先统计告警覆盖率。如果大部分 case 告警为空，应该先修复数据管道（回填告警），再测 LLM。

**排查方法**：`tmp/check_alarm_coverage.py`

---

## 6. Modifier 剪枝会切掉根因

**发现**：毕设路径 `generate_prompts()` 读 `nodes.json`（Modifier 剪枝后 K=10）。全链路 376 节点，剪枝后 10 节点——根因 IP 经常不在 Top-10 里 → LLM 没机会看到。

**教训**：剪枝策略在推理路径上是危险的——不能用算法结果去剪算法需要用到的输入。改为读全链路文件，靠 prompt 压缩（证据融合层）保证不超 token。

---

## 7. 消融和 LLM 推理数据必须同一份

**发现**：消融 56% vs LLM skill 85%，30pp 差距。排查很久发现是数据不一致——一份原始数据（告警为空），一份回填后数据。

**教训**：所有对比实验必须记录**数据的 hash 或时间戳**。消融和推理前后脚跑，中间不能变更数据。

---

## 8. 旧标注 vs 新标注的差距是系统性偏差

**发现**：毕设 104 例（非人工标注）PageRank Top-1 = 39%。新数据 146 例（人工标注）= 14-17%。旧标注本身可能偏向拓扑结构 → PageRank 看起来比实际上强。

**教训**：标注来源是实验结果最重要的元数据。非人工标注的结果不能用于消融分析。

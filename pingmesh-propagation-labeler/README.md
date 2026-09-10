# Pingmesh DD/EE 异构传播图标注工具

一个独立、本地运行、零第三方运行依赖的故障传播图人工标注工具。它使用 Python
标准库启动本地 Web 界面，所有 case 数据和标注都保留在本机。

## 主要能力

- 默认提供“简单模式”，人工只需设置根因并绘制有向传播边；
- 自动读取 case 中的 `label_v2.json` / `label.json` 根因设备并在图中用红圈标出；
- 有告警的设备会自动成为传播候选并显示橙色数量标记，点击设备即可查看告警和拓扑连边；
- 未标注、无告警且未聚焦的节点会按拓扑层聚合为紧凑点阵；聚合后的真实节点仍可点击并作为传播边端点；
- 不区分“中间节点”和“传播终点”：传播路径中的任意节点都可继续向后连接传播边；
- 点击任意设备会高亮其全部拓扑连边，并在右侧列出可继续跳转的相邻节点；
- 可添加手工中转 CORE：自动接入没有 CORE 邻居的真实 SPINE，再点选其他节点作为中转出口；
- 简单模式支持在拓扑图内拖动、触摸滑动和滚轮平移；
- 对数百节点、数千条物理边的拓扑做聚焦展示；
- 从设备名中的 `pod` 字符及其后数字提取 Pod 号；
- 将疑似压缩的 `LEAF—CORE` 直连展开为不可标注的“隐藏 SPINE 集合”，并明确展示推测依据；
- 按 IP 或设备名搜索，自动展开证据节点、source/sink 锚点及其邻域；
- 在 `DD 设备传播 / EE 事件演化 / DD+EE 异构总览` 三个图层间切换；
- 简单模式由传播边自动推导传播路径节点；完整模式仍支持 DD/EE 细粒度字段和 initiating event；
- 分开标注 DD 与 EE 的 `definite / possible / explicit_no_* / unknown` 四状态关系；
- 将 EE 依赖/演化关系绑定到其支持的 DD 传播边，并保留 D-E 观测归属；
- 在固定页签中分别查看告警、日志完整字段，并将证据绑定到节点或边；
- 自动保存、断点续标、撤销/重做、快捷键、完成进度和双页面修改冲突保护；
- 保存前校验 schema、设备范围、重复边和 DAG 无环性；
- 默认盲标，可选在“人工标注 / 假设图 / 对照”三个视角间切换。

## 快速开始

需要 Python 3.10 或更高版本。从仓库根目录直接运行：

```powershell
python run_labeler.py `
  --data-root D:\path\to\case_data `
  --labels-root D:\path\to\propagation_labels `
  --annotator A01
```

工具会自动选择可用端口并打开浏览器。按 `Ctrl+C` 停止本地服务。
页面默认进入“简单模式”：设定根因节点后，从根因开始连续绘制有向传播边即可，
传播节点之后可以继续连接传播节点。可在顶部切换到“完整模式”使用 DD/EE
异构标注、假设图和全部证据绑定功能。

也可以安装为命令行工具：

```powershell
python -m pip install .
propagation-labeler --data-root D:\path\to\case_data --labels-root D:\path\to\propagation_labels
```

## 立即体验脱敏示例

仓库内置了一个完全合成的小型 case：

```powershell
python run_labeler.py `
  --data-root examples/demo_cases `
  --labels-root .local/demo_labels `
  --annotator DEMO
```

若要体验当前 M1/M2/M3 异构图审核模式：

```powershell
python run_labeler.py `
  --data-root examples/demo_cases `
  --labels-root .local/demo_labels `
  --hypotheses examples/demo_predictions.json `
  --hypothesis-view
```

启用后，界面会出现“人工标注 / 假设图 / 对照”视角切换。DD 图层展示设备边的
`A→B / B→A / No Direct`，EE 图层展示事件边的
`Ei→Ej / Ej→Ei / No Dependency`，异构总览同时展示 D-E 观测归属。紫色边宽表示
模型方向概率；假设图视角只读，不会修改人工标注。旧参数
`--predictions --prediction-overlay` 仍然可用。

## 输入结构

`--data-root` 下可以任意嵌套 case 目录。每个 case 目录至少需要：

```text
case_data/
└── batch_or_timestamp/
    └── CASE_ID/
        ├── info.json
        └── nodes.json
```

或者使用预处理产物：

```text
CASE_ID/
├── info.json
├── topology_context.json       # 推荐，可保留端口和物理边信息
└── pingmesh-CASE_ID-全链路.json
```

`info.json` 建议包含：

- `alarm_name`
- `alarm_time`
- `source_ip`
- `sink_ip`
- `scenario_code`
- `alarm_description`

`nodes.json` 可以是设备对象字典或设备列表。每个设备建议包含：

- `mgmt_ip` 或 `ip`
- `name`
- `role`
- `linked_from` / `linked_to`
- `alarms` / `logs`

当 `topology_context.json` 不存在时，工具会从 `linked_from` 和 `linked_to` 构建无向物理拓扑。

### 不完整拓扑的恢复层

原始 `task_topo` 可能只保留端到端路径附近的设备，并把中间层折叠成
`LEAF—CORE` 直连。工具会把同一 LEAF/CORE 投影连通分量通过一个虚拟的
“隐藏 SPINE 集合”展开；设备名如 `xxx-pod001-xxx` 会解析为 Pod 1，并沿该
投影分量传播给相邻 CORE，帮助标注者理解层级。

CORE 子图按源到目的识别为多个转发级。同一转发级中的 CORE 并行纵向排列，
相邻转发级之间只保留原始 `task_topo` 已观测到的连接。即使已观测边覆盖两侧
全部 CORE，也不会补齐缺失的笛卡尔组合，因为不同 CORE 转发级不保证全连接。
若源侧和目的侧 CORE 子图在裁剪拓扑中完全断开，工具只报告结构缺口，不生成
虚拟桥接节点或未经观测的 CORE—CORE 边。

恢复层是结构提示，不是新造的设备真值：虚拟节点不具备名称、管理 IP 或确定数量，
不能被标成根因/传播设备，也不能作为 DD 边端点。原始拓扑节点和边保持不变，保存的
DD 标注仍必须对应原始 `task_topo` 邻接边。对于无法由角色和投影结构支持的缺失节点，
工具不会自动补全。

标注过程中手工添加的“中转 CORE”同样只属于展示层。它及其连线保存在当前 case 的
`topology_overrides` 中，便于断点续标，但不会进入 DD 传播真值，也不会绕过原始
`task_topo` 邻接校验。中转 CORE 可继续连接多个下游节点，也可从右侧详情整体删除。

## 输出结构

每个 case 独立保存：

```text
<labels-root>/
└── CASE_ID/
    └── propagation_label.json
```

标签使用 `heterogeneous-propagation-label-v1`，包含：

- 根因作用域与根因设备/链路；
- 可诊断性与标注置信度；
- `device_nodes` 与 `dd_edges`：设备主传播 DAG；
- `event_nodes` 与 `ee_edges`：事件依赖/演化解释层；
- EE 边到 DD 边的支持映射，以及设备/边到原始证据的追溯；
- `annotation_complete_scope`：设备、DD 候选和 EE 候选的完整检查声明；
- 标注轮次、状态、更新时间和工具版本。

为了兼容现有设备级评测脚本，文件还同步保存 `nodes` / `edges` 作为 DD 层别名。
未标关系始终是 `unknown`；只有勾选相应完整检查范围后，才能保存
`explicit_no_direct` 或 `explicit_no_dependency`。

文件使用临时文件 + 原子替换的方式写入，避免意外中断产生半个 JSON。

## 盲标与假设图审核

默认模式不读取也不展示模型预测路径，适合建立论文真值，避免模型结果造成锚定偏差。
case 自带的 `label_v2.json` / `label.json` 只用来提供已知根因设备，
不会导入传播路径或模型预测边。

只有同时提供以下参数，才会开放假设图视角：

```text
--hypotheses /path/to/res.json --hypothesis-view
```

输入优先读取当前 `heterogeneous_graphs.json` 中的完整 `result`：
`m1_candidate_graph`、`m2_probabilistic_graph` 与 `m3_reconstruction`。同时兼容旧的
M1 `hypothesis_graph` 和 `selected_propagation_graph`。压缩版 `res.json` 只有图引用，
不含 DD/EE 明细，因此审核时应传入 `heterogeneous_graphs.json`。
该模式建议只用于算法输出审核、错误分析或工程可用性研究，不应与盲标真值混用。

## 右侧详情区

右侧详情固定为“标注 / 告警 / 日志 / 假设”四个页签。页面本身不再随长表单整体滚动，
只有当前页签内部滚动；Case 级设置默认折叠。告警和日志支持筛选、展开完整原始字段，
选择人工节点或人工传播边后还可以直接勾选绑定证据。

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Shift + 点击节点` | 从当前节点快速添加有向边 |
| `E` | 从当前节点进入连边模式 |
| `1` | 将当前节点设为根因 |
| `D / P / X` | 确定 / 可能 / 排除（边上为不可能） |
| `[` / `]` | 上一个 / 下一个 case |
| `Ctrl+Z / Ctrl+Y` | 撤销 / 重做 |
| `Ctrl+S` | 立即保存 |

画布内按住鼠标左键拖动，或直接触摸滑动，可以自由平移拓扑图。
滚轮用于上下平移，`Shift+滚轮` 用于左右平移，`Ctrl+滚轮` 用于以鼠标位置为中心缩放。
右下角的 `⌂` 按钮可随时恢复到初始视图。

## 数据安全

- 服务默认只监听 `127.0.0.1`；
- 界面不使用 CDN，不向外部服务发送 case 内容；
- `.gitignore` 默认排除 `data/`、`labels/`、`propagation_labels/` 和 `.local/`；
- 正式真值请与待评价推理管线隔离存储；
- 提交或发布仓库前，请再次确认没有内部 case、设备 IP 和原始告警文本。

## 测试

```powershell
python -m pytest
```

运行工具本身不需要 pytest；pytest 仅用于开发和回归测试。

## 开源许可

本仓库尚未附加开源许可证。在获得项目所有者的许可前，请不要对外分发或用于其他授权场景。

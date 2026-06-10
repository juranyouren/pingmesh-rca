"""
BiAn Baseline — faithful reimplementation based on:
  Wang et al., "Towards LLM-Based Failure Localization in Production-Scale
  Networks", SIGCOMM 2025 (BiAn: Bi-level Agent framework for network RCA).

Original three-agent architecture:
  Stage 1 – Information Extraction Agent:
    Classify and summarise multi-source monitoring logs into structured
    per-device summaries.
  Stage 2 – Single-Device Analysis Agent:
    Analyse each device's summary against standard operating procedures
    (SOP) to determine local anomaly severity and suspicion level.
  Stage 3 – Global Verification Agent:
    Cross-score all suspicious devices considering:
      - alarm severity
      - topology adjacency (parent-child relationships)
      - event timeline (temporal ordering)
    Output final root-cause ranking and diagnostic explanation.

This implementation follows the three-stage architecture faithfully while
adapting prompts for the DCN Pingmesh setting.
"""

import os, json, time, math, re
from multiprocessing import Pool, cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp


# ── helpers ──────────────────────────────────────────────────────────
def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── BiAn Prompts ─────────────────────────────────────────────────────

# Stage 1: Information Extraction — per-device structured summary
BIAN_STAGE1_SUMMARY = """你是一名数据中心网络运维工程师。请对以下网络设备的告警和日志进行**结构化诊断摘要**。

设备IP: {IP}
设备角色: {ROLE}（Spine=核心层, Leaf=接入层, Core=核心路由层）
邻接设备IP: {NEIGHBORS}

告警数据 (alarms):
{ALARMS}

日志数据 (logs):
{LOGS}

请输出 JSON（只输出 JSON，不要其他内容）:
```json
{{
    "ip": "{IP}",
    "role": "{ROLE}",
    "summary": "<1-2句中文，概括该设备的主要异常事件，忽略常规状态信息>",
    "alarm_types": ["<该设备上出现的告警类型列表，取告警名称>"],
    "most_critical_alarm": "<最严重的一条告警名称，如无告警填 '无'>",
    "has_destructive_alarm": <true/false, 是否存在操作型破坏性告警（如DELETE、DOWN、中断等）>,
    "has_hardware_alarm": <true/false, 是否存在硬件层告警（如端口故障、光模块异常等）>,
    "alarm_count": <整数，总告警+日志条数>,
    "temporal_pattern": "<告警的时间特征: '最早出现' / '中期出现' / '最晚出现' / '无法判断'>"
}}
```"""

# Stage 2: Single-Device Analysis — SOP-based anomaly scoring
BIAN_STAGE2_DEVICE = """你是一名数据中心网络排障专家。请根据以下某台设备的诊断摘要，对照网络排障 SOP（标准作业程序）对其进行**单设备异常分析**。

## 该设备的诊断摘要
{DEVICE_SUMMARY}

## 排障 SOP 参考
1. **硬件层故障**（端口Down、光模块异常、硬件告警）→ 嫌疑度最高，通常是根因
2. **路由/协议层故障**（BGP中断、路由删除、BFD震荡）→ 可能是根因也可能是衍生
3. **应用层异常**（丢包、延迟升高）→ 通常是受害者症状，不太可能是根因
4. **状态通知类**（会话UP、配置变更通知）→ 几乎不可能是根因
5. **时间顺序**：同一拓扑区域内最早出现告警的设备更可能是根因
6. **设备角色**：Leaf层设备故障通常不影响其他Leaf；Spine/Core层设备故障会大面积传播

## 输出要求
请输出 JSON（只输出 JSON）:
```json
{{
    "ip": "<设备IP>",
    "anomaly_level": "<正常 / 轻度异常 / 中度异常 / 严重异常>",
    "suspicion_score": <0.0到1.0之间的浮点数，越高越可疑>,
    "is_likely_root_cause": <true/false>,
    "evidence_for": ["<支持该设备为根因的证据>"],
    "evidence_against": ["<不支持该设备为根因的证据>"],
    "sop_reference": "<引用的SOP条款编号或描述>"
}}
```"""

# Stage 3: Global Verification — cross-scoring with topology adjacency
BIAN_STAGE3_GLOBAL = """你是一名 AIOps 高级排障架构师。现有一个数据中心网络故障案例，需要你进行**全局验证与根因定界**。

## 故障现象 (Pingmesh告警)
{INFO}

## 各设备单机分析结果
{DEVICE_ANALYSES}

## 网络拓扑邻接关系
{TOPOLOGY}

## 任务要求
请综合以下三个维度进行交叉验证：

### 维度一：告警严重度交叉验证
- 比较各设备的 anomaly_level 和 suspicion_score
- 高嫌疑度设备之间是否存在告警类型的因果关系？

### 维度二：拓扑邻接关系验证
- 分析故障传播方向：被标记为"严重异常"的设备在拓扑上是上游还是下游？
- 如果某设备异常，其邻接设备是否也有异常？（级联特征）
- 如果某设备异常但所有邻接设备正常，该异常可能是孤立事件或数据噪声

### 维度三：时间线验证
- 比较各设备告警的 temporal_pattern
- 最早出现且具有破坏性告警的设备更可能是根因
- 最晚出现的通常是受害者

## 输出格式
```json
{{
    "reasoning": "<综合以上三个维度的交叉验证推理过程>",
    "ip": ["<确诊根因设备的IP，按嫌疑度从高到低排序，最多5个>"],
    "propagation_path": {{
        "<根因IP>": {{
            "affected_nodes": ["<受影响节点IP列表>"],
            "impact": "<故障传播机制说明>"
        }}
    }}
}}
```"""


# ── BiAn Analyzer ────────────────────────────────────────────────────
class BiAnAnalyzer:
    """
    Full three-stage BiAn pipeline.

    Uses vLLM for all LLM inference.  Runs on Ascend NPU.
    """

    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B",
                 ASCEND_RT_VISIBLE_DEVICES="0,1"):
        self.model_path = model_path
        self.npus = ASCEND_RT_VISIBLE_DEVICES
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.npus

        from vllm import LLM, SamplingParams

        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=len(self.npus.split(",")),
            gpu_memory_utilization=0.85,
            max_model_len=32768,
            trust_remote_code=True,
        )

        self.sampling_params = SamplingParams(
            temperature=0.3,
            max_tokens=4096,
            repetition_penalty=1.05,
        )
        self.tokenizer = self.llm.get_tokenizer()

    def _safe_truncate(self, text, max_tokens=2000):
        tokens = self.tokenizer.encode(text)
        if len(tokens) > max_tokens:
            return self.tokenizer.decode(tokens[:max_tokens]) + "\n...[截断]"
        return text

    def _batch_infer(self, prompts, desc="LLM", batch_size=16):
        from tqdm import tqdm
        all_responses = []
        for i in tqdm(range(0, len(prompts), batch_size), desc=desc):
            batch = prompts[i:i + batch_size]
            applied = [[{'role': 'user', 'content': p}] for p in batch]
            outputs = self.llm.chat(applied, self.sampling_params)
            all_responses.extend([o.outputs[0].text.strip() for o in outputs])
        return all_responses

    def _extract_json(self, text):
        """Extract the LAST ```json ... ``` block from LLM output."""
        blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if blocks:
            try:
                return json.loads(blocks[-1])
            except json.JSONDecodeError:
                pass
        # Fallback: try parsing the whole text as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    # ── Stage 1: Information Extraction ──────────────────────────────
    def _run_stage1(self, nodes_list, info):
        """Classify and summarize alarms per device."""
        stage1_prompts = []
        device_ips = []

        for node in nodes_list:
            ip = node.get("mgmt_ip", "unknown")
            role = node.get("role", "unknown")
            neighbors = (node.get("linked_to", []) +
                         node.get("linked_from", []) +
                         node.get("verified_hops_to", []))
            # Deduplicate and limit
            neighbors = list(set(neighbors))[:10]
            alarms = node.get("alarms", [])
            logs = node.get("logs", [])

            # Skip completely silent nodes
            if not alarms and not logs:
                continue

            alarms_str = self._safe_truncate(json.dumps(alarms, ensure_ascii=False), 1500)
            logs_str = self._safe_truncate(json.dumps(logs, ensure_ascii=False), 1500)

            prompt = BIAN_STAGE1_SUMMARY.format(
                IP=ip, ROLE=role,
                NEIGHBORS=json.dumps(neighbors, ensure_ascii=False),
                ALARMS=alarms_str, LOGS=logs_str,
            )
            stage1_prompts.append(prompt)
            device_ips.append(ip)

        if not stage1_prompts:
            return {}

        responses = self._batch_infer(stage1_prompts, desc="BiAn Stage 1: Summary")
        summaries = {}
        for ip, resp in zip(device_ips, responses):
            parsed = self._extract_json(resp)
            if parsed:
                summaries[ip] = parsed
            else:
                summaries[ip] = {"ip": ip, "summary": resp, "suspicion_score": 0.0}

        return summaries

    # ── Stage 2: Single-Device Analysis ──────────────────────────────
    def _run_stage2(self, stage1_summaries):
        """Analyze each suspicious device against SOP."""
        stage2_prompts = []
        ips_order = []

        for ip, summary in stage1_summaries.items():
            prompt = BIAN_STAGE2_DEVICE.format(
                DEVICE_SUMMARY=json.dumps(summary, ensure_ascii=False, indent=2)
            )
            stage2_prompts.append(prompt)
            ips_order.append(ip)

        if not stage2_prompts:
            return {}

        responses = self._batch_infer(stage2_prompts, desc="BiAn Stage 2: Device Analysis")
        analyses = {}
        for ip, resp in zip(ips_order, responses):
            parsed = self._extract_json(resp)
            if parsed:
                analyses[ip] = parsed
            else:
                analyses[ip] = {"ip": ip, "suspicion_score": 0.0, "anomaly_level": "未知"}

        return analyses

    # ── Stage 3: Global Verification ─────────────────────────────────
    def _run_stage3(self, stage2_analyses, nodes_list, info):
        """Cross-score using topology adjacency, severity, and timeline."""
        # Build topology adjacency summary
        topo_lines = []
        for node in nodes_list:
            ip = node.get("mgmt_ip", "")
            role = node.get("role", "")
            neighbors = (node.get("linked_to", []) +
                         node.get("linked_from", []) +
                         node.get("verified_hops_to", []))
            neighbors = list(set(neighbors))[:8]
            if ip and neighbors:
                topo_lines.append(f"  {ip} ({role}) ↔ {', '.join(neighbors)}")

        topo_text = "\n".join(topo_lines[:50])  # limit topology size

        info_str = json.dumps(info, ensure_ascii=False, indent=2)
        analyses_str = json.dumps(
            {ip: a for ip, a in list(stage2_analyses.items())[:20]},
            ensure_ascii=False, indent=2,
        )

        prompt = BIAN_STAGE3_GLOBAL.format(
            INFO=info_str,
            DEVICE_ANALYSES=analyses_str,
            TOPOLOGY=topo_text,
        )

        resp = self._batch_infer([prompt], desc="BiAn Stage 3: Global RCA", batch_size=1)
        return self._extract_json(resp[0]) if resp else {}

    # ── Main pipeline ────────────────────────────────────────────────
    def process_one(self, dirpath):
        nodes_path = os.path.join(dirpath, "nodes.json")
        info_path = os.path.join(dirpath, "info.json")

        nodes_data = load_json(nodes_path) if os.path.exists(nodes_path) else {}
        info_data = load_json(info_path) if os.path.exists(info_path) else {}

        if isinstance(nodes_data, dict):
            nodes_list = list(nodes_data.values())
        else:
            nodes_list = nodes_data

        # Stage 1: Information Extraction
        s1 = self._run_stage1(nodes_list, info_data)

        # Stage 2: Single-Device SOP Analysis
        s2 = self._run_stage2(s1)

        # Stage 3: Global Cross-Scoring
        s3 = self._run_stage3(s2, nodes_list, info_data)

        return s3

    def process_cases(self, dirpaths, batch_size=1):
        results = []
        # Process sequentially due to multi-stage dependencies
        for i, dp in enumerate(dirpaths):
            print(f"[BiAn] [{i+1}/{len(dirpaths)}] {os.path.basename(dp)}")
            try:
                s3 = self.process_one(dp)
                ips = s3.get("ip", [])
                if isinstance(ips, str):
                    ips = [ips]

                response = json.dumps(s3, ensure_ascii=False, indent=2)
                results.append({
                    "dir": dp,
                    "prompt": "BiAn: 3-stage multi-agent RCA (SIGCOMM 2025)",
                    "draft_response": response,
                })
            except Exception as e:
                print(f"  Error: {e}")
                results.append({
                    "dir": dp,
                    "prompt": "BiAn",
                    "draft_response": f'{{"ip": [], "error": "{str(e)}"}}',
                })

        return results


# ── Parallel runner ──────────────────────────────────────────────────
def generate_prompts(root_path):
    dirpaths = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            dirpaths.append(dirpath)
    return dirpaths


def worker_process(worker_id, npus, dirpaths_chunk, batch_size=1):
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    time.sleep(worker_id * 30)  # stagger init
    analyzer = BiAnAnalyzer(ASCEND_RT_VISIBLE_DEVICES=npus)
    return analyzer.process_cases(dirpaths_chunk, batch_size)


def distribute_inference_tasks(dirpath_list, npu_list, batch_size=1):
    if not dirpath_list:
        return []

    num_instances = len(npu_list) // 2
    if num_instances == 0:
        num_instances = 1
    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]

    chunk_size = math.ceil(len(dirpath_list) / num_instances)
    dir_chunks = [dirpath_list[i:i + chunk_size]
                  for i in range(0, len(dirpath_list), chunk_size)]

    all_results = []
    ctx = mp.get_context('spawn')
    with ProcessPoolExecutor(max_workers=num_instances, mp_context=ctx) as executor:
        futures = []
        for i in range(num_instances):
            if i < len(dir_chunks) and dir_chunks[i]:
                futures.append(executor.submit(
                    worker_process, i + 1, npu_groups[i], dir_chunks[i], batch_size
                ))
        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as e:
                print(f"Worker failed: {e}")

    return all_results


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/sbp/lixinyang/pingmesh/data/nodes_labeled"
    available_npus = [2, 3, 6, 7]

    dirpaths = generate_prompts(root)
    print(f"BiAn: {len(dirpaths)} cases found.")

    t0 = time.time()
    results = distribute_inference_tasks(dirpaths, available_npus)
    elapsed = time.time() - t0

    print(f"Done in {elapsed:.2f}s ({elapsed/max(len(results),1):.2f}s/case)")

    outdir = f"/home/sbp/lixinyang/pingmesh/data/res/bian_baseline_{int(time.time())}"
    save_json(results, os.path.join(outdir, "res.json"))
    print(f"Saved to {outdir}")

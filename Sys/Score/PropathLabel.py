import os,json,re
import sys
import time
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append("/home/sbp/lixinyang/pingmesh")
from utils.prompts import PROPATH_LABEL 
def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_txt(str, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(str)

class PropathLabel:
    def __init__(self, model_path="/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", ASCEND_RT_VISIBLE_DEVICES="0,1"):
        """
        初始化基于 vllm.LLM 直接调用的根因分析器
        """
        print(f"[{os.getpid()}] 正在初始化 vLLM 引擎，使用的 NPU 卡号为: {ASCEND_RT_VISIBLE_DEVICES}")
        
        self.model_path = model_path
        self.ASCEND_RT_VISIBLE_DEVICES = ASCEND_RT_VISIBLE_DEVICES
        
        # 为了确保子进程中生效，在这里显式设置环境变量
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.ASCEND_RT_VISIBLE_DEVICES
        
        # 延迟导入 vLLM，防止在 fork 模式下主进程加载导致显存泄露或 context 冲突
        from vllm import LLM, SamplingParams
        
        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=2,  # 规定每个实例使用两张卡
            gpu_memory_utilization=0.85,
            max_model_len=65536/4,
            trust_remote_code=True
        )
        
        self.sampling_params = SamplingParams(
            temperature=0.6,
            max_tokens=2048,
            repetition_penalty=1.05
        )

    def batch_infer(self, prompts: list, batch_size: int = 8) -> list:
        print(f"[{os.getpid()}] 正在执行批量推理 (共 {len(prompts)} 条, Batch Size: {batch_size})...")

        def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1):
            from tqdm import tqdm
            all_responses = []
            n = getattr(sampling_params, "n", 1)
            for i in tqdm(range(0, len(inputs), batch_size)):
                batch_inputs = inputs[i:i + batch_size]
                applied_prompts = [[
                    {'role': 'user', 'content': prompt}
                ] for prompt in batch_inputs]
                outputs_w_prompts = llm.chat(applied_prompts, sampling_params)
                if n > 1:
                    for item in outputs_w_prompts:
                        all_responses.append([out.text for out in item.outputs])
                else:
                    all_responses.extend([item.outputs[0].text for item in outputs_w_prompts])
            return all_responses
        try:
            responses = vllm_invoke(
                llm=self.llm, 
                inputs=prompts, 
                sampling_params=self.sampling_params, 
                batch_size=batch_size
            )
            return responses
        except Exception as e:
            print(f"\n[Error {os.getpid()}] vLLM 批量推理执行异常: {str(e)}")
            return ["模型未返回有效推理内容或发生异常。"] * len(prompts)

def get_groundtruth_ips(name):
    """
    根据name，在name/label.json的文件中读取label，提取前三个设备的ip作为groundtruth
    """
    label_file_path = os.path.join(name, "label.json")
    if not os.path.exists(label_file_path):
        print(f"警告: 找不到标签文件 {label_file_path}")
        return []

    with open(label_file_path, 'r', encoding='utf-8') as f:
        labels = json.load(f)

    # 根据 ranking 排序，确保提取的是前三个
    labels_sorted = sorted(labels, key=lambda x: x.get("ranking", 999))
    
    groundtruth_ips = []
    # 只取排名前3的设备
    for label in labels_sorted[:3]:
        abnormal_nodes = label.get("abnormal_node", [])
        for node in abnormal_nodes:
            if "ip" in node:
                groundtruth_ips.append(node["ip"])
    
    # 去重并保持原有顺序
    seen = set()
    unique_groundtruth_ips = [ip for ip in groundtruth_ips if not (ip in seen or seen.add(ip))]
    return unique_groundtruth_ips

def generate_prompts(root_path: str) -> tuple:
    """生成 Prompt 列表（外部函数）"""
    dirpath_list = []
    prompt_list = []
    print(f"开始扫描目录 {root_path} 并构造 Prompt...")
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        if "nodes.json" in filenames and "info.json" in filenames:
            node_path = os.path.join(dirpath, "nodes.json")
            info_path = os.path.join(dirpath, "info.json")
            ip_list=get_groundtruth_ips(dirpath)
            try:
                node = load_json(node_path)
                info = load_json(info_path)
                prompt = PROPATH_LABEL.format(NODES=node, INFO=info,IPS=ip_list)
                dirpath_list.append(dirpath)
                prompt_list.append(prompt)
                save_txt(prompt,f"{dirpath}/pmt.txt")
            except Exception as e:
                print(f"\n[错误] 读取/解析目录 {dirpath} 时发生异常: {e}")
                
    return dirpath_list, prompt_list


def worker_process(worker_id: int, npus: str, dirpaths_chunk: list, prompts_chunk: list, batch_size: int = 8) -> dict:
    """
    多进程的工作函数：每个进程负责初始化自己的 Analyzer 并跑完分给它的 chunk。
    """
    # 【核心修改 1】在子进程的极早期，任何其他逻辑之前，设置环境变量
    import os
    os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npus
    print(f"[Worker {worker_id}] 环境变量已设置 ASCEND_RT_VISIBLE_DEVICES={npus}")
    sleep_time = (worker_id - 1) * 60
    time.sleep(sleep_time)
    analyzer = PropathLabel(ASCEND_RT_VISIBLE_DEVICES=npus)
    responses = analyzer.batch_infer(prompts_chunk, batch_size=batch_size)
    
    # 匹配结果并返回字典
    result_dict = {}
    for dp, res in zip(dirpaths_chunk, responses):
        clean_res = res.strip() if isinstance(res, str) else str(res)
        result_dict[dp] = clean_res
    
    return result_dict

def distribute_inference_tasks(dirpath_list: list, prompt_list: list, npu_list: list, batch_size: int = 8) -> dict:
    """
    任务分配核心函数：根据 NPU 数量切分任务并开启多进程推理。
    """
    total_tasks = len(prompt_list)
    if total_tasks == 0:
        return {}

    # 计算可以开几个实例（每个实例需要2张卡）
    num_instances = len(npu_list) // 2
    if num_instances == 0:
        raise ValueError("卡数不足！每个实例至少需要 2 张 NPU 卡。")

    # 分配 NPU 对，例如 npu_list=[1,2,3,4] -> ['1,2', '3,4']
    npu_groups = [f"{npu_list[i*2]},{npu_list[i*2+1]}" for i in range(num_instances)]
    print(f"检测到可用 NPU: {npu_list}。将启动 {num_instances} 个并行实例，分配组: {npu_groups}")

    # 将任务均匀切分为 num_instances 份
    chunk_size = math.ceil(total_tasks / num_instances)
    dir_chunks = [dirpath_list[i:i + chunk_size] for i in range(0, total_tasks, chunk_size)]
    prompt_chunks = [prompt_list[i:i + chunk_size] for i in range(0, total_tasks, chunk_size)]
    
    # 防止因整除问题导致 chunk 数量多于 instance 数量
    if len(dir_chunks) > num_instances:
        # 将多出来的零头合并到最后一个 chunk
        dir_chunks[num_instances - 1].extend(sum(dir_chunks[num_instances:], []))
        prompt_chunks[num_instances - 1].extend(sum(prompt_chunks[num_instances:], []))
        dir_chunks = dir_chunks[:num_instances]
        prompt_chunks = prompt_chunks[:num_instances]

    all_results = {}
    
    # 必须使用 spawn 启动方式，避免子进程继承主进程上下文导致 NPU 驱动冲突
    ctx = mp.get_context('spawn')
    
    with ProcessPoolExecutor(max_workers=num_instances, mp_context=ctx) as executor:
        futures = []
        for i in range(num_instances):
            # 只有当该进程分到了任务才启动
            if i < len(dir_chunks) and len(dir_chunks[i]) > 0:
                print(f"正在提交任务给实例 {i+1} (NPU: {npu_groups[i]}, 任务数: {len(dir_chunks[i])})...")
                future = executor.submit(
                    worker_process, 
                    worker_id=i+1, 
                    npus=npu_groups[i], 
                    dirpaths_chunk=dir_chunks[i], 
                    prompts_chunk=prompt_chunks[i],
                    batch_size=batch_size
                )
                futures.append(future)

        # 收集所有进程的结果
        for future in as_completed(futures):
            try:
                res_dict = future.result()
                all_results.update(res_dict)
            except Exception as exc:
                print(f"某个子进程执行过程中发生了异常: {exc}")

    return all_results

def parse_and_save(data_dict):
    """
    从{
        "path_to_save":<response>,
        ···
    }
    这样的字典数据中，把response进行解析，回去json数据
    ```json
    <result>
    ```
    保存其中的result到path_to_save/label_propath.json下面
    """
    json_pattern = re.compile(r'```json\s*(.*?)\s*```', re.DOTALL)

    for path_to_save, response in data_dict.items():
        try:
            # 1. 提取 JSON 字符串
            match = json_pattern.search(response)
            if match:
                json_str = match.group(1).strip()
            else:
                # 如果没找到 Markdown 块，尝试直接解析整个 response
                json_str = response.strip()

            # 2. 解析 JSON 数据
            result_data = json.loads(json_str)

            # 3. 处理保存路径
            # 确保目标文件夹存在
            if not os.path.exists(path_to_save):
                os.makedirs(path_to_save)
            
            target_file = os.path.join(path_to_save, "label_propath.json")

            # 4. 保存文件
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=4)
            
            print(f"成功保存: {target_file}")

        except json.JSONDecodeError as e:
            print(f"解析失败 (路径: {path_to_save}): 无法识别 JSON 格式。错误: {e}")
        except Exception as e:
            print(f"处理失败 (路径: {path_to_save}): {e}")


# --- 主程序入口 ---
if __name__ == "__main__":
    # 配置
    root_path = "/home/sbp/lixinyang/pingmesh/data/nodes"
    available_npus = [0,1,2, 3, 4,5,6,7]  # 你的可用 NPU 列表
    
    # 1. 生成所有 prompt
    dirpaths, prompts = generate_prompts(root_path)

    # 2. 分配任务并并行推理
    if prompts:
        print(f"共生成 {len(prompts)} 个任务，开始分配并行推理...")
        
        start_time = time.time()
        final_results = distribute_inference_tasks(
            dirpath_list=dirpaths, 
            prompt_list=prompts, 
            npu_list=available_npus,
            batch_size=8
        )
        end_time = time.time()

        
        
        print(f"所有并行推理已完成！总耗时: {end_time - start_time:.2f} 秒")
        
        # 3. 结果保存
        timenow = int(time.time())
        save_dir = f"/home/sbp/lixinyang/pingmesh/data/res/{timenow}"
        os.makedirs(save_dir, exist_ok=True)
        
        if final_results:
            save_path = os.path.join(save_dir, "res.json")
            save_json(final_results, save_path)
            print(f"最终结果已合并并保存至: {save_path}")
        
        parse_and_save(final_results)
    else:
        print("没有找到需要推理的任务。")

    # final_results=load_json("/home/sbp/lixinyang/pingmesh/data/res/propath/res.json")
    # parse_and_save(final_results)
    
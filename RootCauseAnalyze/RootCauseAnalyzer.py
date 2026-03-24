
#        python -m vllm.entrypoints.openai.api_server \
#     --model /usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B
#     --served-model-name Qw7B
# ASCEND_RT_VISIBLE_DEVICES="4,5,6,7" python -m vllm.entrypoints.openai.api_server \
#     --model /usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B \
#     --served-model-name DeepSeek-R1-32B \
#     --tensor-parallel-size 4 \
#     --trust-remote-code \
#     --gpu-memory-utilization 0.85

# watch -n 1 npu-smi info 

import json
import asyncio
import os,sys
from omegaconf import DictConfig
from ms_agent.agent.llm_agent import LLMAgent
from ms_agent.agent import create_agent_skill
sys.path.append("/home/sbp/lixinyang/pingmesh/topo_simplify")
from utils.prompts import PROMPT1,PROMPT2
from utils.public_functions import load_json, save_json
class RootCauseAnalyzer:
    def __init__(self):
        """
        初始化基于 ms_agent 的根因分析器
        """
        # 获取当前文件所在目录，用来构造相对/绝对路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(base_dir) # 回退到 pingmesh 根目录
        project_root=os.path.join(project_root, 'agent')
        # 定义存放技能脚本的目录和工作区 (可以根据你的实际目录结构修改)
        self.skills_path = os.path.join(project_root, 'skills')
        self.work_dir = os.path.join(project_root, 'workspace')
        self.output= os.path.join(project_root, 'output')
        
        # 如果目录不存在则自动创建，防止报错
        os.makedirs(self.skills_path, exist_ok=True)
        os.makedirs(self.work_dir, exist_ok=True)

        # 按照你提供的格式配置大模型与 Agent
        # self.config: DictConfig = DictConfig(
        #     {
        #         'llm': {
        #             'service': 'openai',
        #             # 替换为你本地启动的模型名，如 'qwen2.5-7b-instruct'
        #             'model': '/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B', 
        #             # 接入本地模型，API Key 随便填
        #             'openai_api_key': 'EMPTY',        
        #             # 替换为你本地大模型服务的地址，例如 vLLM 或 Ollama 的服务地址
        #             'openai_base_url': 'http://localhost:8000/v1' 
        #         },
        #         'skills': {
        #             'path': self.skills_path,
        #             'work_dir': self.work_dir,
        #             'auto_execute': True,
        #         },
        #         'output_dir':self.output
        #     }
        # )
        self.config: DictConfig = DictConfig(
            {
                'llm': {
                    'service': 'openai',
                    # 替换为你本地启动的模型名，如 'qwen2.5-7b-instruct'
                    'model': 'DeepSeek-R1-32B', 
                    # 接入本地模型，API Key 随便填
                    'openai_api_key': 'EMPTY',        
                    # 替换为你本地大模型服务的地址，例如 vLLM 或 Ollama 的服务地址
                    'openai_base_url': 'http://localhost:8000/v1' 
                },
                'skills': {
                    'path': self.skills_path,
                    'work_dir': self.work_dir,
                    'auto_execute': True,
                },
                'output_dir':self.output
            }
        )

    def _format_topology_data(self, nodes):
        """将节点字典格式化为 JSON 字符串"""
        if not nodes:
            return "无有效的拓扑数据。"
        return json.dumps(nodes, indent=2, ensure_ascii=False)

    async def _async_infer(self, prompt: str) -> str:
        """
        异步执行核心逻辑，调用 LLMAgent
        """
        agent = LLMAgent(config=self.config)
        # agent = create_agent_skill(
        # # Use a skill from ModelScope Hub by its ID. A list of IDs is also supported. e.g. `ms-agent/skill_examples`
        # # To use local skills, provide the path to the directory, e.g., skills='./skills'
        # # For more details on skill IDs, see: https://modelscope.cn/models/ms-agent/skill_examples
        # skills=self.skills_path,
        # model='/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B',
        # api_key='EMPTY',
        # base_url='http://localhost:8000/v1',
        # stream=True,
        # # Note: Make sure the `Docker Daemon` is running if use_sandbox=True
       
        # work_dir=self.work_dir,
        # )

        # 调用 agent 进行推理
        results = await agent.run(messages=prompt)
        #results = await agent.run(query=prompt)

        final_content = ""
        # 按照你提供的范例解析返回的消息
        for res_msg in results:
            role = res_msg.role
            if role == 'assistant':
                # 拼接模型的输出内容
                final_content += res_msg.content + "\n"

        return final_content.strip()
    def use_skill(self, prompt: str) -> str:
        """
        异步执行核心逻辑，调用 LLMAgent
        """
        #agent = LLMAgent(config=self.config)
        agent = create_agent_skill(
        # Use a skill from ModelScope Hub by its ID. A list of IDs is also supported. e.g. `ms-agent/skill_examples`
        # To use local skills, provide the path to the directory, e.g., skills='./skills'
        # For more details on skill IDs, see: https://modelscope.cn/models/ms-agent/skill_examples
        skills=self.skills_path,
        #model='/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B',
        model='DeepSeek-R1-32B',
        api_key='EMPTY',
        base_url='http://localhost:8000/v1',
        stream=True,
        # Note: Make sure the `Docker Daemon` is running if use_sandbox=True
       
        work_dir=self.work_dir,
        )

        # 调用 agent 进行推理
        #results = await agent.run(messages=prompt)
        result = agent.run(query=prompt)

        

        return result

    def infer_root_cause(self, nodes: dict,info) -> str:
        """
        对外暴露的同步接口。
        因为外部的 run.py 是同步脚本，我们在这里使用 asyncio.run 将异步转化为同步。
        """
        prompt=PROMPT2.format(
            NODES=nodes,
            INFO=info
        )
        
        print(f"[{self.__class__.__name__}] 正在调用本地大模型进行分析，请稍候...")
        
        try:
            # 执行异步推理，等待结果
            result = asyncio.run(self._async_infer(prompt))
            return result if result else "模型未返回有效推理内容。"
        except Exception as e:
            error_msg = f"Agent 推理执行异常: {str(e)}"
            print(f"\n[Error] {error_msg}")
            return error_msg

    def test_skill(self) -> str:
    # 构造给 Agent 的系统提示词和任务输入
        prompt = (
            'Create generative art using p5.js with seeded randomness, flow fields, and particle systems, please fill in the details and provide the complete code based on the templates.'
    
        )
        
        print(f"[{self.__class__.__name__}] 正在调用本地大模型进行分析，请稍候...")
        
        try:
            # 执行异步推理，等待结果
            result = self.use_skill(prompt)
            return result if result else "模型未返回有效推理内容。"
        except Exception as e:
            error_msg = f"Agent 推理执行异常: {str(e)}"
            print(f"\n[Error] {error_msg}")
            return error_msg

# --- 本地快速测试代码 ---
if __name__ == "__main__":
    # mock_simplified_nodes = {
    #     "Leaf-Switch-01": {"role": "leaf", "alarms": [{"msg": "BGP peer down"}], "logs": []},
    #     "Spine-Switch-01": {"role": "spine", "alarms": [], "logs": []}
    # }

    root_path = "/home/sbp/lixinyang/pingmesh/data/nodes"
    analyzer = RootCauseAnalyzer() # 在循环外初始化，节省资源

    # 用于集中存储所有结果（如果需要后续处理的话）
    batch_results = {}

    print("开始批量处理...")

    # os.walk 会遍历 root_path 下的所有层级的目录
    for dirpath, dirnames, filenames in os.walk(root_path):
        # 检查当前目录下是否同时存在这两个需要的文件
        if "nodes.json" in filenames and "info.json" in filenames:
            node_path = os.path.join(dirpath, "nodes.json")
            info_path = os.path.join(dirpath, "info.json")
            
            try:
                # 加载数据
                node = load_json(node_path)
                info = load_json(info_path)
                
                # 执行分析
                res = analyzer.infer_root_cause(node, info)
                
                # 打印当前目录的独立结果
                print(f"\n=== 目录: {dirpath} 的测试结果 ===")
                print(res)
                
                # 将结果保存到字典中
                batch_results[dirpath] = res
                
            except Exception as e:
                print(f"\n[错误] 处理目录 {dirpath} 时发生异常: {e}")

    save_json(batch_results,"data/res")
    print("\n批量处理完成！")


    # path="/home/sbp/lixinyang/pingmesh/data/nodes/1760594400000/1231999173"
    # node_path=f"{path}/nodes.json"
    # info_path=f"{path}/info.json"
    # node=load_json(node_path)
    # info=load_json(info_path)
    # analyzer = RootCauseAnalyzer()
    # res = analyzer.infer_root_cause(node,info)
    # print("\n=== 测试结果 ===")
    # print(res)
    
    # analyzer = RootCauseAnalyzer()
    # res = analyzer.test_skill()
    # print("\n=== 测试结果 ===")
    # print(res)
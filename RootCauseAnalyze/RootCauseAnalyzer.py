
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
import os
from omegaconf import DictConfig
from ms_agent.agent.llm_agent import LLMAgent
from ms_agent.agent import create_agent_skill

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
        self.config: DictConfig = DictConfig(
            {
                'llm': {
                    'service': 'openai',
                    # 替换为你本地启动的模型名，如 'qwen2.5-7b-instruct'
                    'model': '/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-7B', 
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

    def infer_root_cause(self, nodes: dict) -> str:
        """
        对外暴露的同步接口。
        因为外部的 run.py 是同步脚本，我们在这里使用 asyncio.run 将异步转化为同步。
        """
        if not nodes:
            return "错误：传入的节点数据为空，无法进行推理。"
            
        topo_string = self._format_topology_data(nodes)
        
        # 构造给 Agent 的系统提示词和任务输入
        prompt = (
            "你是一个资深的云网络运维专家。现在网络中发生了一次故障，\n"
            "以下是经过清洗和简化后的网络拓扑及状态数据：\n"
            f"```json\n{topo_string}\n```\n\n"
            "任务要求：\n"
            "1. 请分析上述 json 数据中的连通性(linked_from/to)、alarms（告警）和logs（日志）。\n"
            "2. 如果你认为给出的节点信息不足，请主动使用你拥有的 skill 去查询相关节点的底层详情。\n"
            "3. 结合所有线索，给出详细的推理过程，并在最后明确指出【根因设备名称（Root Cause Node）】。"
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
    
    # analyzer = RootCauseAnalyzer()
    # res = analyzer.infer_root_cause(mock_simplified_nodes)
    # print("\n=== 测试结果 ===")
    # print(res)

    
    analyzer = RootCauseAnalyzer()
    res = analyzer.test_skill()
    print("\n=== 测试结果 ===")
    print(res)
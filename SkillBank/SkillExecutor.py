import os
import json
import importlib.util
import re

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
def generate_target_path(source_dir):
    # 提取最后一级目录名 (去除末尾可能的斜杠以防出错)
    node_id = os.path.basename(source_dir.rstrip(os.sep))
    filename = f"merged_pingmesh-{node_id}-全链路.json"
    return os.path.join(source_dir, filename)

class SkillExecutor:
    def __init__(self, skills_folder="/home/sbp/lixinyang/pingmesh/SkillBank/skills"):
        self.skill_map = {}          # 存放函数指针: {"evaluate_evidence_weight": <function>}
        self.skill_configs = []
        self.skills_folder=skills_folder      # 存放给大模型看的 JSON 列表
        # 核心：动态加载 Skill 库
        self._load_skills_dynamically(skills_folder)

    def _load_skills_dynamically(self, skills_path):
        if not os.path.exists(skills_path):
            print(f"警告：未找到 Skill 库目录 {skills_path}")
            return

        for filename in os.listdir(skills_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]
                file_path = os.path.join(skills_path, filename)
                
                # 动态导入模块
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                    
                    # 1. 提取元数据 (JSON)
                    if hasattr(module, "SKILL_META"):
                        self.skill_configs.append(module.SKILL_META)
                    
                    # 2. 提取并绑定执行函数
                    if hasattr(module, "EXECUTORS"):
                        for executor_name, func in module.EXECUTORS.items():
                            self.skill_map[executor_name] = func
                            
                except Exception as e:
                    print(f"加载插件 {filename} 失败: {e}")
        
        # 可选：按 skill_id 排序，保证输出给大模型的顺序是固定的
        self.skill_configs.sort(key=lambda x: int(x.get("skill_id", 999)))

    def get_skill_conf(self):
        return self.skill_configs

    def get_llm_skill_prompt(self) -> str:
        """调用此方法，自动生成喂给大模型的完整 JSON Skill 字符串"""
        return json.dumps(self.skill_configs, ensure_ascii=False, indent=2)
    
    def get_node_list(self,dirpath):
        nodes = load_json(generate_target_path(dirpath))
        if isinstance(nodes, list):
            return nodes
        elif isinstance(nodes, dict):
            return list(nodes.values())
        return []
    
    def execute(self, executor_name: str,node_path:str) -> str:
        """大模型调用具体函数的入口"""
        skill_func = self.skill_map.get(executor_name)
        if not skill_func:
            return f"【错误】找不到对应的执行脚本: {executor_name}"
        try:
            # 将 node_list 作为参数传给插件，插件无需关心数据是怎么解析的
            return skill_func(self.get_node_list(node_path))
        except Exception as e:
            return f"【系统脚本执行异常 - {executor_name}】: {str(e)}"
    
    def add_skill_from_response(self, response_text: str) -> str:
        """解析大模型的回复，提取 Python 插件代码，分配 ID 并保存生效"""
        
        # 1. 提取 Python 代码块
        code_match = re.search(r'```python\s*(.*?)\s*```', response_text, re.DOTALL)
        if code_match:
            py_code = code_match.group(1)
        else:
            # 容错：如果没有 markdown 标记，假定全文都是代码
            py_code = response_text
            
        # 2. 校验插件完整性
        if "SKILL_META" not in py_code or "EXECUTORS" not in py_code:
            return "【失败】提取的代码中缺少 SKILL_META 或 EXECUTORS 核心结构，丢弃该插件。"

        # 3. 计算分配新的 skill_id
        existing_ids = []
        for conf in self.skill_configs:
            try:
                existing_ids.append(int(conf.get("skill_id", 0)))
            except ValueError:
                pass
                
        next_id = max(existing_ids) + 1 if existing_ids else 1
        next_id_str = str(next_id)

        # 4. 替换代码块中的 skill_id 
        # (使用正则替换避免使用 AST 带来的复杂性，适配双引号和单引号)
        py_code = re.sub(
            r'("skill_id"\s*:\s*)["\']\d+["\']', 
            rf'\g<1>"{next_id_str}"', 
            py_code
        )
        py_code = re.sub(
            r"('skill_id'\s*:\s*)['\"]\d+['\"]", 
            rf"\g<1>'{next_id_str}'", 
            py_code
        )

        # 5. 提取执行器名称，用于生成易读的文件名
        executor_match = re.search(r'["\']python_executor["\']\s*:\s*["\']([^"\']+)["\']', py_code)
        executor_name = executor_match.group(1) if executor_match else "auto_generated"
        
        # 生成规范化的文件名：例如 skill_06_evaluate_evidence_weight.py
        filename = f"skill_{next_id:02d}_{executor_name}.py"
        save_path = os.path.join(self.skills_folder, filename)

        # 6. 保存文件并触发热更新
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(py_code)
                
            # 清空旧缓存，重新挂载整个技能目录
            self.skill_map.clear()
            self.skill_configs.clear()
            self._load_skills_dynamically(self.skills_folder)
            
            return f"【成功】新技能已摄取！分配ID: {next_id_str}, 执行器: {executor_name}, 文件已保存并热加载完成。"
            
        except Exception as e:
            return f"【失败】保存或加载新 Skill 文件时发生异常: {str(e)}"

if __name__ == "__main__":
    se=SkillExecutor()
    res_dict={}
    res_dict=load_json("/home/sbp/lixinyang/pingmesh/data/res/exeskilled3/single_reviews.json")
    for name,res in res_dict.items():
        se.add_skill_from_response(res)
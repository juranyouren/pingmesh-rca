import json
import re,sys

from urllib3 import response
sys.path.append("/home/sbp/lixinyang/pingmesh")
from utils.public_functions import load_txt,save_json

def extract_skill( response_text):
    if not response_text:
        return {}

    json_pattern = re.compile(r'```json\s*(\[.*?\])\s*```', re.DOTALL | re.IGNORECASE)
    json_blocks = json_pattern.findall(response_text)
    res=[]
    if json_blocks:
        for jb in json_blocks:
            data = json.loads(jb)
            for sk in data:
                res.append(sk)
    
    return res

if __name__ == "__main__":
    input="/home/sbp/lixinyang/pingmesh/data/res/naive_res_prmt4_0/extracted_skills_merged.md"
    response=load_txt(input)
    output="/home/sbp/lixinyang/pingmesh/SkillBank/skills.json"
    save_json(extract_skill(response),output)
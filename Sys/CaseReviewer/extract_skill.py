import json
import re,sys,os

from urllib3 import response
sys.path.append("/home/sbp/lixinyang/pingmesh")
from utils.public_functions import load_txt,save_json,load_json

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

def extract_judges(path):
    data=load_json(path)
    result=[]
    for dir,res in data.items():
        json_pattern = re.compile(r'```json\s*(.*?)\s*```', re.DOTALL | re.IGNORECASE)
        json_blocks = json_pattern.findall(res)
        if json_blocks:
            jb=json_blocks[-1]
            d = json.loads(jb)
            result.append(d)
    save_json(result,f"{os.path.dirname(path)}/exps.json")
    return result
def extract_skills_gd(path):
    data=load_txt(path)
    result=[]
    res=data
    json_pattern = re.compile(r'```json\s*(.*?)\s*```', re.DOTALL | re.IGNORECASE)
    json_blocks = json_pattern.findall(res)
    if json_blocks:
        jb=json_blocks[-1]
        d = json.loads(jb)
        result.append(d)
    save_json(d,f"{os.path.dirname(path)}/sk_guide.json")
    return d

if __name__ == "__main__":
    # input="/home/sbp/lixinyang/pingmesh/data/res/naive_res_prmt4_0/extracted_skills_merged.md"
    # response=load_txt(input)
    # output="/home/sbp/lixinyang/pingmesh/SkillBank/skills.json"
    # save_json(extract_skill(response),output)

    extract_skills_gd("/home/sbp/lixinyang/pingmesh/data/res/exeskilled5/extracted_skills_merged.md")
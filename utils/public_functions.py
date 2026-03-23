import pickle, os, torch, json, logging, requests
from zhconv import convert
from tqdm import tqdm

def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1):
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

# def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1):
#     all_responses = []
#     for i in tqdm(range(0, len(inputs), batch_size)):
#         batch = inputs[i:i+batch_size]
#         responses = vllm_api_invoke(llm, batch, sampling_params)
#         all_responses.extend(responses)
#     return all_responses

# def vllm_api_invoke(llm, inputs:list, sampling_params, batch_size=1, time_out=600):
#     API_URL = "http://localhost:8000/v1/completions"
#     HEADERS = {
#         "Content-Type": "application/json",
#     }
#     if isinstance(inputs, str):
#         inputs = [inputs]
#     payload = {
#         "model": "14B", 
#         "prompt": inputs, 
#         "temperature": sampling_params.temperature, 
#         "top_p": sampling_params.top_p, 
#         "max_tokens": sampling_params.max_tokens
#     }
#     resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=time_out)
#     resp.raise_for_status()
#     data = resp.json()
#     return [choice["text"] for choice in data["choices"]]

def vllm_api_invoke(llm, inputs: list, sampling_params, batch_size: int = 1, time_out: int = 600):
    API_URL = "http://localhost:8000/v1/completions"
    # API_URL = "http://localhost:8000/v1/chat/completions"
    HEADERS = {
        "Content-Type": "application/json",
    }

    if isinstance(inputs, str):
        inputs = [inputs]
    all_responses = []
    n = getattr(sampling_params, "n", 1)
    for i in tqdm(range(0, len(inputs), batch_size)):
        batch_inputs = inputs[i:i + batch_size]
        payload = {
            "model": "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-14B",
            "prompt": batch_inputs,
            "temperature": sampling_params.temperature,
            "top_p": sampling_params.top_p,
            "max_tokens": sampling_params.max_tokens,
            "n": n,
        }
        resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=time_out)
        resp.raise_for_status()
        data = resp.json()
        choices = data["choices"]
        if n > 1:
            for j in range(len(batch_inputs)):
                start = j * n
                end = (j + 1) * n
                batch_choices_for_prompt = choices[start:end]
                texts = [c["text"] for c in batch_choices_for_prompt]
                all_responses.append(texts)
        else:
            all_responses.extend([c["text"] for c in choices])
    return all_responses

def get_logger(log_file_path):
    logger = logging.getLogger('my_logger')
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    return logger

def save_txt(str, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(str)

def load_txt(path):
    with open(path, 'r', encoding='utf-8') as file:
        return file.read()

def save_pkl(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(data, f)

def load_pkl(path):
    with open(path, 'rb') as f:
        return pickle.load(f)

def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_jsonl(data, path):
    with open(path, 'a') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

def load_jsonl(path):
    lines = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            lines.append(json.loads(line.strip()))
    return lines

def cn_convert(str):
    return convert(str, 'zh-cn')

def str_idx_in_list(s, lst):
    try:
        return lst.index(s)
    except:
        return None

# transformers 库导入大模型
# def llm_invoke(model, tokenizer, inputs:list, temperature=0.6, top_p=0.9, max_length=512, batch_size=1): 
#     all_responses = []
#     for i in range(0, len(inputs), batch_size):
#         batch_inputs = tokenizer(inputs[i:i + batch_size], padding=True, truncation=True, return_tensors="pt")
#         with torch.no_grad():
#             outputs = model.generate(
#                 batch_inputs["input_ids"], 
#                 temperature=temperature, 
#                 top_p=top_p, 
#                 max_length=max_length, 
#                 num_return_sequences=1, # 每个输入返回 1 个输出
#                 no_repeat_ngram_size=3, # 防止重复生成
#                 pad_token_id=tokenizer.eos_token_id # 填充的 token id
#             )
#         responses = [tokenizer.decode(output, skip_special_tokens=True) for output in outputs]
#         all_responses.extend(responses)
#     return all_responses

# API 大模型
# def vllm_invoke(llm, inputs:list, sampling_params, batch_size=1, temperature=0.5, top_p=0.95, max_tokens=4096, time_out=600):
#     API_URL = "http://localhost:8000/v1/completions"
#     HEADERS = {
#         "Content-Type": "application/json",
#     }
#     if isinstance(inputs, str):
#         inputs = [inputs]
#     payload = {
#         "model": "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B", 
#         "prompt": inputs, 
#         "temperature": temperature, 
#         "top_p": top_p, 
#         "max_tokens": max_tokens
#     }
#     resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=time_out)
#     resp.raise_for_status()
#     data = resp.json()
#     return [choice["text"] for choice in data["choices"]]
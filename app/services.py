import base64
import requests
from .config import DASHSCOPE_API_KEY
from fastapi import HTTPException

# 调用通义千问文字 API
def call_qwen(prompt: str, history: list):
    DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="API Key 未设置")
    # 构造请求头
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    # 构造请求体
    messages = [{"role": "user", "content": msg} for msg in history]
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": "qwen2.5-14b-instruct",
        "messages": messages
    }

    try:
        response = requests.post(DASHSCOPE_API_URL, headers=headers, json=data)
        response.raise_for_status()
        response_json = response.json()
        if "choices" in response_json and len(response_json["choices"]) > 0:
            return response_json["choices"][0]["message"]["content"]
        else:
            return "AI 返回了空内容。"
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"调用 AI 失败: {str(e)}")

# 调用通义千问视觉API   qwen2.5-vl-72b-instruct
def call_qwen_vl(image_path: str, prompt: str, imageform: str):
    DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="API Key 未设置")
    # 构造请求头
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        # 构造请求体
        payload = {
            "model": "qwen2.5-vl-32b-instruct",  # 指定模型名称
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "根据要求做出应答，保证格式正确"}],
                },
                {
                    'role': 'user',
                    'content': [
                        {
                            "type": "image_url",
                            # 需要注意，传入Base64，图像格式（即image/{format}）需要与支持的图片列表中的Content Type保持一致。"f"是字符串格式化的方法。
                            # PNG图像：  f"data:image/png;base64,{base64_image}"
                            # JPEG图像： f"data:image/jpeg;base64,{base64_image}"
                            # WEBP图像： f"data:image/webp;base64,{base64_image}"
                            "image_url": {"url": f"data:image/{imageform};base64,{image_path}"},
                        },
                        {"type": "text", "text": f"{prompt}"},
                    ]
                },
            ]
        }
        # 发送 POST 请求
        response = requests.post(DASHSCOPE_API_URL, headers=headers, json=payload)
        # 检查响应状态码
        if response.status_code != 200:
            raise Exception(f"API 返回错误: {response.text}")
        # 解析响应内容
        result = response.json()
        print(f"完整 API 响应:{result}\n\n")  # 打印完整响应以便调试
        return result
    except FileNotFoundError:
        print(f"图片文件不存在: {image_path}")
        return None
    except Exception as e:
        print(f"Error calling visual API: {e}")
        return None

# 调用DeepseekAPI deepseek-r1-distill-qwen-7b
def call_deepseek_r1_distill(prompt: str):
    DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    # 检查 API Key 是否设置
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="API Key 未设置")
    # 构造请求头
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    # 构造请求体
    data = {
        "model": "deepseek-r1-distill-qwen-7b",  # 指定模型名称
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,  # 用户输入内容
                }
            ]
        },
        "parameters": {
            "result_format": "message"  # 返回结果格式
        }
    }

    try:
        # 发送 POST 请求
        response = requests.post(DASHSCOPE_API_URL, headers=headers, json=data)
        # 检查响应状态码
        response.raise_for_status()
        # 解析响应内容
        result = response.json()
        output = result.get("output", None)  # 假设 API 返回的字段名为 "output"
        if output is None:
            raise Exception("API 返回了空内容。")
        # 提取回复内容
        choices = output.get("choices", [])
        if choices and isinstance(choices, list):
            return choices[0].get("message", {}).get("content", "")
        else:
            raise Exception("API 返回的内容格式不正确。")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"调用 AI 失败: {str(e)}")
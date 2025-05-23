import requests
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException

from .config import DASHSCOPE_API_KEY, ENVPATH
from .utils import mkdir

# --- 通用业务 ---
# -- AI业务 --
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
    # 构造请求体
    payload = {
        "model": "qwen2.5-vl-32b-instruct",  # 指定模型名称
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "根据要求做出应答，保证格式正确"}], },
            {
                'role': 'user', 'content':
                [
                    {
                        "type": "image_url", "image_url":
                        {
                            "url": f"data:image/{imageform};base64,{image_path}"
                        },
                    },
                # 需要注意，传入Base64，图像格式（即image/{format}）需要与支持的图片列表中的Content Type保持一致。"f"是字符串格式化的方法。
                # PNG图像：  f"data:image/png;base64,{base64_image}"
                # JPEG图像： f"data:image/jpeg;base64,{base64_image}"
                # WEBP图像： f"data:image/webp;base64,{base64_image}"
                    {
                        "type": "text", "text": f"{prompt}"
                    },
                ]
            },
        ]
    }
    try:
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

# 指向学习建议下载部分的定向API
def call_deepseek_r1_distill_download(username: str):
    DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
    # 检查 API Key 是否设置
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="API Key 未设置")

    # 创建用户文件夹和用户画像文件路径
    user_folder = Path(ENVPATH) / username
    mkdir(user_folder)
    user_profile_path = user_folder / f"{username}_profile.txt"

    # 加载用户画像（如果存在）
    user_profile = ""
    if user_profile_path.exists():
        with open(user_profile_path, "r", encoding="utf-8") as f:
            user_profile = f.read()
    else:
        raise Exception("用户画像为空")

    # 构造请求头
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }
    # 构造请求体
    Preprompt = {
        "advice": [
            {
                "method": "给出应对困难知识点的方法",
                "schedule": "根据用户画像，在学段内，结合现实给出以后的学习计划"
            }
        ]
    }
    data = {
        "model": "deepseek-r1-distill-qwen-7b",  # 指定模型名称
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": f"根据用户画像，给出用户学习建议。{user_profile}"
                               f"请按照以下 JSON 格式返回结果："
                               f"{Preprompt}",  # 用户输入内容
                }
            ]
        },
        "parameters": {
            "result_format": "message"# 返回结果格式
        }
    }
    try:
        # 发送 POST 请求
        response = requests.post(DASHSCOPE_API_URL, headers=headers, json=data)
        # 检查响应状态码
        response.raise_for_status()
        # 解析响应内容
        result = response.json()
        print("API 响应:", result)
        output = result.get("output", None)
        if not output or "choices" not in output:
            raise ValueError("API 返回的 output 字段为空或格式不正确")
        choices = output.get("choices", [])
        if not isinstance(choices, list) or len(choices) == 0:
            raise ValueError("API 返回的 choices 字段为空或格式不正确")
        # 提取消息内容
        message_content = choices[0].get("message", {}).get("content", "")
        if not message_content:
            raise ValueError("API 返回的消息内容为空")
        # 将消息内容解析为 JSON
        try:
            advice_data = eval(message_content.strip("```json\n").strip("\n```"))
        except Exception as e:
            raise ValueError(f"解析消息内容为 JSON 失败: {str(e)}")
        # 提取 advice 列表
        advice_list = advice_data.get("advice", [])
        if not isinstance(advice_list, list) or len(advice_list) == 0:
            raise ValueError("advice 列表为空或格式不正确")
        # 写入文件并返回结果
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = user_folder / f"{username}_advice.txt"
        with open(file_path, "a", encoding="utf-8") as f:
            f"在{date_str}\n\n{username}获取学习建议：\n\n"
            for advice in advice_list:
                method = advice.get("method", "")
                schedule = advice.get("schedule", "")
                f.write(
                    f"方法: {method}\n\n计划: {schedule}\n\n"
                )
        return {"status": "success", "response": advice_list}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"调用 AI 失败: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"解析 API 响应失败: {str(e)}")
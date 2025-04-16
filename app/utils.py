import base64
import json
from pathlib import Path

# 创建文件夹
def mkdir(path):
    folder_path = Path(path)
    try:
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"文件夹 '{folder_path}' 创建成功")
    except FileExistsError:
        print(f"文件夹 '{folder_path}' 已存在")

#  base 64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def extract_json_content(api_response):
    try:
        # 提取 choices 列表
        choices = api_response.get("choices", [])
        if not choices:
            raise ValueError("API 响应中缺少 'choices' 字段")

        # 提取第一个 choice 的 message content
        first_choice = choices[0]
        message = first_choice.get("message", {})
        content = message.get("content", "")

        if not content:
            raise ValueError("API 响应中缺少 'content' 字段")

        # 去除 Markdown 包裹的 ```json 和 ```
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()  # 去掉开头的 "```json" 和结尾的 "```"

        # 尝试将内容解析为 JSON
        parsed_content = json.loads(content)
        return parsed_content

    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析为合法的 JSON: {e}")
    except Exception as e:
        raise ValueError(f"处理 API 响应时出错: {e}")
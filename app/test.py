# 测试图片路径（替换成实际的图片路径）
from app.services import call_qwen_vl
from app.utils import encode_image, extract_json_content
import json

TEST_IMAGE_PATH = r"F:\TC\Test_Problem.jpg"  # 使用原始字符串避免转义问题

# 测试图片格式（根据图片类型选择：image/png, image/jpeg 等）
IMAGE_FORMAT = "jpg"  # 根据您的图片格式调整

# 测试提示文本
PROMPT = (
    "请按照以下 JSON 格式返回结果，不要使用markdown格式："
    "{"
    '    "题目": "识别到的完整题目，如果是选择题，需要加入选项",'
    '    "正确答案": {'
    '        "详细解析": "详细的解答过程",'
    '        "考察知识点": ["知识点1", "知识点2"]'
    "    }"
    "}"
)

if __name__ == "__main__":
    TEST_IMAGE_PATH = encode_image(TEST_IMAGE_PATH)
    # 调用函数
    try:
        result = call_qwen_vl(TEST_IMAGE_PATH, PROMPT, IMAGE_FORMAT)
        if result:
            content = extract_json_content(result)
            ai_response = content
            # 提取题目部分
            question = ai_response.get("题目", "").strip()
            if not question:
                raise ValueError("无法从模型响应中提取题目内容")
            # 提取正确答案部分
            correct_answer = ai_response.get("正确答案", {})
            detailed_explanation = correct_answer.get("详细解析", "").strip()
            knowledge_points = correct_answer.get("考察知识点", [])
            print(f"{question}\n{correct_answer}\n{detailed_explanation}\n{knowledge_points}")
        else:
            print("API 调用失败或返回空结果。")
    except Exception as e:
        print(f"测试程序出错: {e}")
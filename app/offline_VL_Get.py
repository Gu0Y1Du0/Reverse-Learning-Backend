from transformers import Qwen2_5_VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
from app.config import Qwen2_5_VL_3B_Instruct_gptq_Int4_dir

# --- 模型与分词器加载 ---
model_name_or_path = Qwen2_5_VL_3B_Instruct_gptq_Int4_dir
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    model_name_or_path,
    torch_dtype="auto",
    device_map="auto"
)
processor = AutoProcessor.from_pretrained(model_name_or_path)
model.eval()

# --- 识题API ---
def vl_question(Photograph: str, prompt: str, max_new_tokens: int):
    # 构建 messages 格式
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": Photograph},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    text = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    # 编码输入
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt"
    ).to("cuda")

    # 生成回答
    generated_ids = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens
    )

    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]

    response = processor.batch_decode(
        generated_ids_trimmed,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=False
    )[0]

    # 后处理：移除描述性内容，保留纯文字
    if "包含以下文字：" in response:
        response = response.split("包含以下文字：")[1].strip()

    return response
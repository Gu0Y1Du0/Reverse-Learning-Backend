from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
from app.config import Qwen2_5_Math_1_5B_Instruct_bnb_4bit_dir

# --- 模型与分词器加载 ---
model_name_or_path = Qwen2_5_Math_1_5B_Instruct_bnb_4bit_dir
model = AutoModelForCausalLM.from_pretrained(
    model_name_or_path,
    torch_dtype="auto",
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
model.eval()  # 切换到评估模式

# --- 解题API ---
def text_response(system_message: str, prompt: str, max_new_tokens: int):
    # 构建 messagesTIR 格式
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]

    text = tokenizer.apply_chat_template(
        conversation=messages,
        tokenize=False,
        add_generation_prompt=True
    )
    # 编码输入
    model_inputs = tokenizer(
        [text],
        return_tensors="pt",
    ).to("cuda")

    # 生成回答
    with torch.no_grad():
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
        )

    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]

    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    return response
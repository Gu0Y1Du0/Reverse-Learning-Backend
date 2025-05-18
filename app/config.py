import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
# 配置项
DATABASE_URL = os.environ.get('DATABASE_URL')
FRONT_URL = os.environ.get('front_url')
ENVPATH = os.environ.get('envpath')
DASHSCOPE_API_KEY = os.environ.get('dashscope_api_key')

model_dir = os.environ.get('model_dir')
Qwen2_5_Math_1_5B_Instruct_bnb_4bit_dir = os.environ.get("QWEN2_5_MATH_1_5B_INSTRUCT_BNB_4BIT_DIR")
Qwen2_5_VL_3B_Instruct_gptq_Int4_dir = os.environ.get("QWEN2_5_VL_3B_INSTRUCT_GPTQ_INT4_DIR")
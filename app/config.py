import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
# 配置项
DATABASE_URL = os.environ.get('DATABASE_URL')
FRONT_URL = os.environ.get('front_url')
ENVPATH = os.environ.get('envpath')
DASHSCOPE_API_KEY = os.environ.get('dashscope_api_key')

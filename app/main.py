from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from .config import FRONT_URL
from .routes import router

app = FastAPI()

# 引入路由
app.include_router(router)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONT_URL],  # 允许的前端地址
    allow_credentials=True,
    allow_methods=["*"],  # 允许的 HTTP 方法
    allow_headers=["*"],  # 允许的请求头
)
#!/usr/bin/env python3
"""
FastAPI 应用入口

这是 Agent Loop 项目的主入口文件，负责：
1. 创建和配置 FastAPI 应用
2. 设置 CORS 中间件
3. 初始化数据库
4. 注册路由模块
5. 提供健康检查端点

架构说明：
- 使用模块化设计，将路由拆分到独立文件
- 使用依赖注入模式共享数据库实例
- 支持热重载开发模式
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from backend.storage.database import Database
from backend.api import routes_chat
from backend.api import routes_conversations

# 加载环境变量
load_dotenv(override=True)

# 获取模型配置
MODEL = os.environ.get("MODEL_ID", "claude-3-5-sonnet-20241022")


def get_model_info() -> dict:
    """获取模型配置信息。"""
    return {
        "model": MODEL,
        "cwd": os.getcwd(),
        "base_url": os.getenv("ANTHROPIC_BASE_URL", "default")
    }


# 初始化数据库
db = Database()

# 创建 FastAPI 应用
app = FastAPI(
    title="Agent API",
    description="AI Agent with tool execution and conversation history",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注入数据库到路由模块
routes_chat.init_db(db)
routes_conversations.init_db(db)

# 注册路由
app.include_router(routes_chat.router)
app.include_router(routes_conversations.router)


@app.get("/api/health")
def health():
    """健康检查端点。"""
    info = get_model_info()
    return {
        "status": "ok",
        **info
    }


if __name__ == "__main__":
    import uvicorn
    print("[INFO] Starting Agent Loop API...")
    print(f"[INFO] Model: {get_model_info()['model']}")
    print(f"[INFO] Working directory: {get_model_info()['cwd']}")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

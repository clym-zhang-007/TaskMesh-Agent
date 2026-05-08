# 多 Agent 系统

一个支持多 Agent 协作的 AI 编程助手系统，具备任务编排、工具调用、流式响应、持久化任务管理，以及自主队友协作能力。

## 特性概览

- 单 Agent 对话式编排
- 持久化任务管理与依赖控制
- 多 Agent / teammate 自主协作
- SSE 流式响应
- 三层上下文压缩
- 技能按需加载
- 子 Agent 委托执行

## 项目结构

```text
backend/
├── main.py                     # 后端入口
├── api/                        # HTTP 路由层
│   ├── routes_chat.py
│   └── routes_conversations.py
├── core/                       # Agent 核心编排层
│   ├── agent.py
│   ├── context_manager.py
│   ├── skill_loader.py
│   ├── task_manager.py
│   ├── todo_manager.py
│   └── tools.py
├── schema/                     # Pydantic 数据结构与接口契约
│   └── models.py
├── storage/                    # 存储实现层
│   └── database.py
└── team/                       # 多 Agent 协作子系统
    ├── message_bus.py
    ├── subagent.py
    └── teammate_manager.py

frontend/
├── src/
├── index.html
└── package.json

tests/
├── test_main.py
└── test_multiagent.py
```

## 架构分层

- `api/`：对外暴露 HTTP 接口
- `core/`：主 Agent 编排、工具调度、任务机制
- `schema/`：数据结构与接口契约
- `storage/`：数据库与持久化实现
- `team/`：多 Agent 协作能力

## 快速开始

### 1. 安装后端依赖

```bash
pip install -r backend/requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写：

```env
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_BASE_URL=https://api.anthropic.com
MODEL_ID=claude-sonnet-4-20250514
MAX_ITERATIONS=50
```

### 3. 启动后端

```bash
python backend/main.py
```

或：

```bash
uvicorn backend.main:app --reload --port 8000
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 使用 Docker 启动前后端

```bash
docker compose up --build
```

- 后端: `http://localhost:8000`
- 前端: `http://localhost:5173`

## 测试

```bash
pytest tests/test_main.py -v
pytest tests/test_multiagent.py -v
```

## Git 仓库说明

以下内容默认不会提交：
- `.env`
- `.team/`
- `*.db`
- `*.jsonl`
- 各类日志、缓存、测试输出

如果你希望提交本地参考资料，如 `agents/` 或 `skills/`，请根据需要调整 `.gitignore`。

## 文档

- `backend/README.md`：后端结构与模块说明
- `USAGE.md`：使用指南与工作流示例

## 许可证

MIT

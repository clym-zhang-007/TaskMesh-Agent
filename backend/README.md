# Agent Loop Backend

AI Agent 后端服务，提供对话管理、工具执行、流式响应，以及多 Agent 协作能力。

## 项目结构

```text
backend/
├── main.py                     # FastAPI 后台入口
├── api/                        # HTTP 路由层
│   ├── routes_chat.py          # 聊天流式接口
│   └── routes_conversations.py # 对话管理接口
├── core/                       # Agent 核心编排层
│   ├── agent.py                # 主 Agent 循环与流式执行
│   ├── tools.py                # 工具定义与处理器
│   ├── context_manager.py      # 上下文压缩策略
│   ├── skill_loader.py         # 技能加载机制
│   ├── task_manager.py         # 持久化任务编排与认领
│   └── todo_manager.py         # 短期任务清单机制
├── schema/                     # 数据结构与接口契约
│   └── models.py               # Pydantic schemas
├── storage/                    # 存储实现层
│   └── database.py             # SQLite 数据库实现
├── team/                       # 多 Agent 协作子系统
│   ├── teammate_manager.py     # 队友生命周期管理
│   ├── message_bus.py          # 队友消息通信
│   └── subagent.py             # 子 Agent 执行能力
├── requirements.txt            # Python 依赖
└── Dockerfile                  # Docker 配置
```

## 模块职责

### `main.py`
- 创建 FastAPI 应用
- 配置 CORS 中间件
- 初始化数据库
- 注册 API 路由

### `api/`
对外提供 HTTP 接口：
- `routes_chat.py`：SSE 流式聊天接口
- `routes_conversations.py`：对话 CRUD 接口

### `core/`
主 Agent 的运行时与编排逻辑：
- `agent.py`：主循环、工具调度、流式事件输出
- `tools.py`：工具定义、工具处理器、命令执行安全控制
- `context_manager.py`：上下文压缩与历史裁剪
- `skill_loader.py`：按需技能加载
- `task_manager.py`：持久化任务的编排、认领、扫描
- `todo_manager.py`：短期内存任务清单

### `schema/`
定义数据结构和接口契约：
- 聊天请求/响应
- 消息结构
- 对话结构
- 工具执行结构

### `storage/`
负责底层存储实现：
- SQLite 连接
- 对话、消息、任务的持久化

### `team/`
封装多 Agent 协作能力：
- 队友生命周期管理
- 消息总线
- 子 Agent 执行

## 启动方式

在项目根目录执行：

```bash
python backend/main.py
```

或使用 uvicorn：

```bash
uvicorn backend.main:app --reload --port 8000
```

启动后可访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 环境变量

常用配置：

```env
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_BASE_URL=https://api.anthropic.com
MODEL_ID=claude-sonnet-4-20250514
MAX_ITERATIONS=50
```

## 依赖安装

推荐在项目根目录执行：

```bash
pip install -r backend/requirements.txt
```

## 测试

在项目根目录执行：

```bash
pytest tests/test_main.py -v
pytest tests/test_multiagent.py -v
```

## 说明

- `schema/` 负责数据契约，不负责存储
- `storage/` 只保留存储实现，不混入编排逻辑
- `core/` 负责 Agent 核心编排
- `team/` 是多 Agent 协作子系统，供 `core.agent` 调用

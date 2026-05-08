# 使用指南

本文档说明如何使用多 Agent 系统进行单 Agent 编排、持久化任务管理与多 Agent 协作。

## 启动

### 本地启动

先启动后端：

```bash
python backend/main.py
```

如果使用前端，再在 `frontend/` 目录启动开发服务器：

```bash
npm install
npm run dev
```

### Docker 启动

```bash
docker compose up --build
```

## 核心工作模式

### 1. 短期任务：`todo`
适用于单次对话内的 3-5 步小任务。

示例：

```text
用户: 创建 3 个配置文件
Agent:
1. 调用 todo 创建任务列表
2. 逐个执行文件创建
3. 更新 todo 状态直到完成
```

### 2. 长期任务：`task_create` / `task_update`
适用于跨对话、可持久化、带依赖关系的任务。

示例：

```text
用户: 构建认证系统
Agent:
1. task_create("设计数据库")
2. task_create("实现用户模型")
3. task_create("实现 API")
4. 使用 task_update 设置依赖关系
```

### 3. 多 Agent 协作：`spawn_teammate`
适用于需要并行推进的任务。

示例：

```text
用户: 同时开发前端和后端
Agent:
1. 创建多个持久化任务
2. 生成多个 teammate
3. teammate 自动扫描并认领任务
4. 使用 list_teammates/read_inbox 跟踪进度
```

## 推荐工作流

### 工作流 1：普通编码任务

```text
1. read_file / 分析代码
2. todo 建立短期步骤
3. 修改文件
4. 验证结果
5. 更新 todo 完成状态
```

### 工作流 2：长期项目拆解

```text
1. task_create 拆解任务
2. task_update 设置 blocked_by
3. 分阶段推进
4. task_list / task_list_all 跟踪进度
```

### 工作流 3：多 Agent 协作

```text
1. task_create 创建可独立执行的任务
2. spawn_teammate 指定角色与初始提示
3. list_teammates 查看状态
4. read_inbox 查看汇报
5. send_message / broadcast 做协调
6. shutdown_teammate 做收尾
```

## 最佳实践

### 任务粒度
- 太大：`构建整个系统`
- 太小：`创建一个变量`
- 合适：`实现用户注册 API`

### teammate 角色定义
- 不清晰：`帮我写代码`
- 清晰：`FastAPI 开发者，负责实现认证接口`

### 任务描述
- 不清晰：`做一些改进`
- 清晰：`重构 auth.py，提取重复鉴权逻辑`

## 故障排查

### 队友没有认领任务
- 确认任务状态是 `pending`
- 确认任务没有未满足的依赖
- 确认 teammate 处于 `idle` 或 `working`

### 队友卡住不动
- 使用 `read_inbox()` 查看是否有错误回报
- 关闭并重新生成 teammate

### 任务执行失败
- 检查任务描述是否足够具体
- 检查角色是否匹配任务类型
- 检查环境变量和依赖是否完整

## 相关文档

- `README.md`：项目总览
- `backend/README.md`：后端结构说明
- `tests/test_multiagent.py`：多 Agent 行为示例

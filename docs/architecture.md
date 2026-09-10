# Atelier OJ 架构说明

本文说明当前代码边界与依赖方向，供维护、验收和后续扩展使用。业务行为以课程
[API 文档](https://dbg-course.github.io/python-docs/oj/api/)为准。

## 目录职责

```text
src/oj/
├── main.py                 # 仅负责应用装配与 lifecycle
├── routers/                # HTTP 参数、权限依赖、课程响应 envelope
├── ai/                     # AI 命题独立领域包
│   ├── authoring.py        # 配置、流式调用、用量、取消与质量门禁
│   ├── experience.py       # 草稿、局部修改、助手等持久化工作流
│   ├── policy.py           # 模型选择与计价策略
│   ├── prompts.py          # 版本化系统提示词
│   ├── sections.py         # 局部修改 schema 与合并规则
│   ├── presentation.py     # 题面展示质量检查
│   └── transport.py        # DNS 固定、SSE 大小限制与网络边界
├── auth.py / security.py   # Session 与 bcrypt
├── schemas.py              # 输入、持久化内容与模型输出的信任边界
├── database.py             # SQLite schema、迁移与异步连接
├── problem_store.py        # 题目 JSON 原子存储
├── languages.py            # 语言配置及安全命令模板
├── judge.py                # 编译、运行、资源限制和输出比对
├── submissions.py          # 后台评测任务生命周期与结果持久化
└── evaluation.py           # 评测结果的统一解释与可见性投影

frontend/                   # 课程要求的 Streamlit 默认入口
web/                        # React 可选入口、共享前端组件与浏览器测试
data/problem_seeds/         # 可版本化、可 reset 的初始题库
tests/                      # API、权限、runner、AI 与 UI 回归测试
scripts/                    # 启动、配置、验收和报告构建脚本
docs/                       # 架构、验收证据、实验报告与任务说明
output/pdf/                 # 最终 PDF 报告固定输出目录
```

## 依赖方向

```text
Streamlit / React
        │ REST + HttpOnly Session Cookie
        ▼
FastAPI routers
        │
        ├── core services ──► SQLite / JSON store
        │       └───────────► async judge subprocesses
        │
        └── AI package ─────► model provider + local judge quality gates
```

- `routers` 不实现持久化细节，只处理 HTTP contract、权限和响应裁剪。
- `schemas` 是外部输入与模型输出进入系统前的统一校验边界。
- `judge` 不依赖 FastAPI，可由提交管理与 AI 验证复用。
- `ai` 可以依赖 OJ core，但 OJ core 不依赖 AI；只有 `main.py` 装配两者。
- Streamlit 与 React 均通过 REST API 工作，不直接访问数据库或题目文件。

## 异步与任务所有权

- 所有课程 API endpoint 均为 `async def`，SQLite 使用 `aiosqlite`。
- 文件 I/O、bcrypt、DNS 查询等阻塞工作使用 `asyncio.to_thread`。
- `SubmissionManager` 拥有评测 Task；`AIExperience` 拥有命题 Task。
- shutdown、reset、rejudge 和 AI cancel 都会取消并等待对应 Task，防止旧任务回写新状态。
- `ProblemStore` 和提交入口分别用锁保护原子写与每题每用户限频检查。

## 数据与安全边界

- 题目：每题一个 JSON，临时文件写入、`fsync` 后原子替换。
- 关系数据：SQLite + WAL；schema 升级前备份，迁移通过 `user_version` 幂等执行。
- 密码：bcrypt；模型密钥：Fernet 加密；两者均不进入普通响应或日志。
- 评测命令：不经过 shell，只允许有限 executable 与 `{src}` / `{exe}` 占位符。
- Linux runner：墙钟、地址空间、文件大小、进程数量、输出大小和进程组回收。
- 当前 runner 是可信单机课程环境，不是生产级多租户沙箱；公网部署仍需容器/VM、
  cgroup、seccomp 与网络隔离。

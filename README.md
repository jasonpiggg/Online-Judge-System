# Atelier OJ

> 程序设计训练（Python）实验二 · Online Judge System

Atelier OJ 是一个功能完整的小型在线评测系统：FastAPI 提供全异步 REST API，
Streamlit 提供浏览器工作台，Linux runner 执行 Python 与 C++14，并包含用户权限、
访问审计及可中断的 AI 智能命题。实现对应课程 Step 1–6 与 Advance R1–R4。

## 功能矩阵

| 模块 | 实现内容 |
| --- | --- |
| Step 1 · 题目管理 | JSON 独立存储、原子写入、完整 CRUD、字段校验、初始题目 |
| Step 2 · 评测控制 | Python/C++14、异步子进程、逐点判题、资源与输出限制、七类 verdict |
| Step 3 · 提交管理 | 后台评测、状态恢复、组合筛选、分页、限频、管理员重测 |
| Step 4 · 用户管理 | bcrypt、服务端 Session、注册登录、角色与禁用、实时统计 |
| Step 5 · 日志审计 | 测试点日志、公开策略、访问成功/拒绝审计、管理员筛选 |
| Step 6 · Web UI | Streamlit 响应式工作台、题目/提交/管理/AI 全流程 |
| Advance · AI 命题 | 加密配置、流式兼容 API、真实取消、批判改进、本地验证、Token 计费 |

所有业务响应统一为 `{"code": HTTP状态码, "msg": "...", "data": ...}`；
FastAPI 的请求校验错误按实验要求转换为 HTTP 400。

## 架构

```text
Browser
  │
  ▼
Streamlit UI ── requests.Session / HttpOnly Cookie ── FastAPI
                                                        ├── JSON problem store
                                                        ├── SQLite metadata & audit
                                                        ├── async judge task registry
                                                        └── streaming AI task registry
                                                                 │
                                          Linux subprocess / rlimit / psutil
```

- `src/oj/routers/`：课程 API 路由、依赖鉴权与统一错误处理。
- `src/oj/*.py`：认证、数据库、题目存储、评测、提交和 AI 工作流。
- `frontend/`：仅通过 REST API 操作后端的 Streamlit 客户端。
- `data/problem_seeds/`：版本化的初始题目；运行数据保存在已忽略的 `var/`。
- `tests/`：模型、API、权限矩阵、runner、AI mock 与界面 smoke tests。

## 快速开始

完整评测环境为 Ubuntu/WSL2，要求 Python 3.12 与 `g++`。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen --extra dev --extra report
cp .env.example .env
uv run -- bash scripts/run.sh
```

Windows 可用于界面开发；原生 Windows 的资源限制不宣称与 Linux 等价。

```powershell
winget install --id=astral-sh.uv -e
uv sync --frozen --extra dev --extra report
Copy-Item .env.example .env
uv run -- powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

没有 `uv` 时仍可使用 `python -m venv .venv` 后执行
`pip install -r requirements-dev.txt`；正式验收与 CI 使用已提交的 `uv.lock`。

打开 <http://127.0.0.1:8501>。后端 API 和交互文档分别位于
<http://127.0.0.1:8000> 与 <http://127.0.0.1:8000/docs>。

初始管理员：

- 用户名：`admin`
- 密码：`admintestpassword`

首次启动会创建初始题目和语言。`POST /api/reset/` 可由管理员恢复干净状态。

## 配置

复制 `.env.example` 后按需修改：

| 变量 | 用途 |
| --- | --- |
| `OJ_DATABASE_PATH` | SQLite 路径，默认 `var/oj.db` |
| `OJ_PROBLEM_DIR` | 题目 JSON 目录，默认 `var/problems` |
| `OJ_SESSION_TTL_SECONDS` | Session 有效期 |
| `OJ_COOKIE_SECURE` | HTTPS 部署时应设为 `true` |
| `OJ_AI_ENCRYPTION_KEY` | AI API key 加密主密钥；生产环境必须显式设置 |
| `OJ_ALLOW_PRIVATE_AI_ENDPOINTS` | 仅本地 mock 测试可设为 `true` |
| `OJ_API_URL` | Streamlit 访问后端的地址 |

AI 配置保存在数据库中，API key 使用 Fernet 加密，接口只返回
`api_key_configured`。本地开发若未提供主密钥，会在运行数据目录生成持久化
`.ai-key`；迁移或备份数据库时应一并保留。生产环境必须显式设置环境主密钥。

## 测试与质量门禁

```bash
uv run ruff check src frontend tests scripts
uv run mypy src
uv run pytest --cov=oj --cov-branch --cov-report=json:coverage.json
uv run python scripts/check_coverage.py coverage.json
uv run pip-audit --local --skip-editable
```

GitHub Actions 在 Ubuntu、Python 3.12 和系统 `g++` 下执行上述检查，并额外覆盖
Python/C++ 的完整 verdict 矩阵、异步状态、权限与 AI 流式 mock。当前基线为
98 个测试通过，后端行覆盖率 97.67%、分支覆盖率 93.07%；门槛分别为 90% 和 85%。

## API 与报告

- [API 参考](docs/API.md)
- [实验报告（Markdown）](docs/experiment-report.md)
- [实验报告（PDF）](output/pdf/atelier-oj-experiment-report.pdf)
- [评分点核对表](docs/scoring-checklist.md)
- [v1.1 测试记录](docs/test-record.md)
- [OpenAPI 交互文档](http://127.0.0.1:8000/docs)

## 安全边界

系统对题号、命令模板、请求长度、输出大小和 AI 服务地址做白名单或上限校验；
评测进程使用独立临时目录、最小环境、进程组终止、墙钟超时、RSS 监控及 Linux
`rlimit`。这些措施适用于课程实验和可信单机环境，**不能替代容器、虚拟机、seccomp、
cgroup 与网络隔离**。默认只绑定 localhost，禁止将任意代码执行服务直接暴露到公网。

## Git 工作流

项目按短期 feature branch、Conventional Commits、真实 Pull Request 和 CI 门禁推进；
每个阶段在检查通过后以 merge commit 合入 `main`。完整提交与 PR 历史保留在 GitHub。

课程说明：<https://dbg-course.github.io/python-docs/oj/>

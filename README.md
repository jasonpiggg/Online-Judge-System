# Atelier OJ

> 程序设计训练（Python）实验二 · Online Judge System

Atelier OJ 是一个功能完整的小型在线评测系统：FastAPI 提供全异步 REST API，
React + TypeScript 提供默认浏览器工作台，Streamlit 保留为兼容入口，Linux runner 执行 Python 与 C++14，并包含用户权限、
访问审计及可中断的 AI 智能命题。实现对应课程 Step 1–6 与 Advance R1–R4。

## 功能矩阵

| 模块 | 实现内容 |
| --- | --- |
| Step 1 · 题目管理 | JSON 独立存储、原子写入、完整 CRUD、字段校验、初始题目 |
| Step 2 · 评测控制 | Python/C++14、异步子进程、逐点判题、资源与输出限制、七类 verdict |
| Step 3 · 提交管理 | 后台评测、状态恢复、组合筛选、分页、限频、管理员重测 |
| Step 4 · 用户管理 | bcrypt、服务端 Session、注册登录、角色与禁用、实时统计 |
| Step 5 · 日志审计 | 测试点日志、公开策略、访问成功/拒绝审计、管理员筛选 |
| Step 6 · Web UI | 白底 React 工作台、Monaco、Markdown/数学公式、移动端标签、版本草稿与 AI 做题助手 |
| Advance · 命题中心 | 加密配置、流式任务、版本草稿、独立 oracle 对拍、mutation score、Token 计费 |

所有业务响应统一为 `{"code": HTTP状态码, "msg": "...", "data": ...}`；
FastAPI 的请求校验错误按实验要求转换为 HTTP 400。

## 架构

```text
Browser
  │
  ▼
React UI / Streamlit ── HttpOnly Session Cookie ── FastAPI
                                                        ├── JSON problem store
                                                        ├── SQLite metadata & audit
                                                        ├── async judge task registry
                                                        └── streaming AI task registry
                                                                 │
                                          Linux subprocess / rlimit / psutil
```

- `src/oj/routers/`：课程 API 路由、依赖鉴权与统一错误处理。
- `src/oj/*.py`：认证、数据库、题目存储、评测、提交和 AI 工作流。
- `web/`：默认 React 前端；构建到 `web/dist/`，由 FastAPI 同源提供。
- `frontend/`：保留的 Streamlit 兼容客户端。
- `data/problem_seeds/`：版本化的初始题目；运行数据保存在已忽略的 `var/`。
- `tests/`：模型、API、权限矩阵、runner、AI mock 与界面 smoke tests。

## 快速开始

完整评测环境为 Ubuntu/WSL2，要求 Python 3.12 与 `g++`。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen --extra dev --extra report
cp .env.example .env
(cd web && npm ci && npm run build)
uv run -- bash scripts/run.sh
```

Windows 可用于界面开发；原生 Windows 的资源限制不宣称与 Linux 等价。

### Windows 日常一键打开（环境已安装）

1. 打开项目文件夹，双击根目录的 `Open-OJ.cmd`。
2. 脚本自动使用项目 `.venv`，后台启动 FastAPI 并提供构建后的前端；就绪后自动打开
   `http://127.0.0.1:8000`。日常启动无需 Node，也不会联网安装依赖。
3. 关闭浏览器不会停止服务；再次双击同一文件会复用服务并重新打开网页。
4. 不再使用时，双击 `Stop-OJ.cmd` 释放后台进程。请等提交评测/AI 命题结束后再停止，
   避免中断进行中的任务。已保存的账号、题库和数据不会删除。

可给 `Open-OJ.cmd` 创建桌面快捷方式；不要把脚本本身移出项目目录。
重启电脑后再次双击即可，无需开机自启动。修改后端代码或 `.env` 后，先停止再打开。
首次依赖安装仍需下面的命令；已有 `.env` 时不要重新复制模板覆盖密钥。

启动失败时窗口保留错误提示，日志在 `var/launcher/backend.log` 和 `frontend.log`。
重复双击有锁保护；脚本只关闭本项目启动且身份匹配的进程，不强杀占用端口的其他程序。
如果之前手动启动过服务，请先关闭原来的前后端，再使用一键入口。

可选命令行用法：

```powershell
.\scripts\run.ps1                      # 启动并打开网页
.\scripts\run.ps1 -Action status       # 查看状态
.\scripts\run.ps1 -Action stop         # 停止服务
.\scripts\run.ps1 -NoBrowser           # 仅启动，不打开浏览器
.\scripts\run.ps1 -Legacy              # 兼容 Streamlit，打开 8501
```

### Windows 首次安装

```powershell
winget install --id=astral-sh.uv -e
uv sync --frozen --extra dev --extra report
Copy-Item .env.example .env
# 先安装 Node.js 24 LTS；仅首次安装或更新前端后需要构建。
Push-Location web
npm ci
npm run build
Pop-Location
uv run -- powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

没有 `uv` 时仍可使用 `python -m venv .venv` 后执行
`pip install -r requirements-dev.txt`；正式验收与 CI 使用已提交的 `uv.lock`。

打开 <http://127.0.0.1:8000>。交互文档位于 <http://127.0.0.1:8000/docs>。
Linux 使用 `scripts/run.sh --legacy` 可启动兼容界面。

开发前端：先启动 `uv run uvicorn oj.main:app --host 127.0.0.1 --port 8000`，
再在 `web/` 执行 `npm run dev`，打开 `http://127.0.0.1:5173`；Vite 代理 `/api`。
新版使用浏览器 Session Cookie，旧版会话无需迁移。页面与 AI 验收记录见
[新版前端与 AI 工作流](docs/web-ai-experience.md)。

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
| `OJ_AI_DEFAULT_PROVIDER_URL` | 系统默认模型兼容 API 基地址（通常以 `/v1` 结尾） |
| `OJ_AI_DEFAULT_MODEL` | 系统默认模型名称 |
| `OJ_AI_DEFAULT_API_KEY` | 仅服务器持有的系统模型密钥 |
| `OJ_AI_DEFAULT_INPUT_PRICE` / `OJ_AI_DEFAULT_OUTPUT_PRICE` | 系统基础模型输入/输出 Token 单价，默认 0 |
| `OJ_AI_DEFAULT_PRICE_UNIT` | 单价对应 Token 数量，默认 1000000 |
| `OJ_AI_DEFAULT_CURRENCY` | `USD` 或 `CNY`，默认 USD；不隐式换汇 |
| `OJ_AI_DEFAULT_CACHED_INPUT_PRICE` | 缓存命中输入单价；省略时按普通输入价 |
| `OJ_AI_ROUTING_ENABLED` / `OJ_AI_QUALITY_MODEL` | 启用任务分流和高质量模型名称 |
| `OJ_AI_QUALITY_INPUT_PRICE` / `OJ_AI_QUALITY_OUTPUT_PRICE` / `OJ_AI_QUALITY_CACHED_INPUT_PRICE` | 高质量模型单价；共用系统币种、Token 单位及加密凭据 |
| `OJ_AI_MAX_OUTPUT_TOKENS` | 每次调用最大输出（含推理），默认 16384 |
| `OJ_AI_DEFAULT_REASONING_EFFORT` / `OJ_AI_QUALITY_REASONING_EFFORT` | 可选服务商参数 `high/max`，默认不发送；不影响个人配置 |
| `OJ_AI_DEFAULT_JSON_MODE` / `OJ_AI_QUALITY_JSON_MODE` | 是否发送 `response_format=json_object`，默认 true；关闭不影响后端严格 JSON/Schema 验证 |
| `OJ_ALLOW_PRIVATE_AI_ENDPOINTS` | 仅本地 mock 测试可设为 `true` |
| `OJ_API_URL` | Streamlit 访问后端的地址 |

### 新用户开箱即用的系统模型

在服务器未跟踪的 `.env` 中填写 `OJ_AI_DEFAULT_PROVIDER_URL`、
`OJ_AI_DEFAULT_MODEL`、`OJ_AI_DEFAULT_API_KEY`，并设置一个长期保持不变的强随机
`OJ_AI_ENCRYPTION_KEY`。四项都需要配置；不要把真实值填到 `.env.example`、代码、
Git、截图或前端环境变量里。默认公网 HTTPS 校验仍生效。

启动后端时，系统配置仅在数据库尚无默认模型时导入，并使用 Fernet 加密保存。
新注册用户登录后即可创建 AI 任务，不需要逐用户复制密钥。前端仅显示“系统模型已配置”，
不返回系统服务地址、模型名称、明文或加密后的密钥。任务可以展示用量、费用和配置来源。

配置优先级是 **个人配置 > 系统默认 > 未配置**。用户在命题中心可以保存自己的
模型配置；首次个人覆盖必须提供自己的 key，不能借用系统 key 发往个人指定地址。
移除个人配置后恢复系统默认。个人调用失败时不会暗中改用系统密钥重试或收费。

后续启动不会用 `.env` 覆盖已有系统配置；改动 `.env` 不代表已经完成密钥轮换。
调整非敏感模型/价格策略后，在项目根目录运行 `python scripts/configure_system_ai.py --apply`。
该命令显式同步 `.env` 的模型、分流和计价配置；数据库为空时先初始化默认配置。
已保存的服务地址与密钥必须匹配，否则拒绝同步，不执行密钥轮换或付费请求。
运行中任务沿用启动该任务时读取的配置快照；新任务读取新配置。
必须保留原加密主密钥和数据库的配套备份，错误或缺失主密钥会导致启动失败。
课程 reset 清除用户配置，但保留系统默认模型；不要用 reset 更新模型或轮换密钥。

旧版仅个人配置的本地环境可以继续使用运行目录 `.ai-key`。首次启用系统默认和稳定
主密钥时，会尝试用原 `.ai-key` 解密旧个人配置并重新加密；无法解密则报错，不覆盖旧值。
迁移后保留 `.ai-key` 以便恢复迁移前备份。已有环境主密钥不能随意更换。

系统默认调用费用由服务器配置的账户承担。单价默认 0 只是未设置计价，**不表示免费**；
请填写真实单价并在服务商侧设置预算。当前课程系统仍仅面向可信本地用户，面向公众开放
注册前还需要账号滥用防护、共享额度限制和生产级代码沙箱。

### 双模型分流与双币种计价

分流仅作用于系统配置，不覆盖用户自带模型，不新增付费分类请求，也不在失败后自动重试。
对已有题目执行 `revise + samples/statement` 使用独立局部协议：只返回样例或题面字段，
不重写测试点、参考解或错误算法。初稿可用 Flash，复审使用高质量模型；每阶段默认
8192 输出 Token（`OJ_AI_SECTION_MAX_OUTPUT_TOKENS`）。样例每条输入/输出最多 2000 字符。
局部建议不宣称整题通过质量门禁，需在任务页确认后载入编辑器并手动保存；旧版草稿发生
变更时阻止直接采纳，避免覆盖新内容。完整命题仍保留原来的参考解、卡错和独立对拍门禁。
入门题初稿、简单题面润色使用基础 Flash；复杂/难度不明的命题、算法修改、测试设计、
审核及第二阶段完整复审使用高质量模型。原题/草稿的 difficulty 和 tags 参与判断；
复杂信号优先于简单信号。规则是保守启发式，不保证理解任意自然语言中的难度。
本地参考解评测、错误解卡错、oracle 对拍仍由本地评测器完成，不交给模型判分。

按本次提供的截图，可使用以下服务器设置（不包含密钥）：

```dotenv
OJ_AI_DEFAULT_MODEL=glm-5.3-flash
OJ_AI_DEFAULT_CURRENCY=CNY
OJ_AI_DEFAULT_PRICE_UNIT=1000000
OJ_AI_DEFAULT_INPUT_PRICE=0.4
OJ_AI_DEFAULT_OUTPUT_PRICE=1.4
OJ_AI_DEFAULT_CACHED_INPUT_PRICE=0.115
OJ_AI_ROUTING_ENABLED=true
OJ_AI_QUALITY_MODEL=glm-5.3
OJ_AI_QUALITY_INPUT_PRICE=8
OJ_AI_QUALITY_OUTPUT_PRICE=28
OJ_AI_QUALITY_CACHED_INPUT_PRICE=2
OJ_AI_DEFAULT_REASONING_EFFORT=high
OJ_AI_QUALITY_REASONING_EFFORT=high
OJ_AI_DEFAULT_JSON_MODE=false
OJ_AI_QUALITY_JSON_MODE=false
```

Flash 是截图中的限时折扣价；原价为 0.8 / 2.8 / 0.23 元，截图未给出确切截止日期，
系统不会推测到期时间或自动切价。优惠结束需更新 `.env` 后显式同步。
截图中的缓存存储暂时免费；当前接口未提供存储时长，因此不另算存储费。

每个阶段保存独立单价、档位、路由理由、缓存命中量和费用快照；任务总价为各阶段费用之和。
输入总量包含缓存 Token，费用为 `(输入−缓存)×输入价 + 缓存×缓存价 + 输出×输出价`，
再除以计价单位。缓存量来自服务商 `usage.prompt_tokens_details.cached_tokens`
（[官方缓存说明](https://docs.bigmodel.cn/cn/guide/capabilities/cache)）；
未报告时不推测折扣。输出用量包含服务商计入的 reasoning tokens，断流时仅估算已观测内容。
费用是按配置计算的账单估算，仍以服务商实际账单为准。
个人配置可独立选择 USD/CNY；历史记录保持原币种，v5 迁移不改变旧 USD 金额。

GLM 推理也占输出预算。两档显式使用 `high` 增强推理，避免服务商默认的 `max`
深度推理给简单任务带来过长等待（[官方参数说明](https://docs.bigmodel.cn/cn/guide/start/concept-param)）。
需要更多推理时可将质量档改为 `max` 后同步；不向其他兼容服务商默认发送该专用参数。
当前本地 `.env` 已扩展为完整命题 65536 / 局部修改 16384 输出 Token（含推理），
单阶段 900 秒、全任务 2400 秒、流式读取等待 180 秒。读取超时控制无数据到达的等待，
阶段超时控制整次调用，二者不同；仍可能因服务商异常或不合格内容失败。
上限不是目标消耗。按当前 GLM-5.3 输出价，两次调用都耗尽 65536 Token 时，
仅输出费用约 CNY 3.67，另计输入；不要无界加大预算或连续重复提交。
首稿 JSON/Schema 错误及 Python 语法诊断会送入原定第二阶段修正，不增加第三次自动调用。
第二阶段依然必须严格校验通过；首稿错误不会被静默当成合法结果。
Token 达上限、超时或失败都保留已观测用量，不自动重试收费。
已完成的初稿在复审失败后保留，截断的原始输出可以下载，但不能直接发布。
失败/取消任务页提供“按原需求重新发起”，须明确确认新费用；新任务不覆盖历史失败记录。
可运行 `python scripts/check_ai_authoring.py --paid` 显式执行一次真实双阶段端到端检查：
使用临时数据库，不写入正式题库；会消耗服务器模型账户 Token，完成后清理测试数据。

本次实测当前 GLM-5.3 接口的 `json_object` 模式会删除字符串值中的 `json` 标识符，
使 `import json` / `json.dumps` 变为非法代码；相同输入不发送该参数则保留完整源码。
因此这套 GLM 配置关闭 JSON mode，仍要求模型返回 JSON，并继续严格解析、Schema 验证及
全部本地质量门禁；不通过修改生成代码来掩盖提供商问题，不自动追加付费请求。

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

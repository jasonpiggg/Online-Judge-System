# 课程要求逐项验收矩阵

审计日期：2026-09-10。依据为课程最新版
[Step 1–6 与 Advance](https://dbg-course.github.io/python-docs/oj/)、
[API 文档](https://dbg-course.github.io/python-docs/oj/api/)、
[FAQ](https://dbg-course.github.io/python-docs/oj/faq/)和
[评分标准](https://dbg-course.github.io/python-docs/oj/requirements/)。

状态说明：`PASS` 表示代码、自动测试或浏览器验收已有直接证据；`ENV` 表示实现和 Linux CI
覆盖，但 Windows 本地不能等价验证；本表不替代助教最终评分。

## 全局硬性要求

| 要求 | 状态 | 实现证据 | 验证证据 |
| --- | --- | --- | --- |
| 课程 API 全部使用 FastAPI `async def` | PASS | `src/oj/routers/`、`src/oj/main.py` | `test_every_course_api_endpoint_is_async` 反射检查全部 `/api/` route |
| 阻塞 I/O 不占用 event loop | PASS | JSON/bcrypt/DNS 使用 `asyncio.to_thread`；SQLite/子进程使用异步 API | Ruff `ASYNC`、单元测试、mypy |
| HTTP 状态码与 JSON `code` 相同 | PASS | `src/oj/errors.py` 统一 envelope/handler | API 全套测试逐项断言 |
| 参数错误统一 400，不泄漏 FastAPI 422 | PASS | `RequestValidationError` handler；扩展 verdict 参数也返回 400 | `test_extension_parameter_errors_follow_course_http_400_contract` |
| 异常优先级 401 > 403 > 400 > 429 > 409 > 404 > 500 | PASS | `AuthorizedRoute` 在 body 解析前执行认证/管理员依赖 | `test_authentication_precedes_malformed_json`、`test_api_edges.py` |
| 敏感数据不进入普通响应/错误/日志 | PASS | 密码哈希、AI key 加密、错误清洗 | auth、AI config、judge diagnostics tests |

## Step 1：题目管理（5 分）

| 具体得分点 | 状态 | 实现与边界 | 主要证据 |
| --- | --- | --- | --- |
| `GET /api/problems/` 返回题目简要列表 | PASS | 登录依赖；默认仅 ID/title，扩展 metadata 显式开启 | `routers/problems.py`、`test_problems.py` |
| `GET /api/problems/{id}` 返回完整字段及类型默认值 | PASS | 省略限制按 3 s / 128 MB 返回；字符串/list 默认值完整 | `schemas.py`、`problem_store.py`、`test_core_edges.py` |
| `POST /api/problems/` 新增 | PASS | 全字段 Pydantic 校验、重复 ID 409、未登录 401 | `test_problems.py`、`test_api_edges.py` |
| `PUT /api/problems/{id}` 编辑 | PASS | 路径/请求 ID 不一致 400；全量重新校验；不存在 404 | `test_problems.py` |
| `DELETE /api/problems/{id}` 删除 | PASS | 仅管理员；文件、发布资产和历史标记一致更新 | `test_problem_drafts.py`、`test_published_assets.py` |
| 每题一个 JSON，启动加载并校验 | PASS | seed 复制后校验目录全部 JSON；损坏文件启动失败 | `problem_store.py`、`test_core_edges.py` |
| 文件写入安全 | PASS | 安全题号、同目录临时文件、flush/fsync、原子替换、锁 | `test_core_edges.py` |

结论：Step 1 的 3 分列表/详情和 2 分增删改均有直接证据。

## Step 2：评测控制（5 分）

| 具体得分点 | 状态 | 实现与边界 | 主要证据 |
| --- | --- | --- | --- |
| Python 自动评测 | PASS | 输入经 stdin，stdout 与标准答案比对 | `judge.py`、`test_judge_languages.py` |
| C++14 编译与运行 | PASS | `g++ -O2 -std=c++14`，编译信息独立保存 | `test_linux_judge.py`、`test_judge_regressions.py` |
| 异步提交与后台评测 | PASS | 先写 pending，再 `asyncio.create_task` | `submissions.py`、`test_submissions.py` |
| AC/WA/TLE/MLE/RE/CE/UNK | PASS/ENV | 全部分类已实现；Linux 完整矩阵由 CI 验证 | `test_linux_judge.py`、`test_core_edges.py` |
| pending/success/error 三态 | PASS | success 表示评测正常完成，不等于 AC；基础设施异常才 error | `test_submissions.py` |
| 题目→语言→系统限制继承 | PASS | time/memory 按题目、语言、3 s/128 MB 顺序确定 | `test_judge_regressions.py` |
| 时间限制 | PASS/ENV | `asyncio.wait_for` 超时后终止进程组 | Linux CI `test_linux_judge.py` |
| 内存限制与监控 | PASS/ENV | Linux `RLIMIT_AS` + 进程树 RSS；返回 MLE | Linux CI `test_linux_judge.py` |
| 多进程与输出资源边界 | PASS | 32 进程上限、stdout/stderr 各 1 MB、文件大小限制 | `test_judge_regressions.py` |
| `POST /api/languages/` 动态注册 | PASS | 登录依赖；shell-free argv、executable/placeholder allowlist | `languages.py`、`test_core_edges.py` |
| `GET /api/languages/` 查询列表 | PASS | 返回课程要求 `{"name": [...]}` | `test_judge_languages.py` |
| 逐测试点 10 分及结果持久化 | PASS | counts = testcase × 10；日志保存耗时/内存 | `submissions.py`、`test_submissions.py` |

结论：多语言 2 分、动态语言 1 分、语言列表 1 分、资源限制 1 分均覆盖。完整资源限制验收必须在
Ubuntu/WSL2 执行，Windows 本地结果不能替代 Linux。

## Step 3：评测管理（5 分）

| 具体得分点 | 状态 | 实现与边界 | 主要证据 |
| --- | --- | --- | --- |
| `GET /api/submissions/` | PASS | user/problem 一级条件；status/page/page_size 二级条件 | `routers/submissions.py`、`test_submissions.py` |
| 一级条件不可全空 | PASS | 管理员显式扩展 `all_users=true` 除外 | `test_api_edges.py` |
| 分页组合语义 | PASS | 两者空=全部；仅 page_size=第一页；仅 page=400 | `test_api_edges.py`、`test_experiment_compliance.py` |
| 普通用户/管理员范围 | PASS | 普通用户强制本人；管理员可按题目查看所有用户 | `test_submissions.py` |
| 列表只返回摘要 | PASS | pending/error 仅 ID/status；success 加 score/counts | `submissions.py` |
| `GET /api/submissions/{id}` | PASS | 本人或管理员；返回 status/score/counts/compile/run/error | `test_submissions.py` |
| `PUT .../rejudge` | PASS | 仅管理员；覆盖原 ID，立即 pending，删除旧 cases | `test_submissions.py`、`test_logs_reset.py` |
| 提交频率限制 | PASS | 每用户每题每分钟 3 次；锁内原子检查/创建 | `test_api_edges.py` 并发用例 |
| pending 重启恢复与取消清理 | PASS | lifespan 恢复；shutdown/reset 等待或取消 Task | `test_task_deadline_account.py`、`test_logs_reset.py` |

结论：列表 2 分、详情 2 分、重测 1 分均覆盖。

## Step 4：用户管理（5 分）

| 具体得分点 | 状态 | 实现与边界 | 主要证据 |
| --- | --- | --- | --- |
| 初始管理员 | PASS | 启动幂等创建 `admin / admintestpassword` | `main_support.py`、fixtures |
| `POST /api/users/` 注册 | PASS | 用户名 3–40、密码至少 6、唯一性、bcrypt | `test_auth_users.py` |
| `POST /api/auth/login` | PASS | 错误凭据 401、banned 403、成功轮换 Session | `test_auth_users.py`、`test_api_edges.py` |
| `POST /api/auth/logout` | PASS | 删除服务端 Session 与 Cookie | `test_auth_users.py` |
| Session 安全 | PASS | 高熵 token、服务端存储、过期、HttpOnly/SameSite/Secure 配置 | `auth.py`、`test_auth_users.py` |
| `GET /api/users/{id}` | PASS | 本人或管理员；不返回 password/hash | `test_auth_users.py` |
| `PUT /api/users/{id}/role` | PASS | 仅管理员；严格 role；banned 立即阻止访问 | `test_auth_users.py`、`test_role_audit.py` |
| 权限变更审计 | PASS | actor/target/old/new/time 与更新同事务 | `test_role_audit.py` |
| `GET /api/users/` | PASS | 仅管理员；分页；扩展用户名筛选 | `test_auth_users.py` |
| submit/resolve 统计 | PASS | 提交按次数，通过按 problem 去重 | `test_auth_users.py` |
| Step 1–3 登录/角色补充 | PASS | 题目/语言/提交全部登录；删题/重测仅管理员 | 权限矩阵测试 |

结论：注册 2 分、信息 1 分、权限 1 分、列表 1 分均覆盖。

## Step 5：评测日志（5 分）

| 具体得分点 | 状态 | 实现与边界 | 主要证据 |
| --- | --- | --- | --- |
| `GET .../{id}/log` 与 submission 关联 | PASS | score/counts；允许时返回 case id/result/time/memory | `test_logs_reset.py` |
| 私有日志：本人 | PASS | 本人可见总分，不泄露 details | `test_logs_reset.py` |
| 私有日志：其他普通用户 | PASS | 返回 403，仍记录拒绝审计 | `test_api_edges.py` |
| 管理员日志 | PASS | 所有提交均可查看完整 details | `test_logs_reset.py` |
| 公开日志 | PASS | `public_cases=true` 后所有已登录用户可见 details | `test_api_edges.py` |
| `PUT .../log_visibility` | PASS | 仅管理员；普通完整题目更新也不能绕过 | `test_ai_draft_review.py` |
| 访问审计 | PASS | 仅存在资源且已认证时记 `view_logs` 和 200/403 | `test_role_audit.py`、`test_api_edges.py` |
| `GET /api/logs/access/` | PASS | 管理员、用户/题目筛选、课程分页语义 | `test_api_edges.py` |
| 内容裁剪一致 | PASS | 公开日志不开放他人 submission/source；AI/metadata 同一策略 | `test_visual_quality.py`、浏览器测试 |

结论：记录查询 2 分、权限 2 分、审计 1 分均覆盖。

## Step 6：Streamlit 前端（5 分）

`frontend/` 是默认入口；`web/` 的 React 版本是可选增强。两者均只通过 REST API 访问业务。

| 页面/交互 | 状态 | 实现与验收 |
| --- | --- | --- |
| 注册、登录、退出 | PASS | 账户页、友好错误、Cookie bridge；Streamlit/React Playwright |
| 用户信息 | PASS | 个人资料、提交/通过统计、密码修改 |
| 管理员用户管理 | PASS | 列表、筛选、角色修改、角色审计；普通用户不可见且后端 403 |
| 题目列表与详情 | PASS | 搜索、难度/状态筛选、Markdown/KaTeX 题面 |
| 题目新增/编辑/删除 | PASS | 完整表单、草稿、字段校验、管理员删除二次确认 |
| 代码提交 | PASS | 题号/语言/Monaco、文件导入、草稿、REST 提交 |
| 提交列表与详情 | PASS | 状态、得分、编译、运行、错误与允许的测试点 |
| 评测状态刷新 | PASS | pending 轮询或手动刷新，终态停止 |
| 会话传递 | PASS | HttpOnly Session；不硬编码用户身份 |
| 响应/异常处理 | PASS | 统一客户端处理 HTTP 和 envelope；错误给出修复建议 |
| 响应式与可访问性 | PASS | 1440/1024/390/320、无横向溢出、keyboard focus、语义标签 |
| AI 透明度与危险操作 | PASS | AI 人工复核提示；删除/reset/覆盖操作有确认 |

设计复核结论（`frontend-design` + `frontend-design-review`）：核心任务入口明确，课程工作台采用
克制的浅色工具界面和共享 token；桌面/移动布局、焦点状态、错误可操作性和 AI 透明度达到本项目
既有设计基线。本轮没有扩大视觉改版范围，只验证现有方向与课程页面覆盖。

## Advance：AI 智能命题（10 分）

| 得分点 | 状态 | 实现与证据 |
| --- | --- | --- |
| R1 出题交互界面（1） | PASS | 命题需求、状态、结果、版本草稿、编辑/验证/发布闭环；浏览器测试 |
| R2 provider/model/key（1） | PASS | 个人/系统配置真实用于请求；Fernet；GET/错误/日志不回显 key |
| R3 实时进度与中断（1） | PASS | SSE/轮询显示持久化阶段；取消 Task、HTTP 流和本地 runner；终态 409 |
| R4 Token/费用（1） | PASS | input/output/cached/total、币种、阶段价格快照、provider/估算标识 |
| 题目合理性（2） | PASS（系统能力） | 需求+难度约束、二阶段复审、题面检查、参考解实跑；真实质量仍依模型和教师复核 |
| 测试用例有效性（2） | PASS（系统能力） | 样例/边界/规模、独立 oracle 对拍、错误解杀伤、mutation score |
| 功能易用性（2） | PASS | 草稿恢复、局部修改、失败诊断、显式发布、费用确认、可取消/重发 |

付费外部模型不属于无授权回归。本轮使用本地 HTTP/SSE mock 验证协议、任务、取消、用量、价格和
质量门禁；报告不会把 mock 结果描述成某个真实模型的质量证明。

## 代码规范、报告与扣分项

| 检查 | 状态 | 结论 |
| --- | --- | --- |
| 清晰架构 | PASS | AI 子系统归入 `src/oj/ai/`；依赖方向见 `docs/architecture.md` |
| 注释和可读性 | PASS | 核心模块、任务所有权、异步/安全边界增加 docstring 与 why-comment |
| Ruff / mypy | PASS | Ruff 规则含 ASYNC/Security；mypy strict |
| 测试和覆盖率 | PASS | 357 passed / 10 Windows skipped；行/分支超过 90%/85% 门槛 |
| Python/Node 依赖漏洞 | PASS | pip-audit 与 npm runtime audit 均为 0 |
| Git 大文件 | PASS | 最大跟踪业务资产约 1.2 MiB；venv/dist/db/log/coverage 均忽略 |
| Conventional Commits / PR | PASS | 功能分支、英文 Conventional Commit、PR、自动 review、CI、普通 merge |
| 实验报告 | PASS | `docs/experiment-report.md` 从当前代码重写；含架构、难点、成果、AI 说明和改进 |
| 最终 PDF 路径 | PASS | `output/pdf/atelier-oj-experiment-report.pdf` |

## 最终验收命令

```powershell
.\.venv\Scripts\ruff.exe check src frontend tests scripts
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\pytest.exe --cov=oj --cov-branch --cov-report=json:coverage.json
.\.venv\Scripts\python.exe scripts\check_coverage.py coverage.json
.\.venv\Scripts\pip-audit.exe --local --skip-editable

Push-Location web
npm run lint
npm run typecheck
npm test -- --run
npm run build
npx playwright test
npx playwright test --config playwright.streamlit.config.ts
Pop-Location
```

# 实验二评分点核对表

本表按课程实验二的 40 分功能、5 分工程规范、5 分实验报告逐项映射。它记录实现与证据，不替代助教评分。

下表保留当时的实验验收记录。React 新版管理员入口的最新核对见
[管理员网页覆盖表](admin-web-coverage.md)；后续真实模型验收见
[视觉与 AI 质量记录](visual-quality-upgrade.md)，不再以本表历史“未验收”状态为最新结论。

| 评分项 | 分值 | 已实现内容 | 主要代码 | 自动/人工证据 |
| --- | ---: | --- | --- | --- |
| Step 1 题目管理 | 5 | 独立 JSON、完整字段与默认值、CRUD、路径 ID 一致性、重复/不存在、登录与管理员删除、原子写和安全题号 | `problem_store.py`、`routers/problems.py` | `test_problems.py`、`test_core_edges.py`；浏览器题库/编辑/删除确认 |
| Step 2 评测控制 | 5 | Python/C++14、动态语言、安全 argv 模板、逐测试点 AC/WA/TLE/MLE/RE/CE/UNK、输出规范化、计时/内存/诊断 | `judge.py`、`languages.py` | Linux `test_linux_judge.py`、`test_judge_regressions.py`；完整 verdict 矩阵 |
| Step 3 提交管理 | 5 | pending 异步入队、重启恢复、详情/一级二级筛选/分页、每分钟 3 次并发安全限频、管理员重测 | `submissions.py`、`routers/submissions.py` | `test_submissions.py`、`test_api_edges.py`；浏览器普通提交/管理员全站记录与重测 |
| Step 4 用户管理 | 5 | 注册/登录/退出、管理员创建、本人资料、角色、禁用、列表分页、bcrypt、服务端 Session 与统计 | `auth.py`、`security.py`、`routers/users.py` | `test_auth_users.py`、`test_role_audit.py`；浏览器注册、角色导航与角色修改 |
| Step 5 日志与审计 | 5 | 本人/管理员日志、公开测试点日志、403/200 访问审计、用户/题目筛选与分页、独立角色变更审计 | `routers/logs.py`、`database.py` | `test_logs_reset.py`、`test_api_edges.py`；浏览器公开开关与审计页 |
| Step 6 Web UI | 5 | 账户、个人进度题库、同屏做题、服务端源码草稿、历史恢复、分区编辑器、提交详情、管理中心 | `frontend/` | `test_frontend.py`、`test_frontend_workflows.py`、`test_frontend_release.py`；1440/1024/390 真实浏览器 |
| Advance R1–R4 | 4 | 可读命题工作台、自定义兼容模型/密钥/单价、流式阶段状态、真实取消、Token 与费用 | `ai_authoring.py`、`ai_transport.py`、`frontend/ai.py` | `test_ai.py`、`test_ai_edges.py`；本地 HTTP/SSE mock 浏览器生成与取消 |
| AI 质量与易用性 | 6 | 二次批判、独立 oracle 与受限生成器对拍、mutation score、版本草稿、发布门禁、编辑器局部入口 | `ai_authoring.py`、`routers/authoring.py`、`frontend/ai.py`、`frontend/editor.py` | mock 自动测试验证执行链；真实外部供应商仍未验收 |
| 工程规范 | 5 | async 路由、统一 envelope/400 校验、权限优先级、模块化、类型/风格/测试、锁文件、CI、Dependabot、真实分支/PR | 全仓库、`.github/`、`uv.lock` | Ruff、mypy、pytest、pip-audit；PR #9–#13 与 release PR |
| 实验报告 | 5 | 架构、关键实现、权限/安全边界、AI 工作流与用量、测试结果、真实截图、局限和改进 | `docs/experiment-report.md`、`output/pdf/` | Markdown/PDF 同源生成；Poppler 逐页渲染及文本/页数校验 |

## 课程接口覆盖

- 题目：`GET/POST /api/problems/`，`GET/PUT/DELETE /api/problems/{problem_id}`，`PUT /api/problems/{problem_id}/log_visibility`。
- 提交和语言：`POST/GET /api/submissions/`，`GET /api/submissions/{submission_id}`，`PUT .../rejudge`，`GET .../log`，`POST/GET /api/languages/`。
- 用户：`POST /api/auth/login`、`POST /api/auth/logout`、`POST /api/users/`、`POST /api/users/admin`、`GET /api/users/{user_id}`、`PUT .../role`、`GET /api/users/`。
- 审计/reset：`GET /api/logs/access/`、`POST /api/reset/`。
- AI：模型配置、任务创建/历史/详情/取消、命题草稿 CRUD/版本/发布，以及按用户和语言隔离的做题草稿 API。

## 明确边界

- Linux/WSL2 才是完整 runner 环境；Windows 原生浏览器验收不用于证明 `rlimit` 等价。
- subprocess 防护是课程级隔离，不是生产沙箱；公网部署需要容器/VM、cgroup、seccomp 和网络隔离。
- 本地 HTTP/SSE mock 证明协议、流程、用量与校验，不证明任意真实模型的出题质量。

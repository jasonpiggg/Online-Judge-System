# 本轮任务交付说明

> 基线：2026-09-10 的 `main` 最新代码
> 审计范围：课程 OJ 文档总览、Step 1–Step 6、进阶模块、API 约定、FAQ，以及仓库内后端、Streamlit、React、测试、文档和 Git 配置。

## 1. 本轮完成内容

本轮工作不是只按评分表标题抽样检查，而是把课程文档中的字段、状态、权限、错误码、异步要求和 AI R1–R4 要求逐项映射到实现与自动化测试。最终产物包括：

- 一份可追踪到实现和测试证据的严格合规审计；
- 一次只调整组织结构、不改变产品边界的后端架构整理；
- 一处课程 API 错误码契约修复；
- 两组防回归合规测试，以及两处更稳定的浏览器测试定位；
- 从当前代码重新撰写的实验报告 Markdown 和重新生成、逐页检查的 PDF；
- 完整的 Python、TypeScript、组件、构建、安全与浏览器端验证。

## 2. 课程要求检查结论

详细逐项证据见 [`requirements-audit.md`](requirements-audit.md)。结论摘要如下：

| 模块 | 核心核验项 | 结论 |
| --- | --- | --- |
| 全局约定 | FastAPI 路由均为 async、统一响应、HTTP/业务码一致、错误优先级 | 符合；新增全路由 async 守卫测试 |
| Step 1 题目管理 | YAML/JSON 字段、默认值与校验、导入导出、管理员 CRUD | 符合 |
| Step 2 评测控制 | Python/C++14、语言注册、进程隔离、超时/内存限制、完整 verdict | 符合 |
| Step 3 评测管理 | 提交、分页查询、详情、状态转换、管理员重评测 | 符合 |
| Step 4 用户管理 | 注册、登录、bcrypt、session、用户/管理员权限 | 符合 |
| Step 5 评测日志 | 测试点明细、owner/admin/public 可见性、管理员访问审计 | 符合 |
| Step 6 前端交互 | Streamlit 页面、REST API 对接、用户/题目/提交/管理闭环 | 符合 |
| 进阶 AI | R1 入口、R2 配置、R3 流式进度和取消、R4 usage/cost | 符合 |
| AI 质量 | 结构化生成、测试覆盖、参考解和错误解验证、人工复核发布 | 符合 |

审计发现的实际偏差是提交列表扩展参数 `verdict` 非法时由框架默认返回 422，而课程 API 约定要求参数错误返回 400。本轮已改为显式校验并补充回归测试。404/409/429/500、认证与授权错误的既有实现也已按课程约定复核。

## 3. 代码与架构调整

### 3.1 AI 子系统归档

原来散落在 `src/oj/` 根目录的七个 `ai_*` 模块移动到 `src/oj/ai/` 包：

- `authoring.py`：命题任务、生成、验证与持久化编排；
- `experience.py`：SSE、任务历史、取消和交互状态；
- `policy.py`：权限、额度和模型策略；
- `presentation.py`：面向界面的状态与结果表达；
- `prompts.py`：Prompt 构造；
- `sections.py`：局部生成/审查的 section 规则；
- `transport.py`：模型传输与 provider 适配。

同步更新了运行代码、运维脚本、测试导入和 monkeypatch 目标。该重构只改变文件组织和 import path，没有修改 API path、数据库 schema 或前端协议。

### 3.2 可读性改进

为核心边界补充了 module docstring 和少量解释“为什么”的注释，覆盖：认证/session、数据库事务、错误响应、判题隔离、语言注册、应用生命周期、题目存储、提交状态、AI 任务生命周期以及各 router 的职责。注释集中在安全边界、并发约束、状态不变量和兼容逻辑，没有逐行复述代码。

新增 [`architecture.md`](architecture.md)，明确后端分层、两套前端的职责、关键数据流、状态所有权和扩展位置，降低后续继续开发时把路由、领域逻辑和存储逻辑混在一起的风险。

## 4. 自动化测试增强

新增两项直接针对课程契约的测试：

1. 枚举 FastAPI 最终注册的所有课程 API route，断言 endpoint 全部为 coroutine function；这会阻止后续误加同步接口。
2. 对非法 `verdict`、`language`、`page` 等扩展查询参数验证 HTTP 400 与业务码 400 一致。

浏览器测试还修正了两类脆弱定位：

- React 导航改用精确的 link role，避免同名标题与导航项导致 strict locator 歧义；
- Streamlit 移动端标签筛选等待折叠面板动画完成，并使用稳定、可见的测试标签，避免点击仍被裁剪的 combobox。

这些改动改善的是测试确定性，没有通过降低断言、跳过用例或扩大 timeout 来掩盖产品故障。

## 5. 实验报告重写

[`experiment-report.md`](experiment-report.md) 已基于当前代码从头重写，包含：

- 系统架构、模块划分和技术选型；
- Step 1–Step 6 的关键实现；
- AI R1–R4、题目合理性与测试用例有效性；
- 关键难点、边界处理和安全设计；
- 自动化测试、覆盖率和界面成果；
- Git/代码规范、AI 工具链和 Vibe Coding 说明；
- 总结、限制和改进建议。

报告预留了姓名、学号、班级等人工信息位置，也保留了截图替换说明。最终 PDF 固定输出到：

`output/pdf/atelier-oj-experiment-report.pdf`

PDF 已重新构建为 16 页 A4，并对封面、目录/架构页、功能页、验证页及整份 contact sheet 做了视觉检查，未发现文字裁切、重叠、空白异常或页脚日期错误。

## 6. 前端设计复核

按项目约定同时采用 `frontend-design` 与 `frontend-design-review` 的检查维度，对现有 React 和 Streamlit 界面做了范围内复核：

- insight-to-action：导航、筛选、编辑、提交、结果和 AI 任务形成完整路径；
- quality craft：桌面与移动端布局、长标题/代码、空状态和错误状态均有回归覆盖；
- trustworthy building：权限受限日志有可操作提示，AI 流式阶段、取消、usage/cost 和发布前验证均透明；
- accessibility/consistency：关键操作使用语义 role、键盘路径与焦点行为由 E2E 覆盖。

本轮没有扩大为视觉改版，仅修正测试与文档证据。

## 7. 验证结果

| 检查 | 结果 |
| --- | --- |
| `pytest` | 357 passed，10 skipped |
| Python coverage | line 95.61%，branch 88.66% |
| Ruff | 通过 |
| mypy | 通过 |
| Vitest（React） | 75 passed |
| Playwright（React） | 52 passed |
| Playwright（Streamlit） | 44 passed |
| ESLint | 通过 |
| TypeScript typecheck | 通过 |
| React / Streamlit production build | 通过 |
| `pip-audit` | 未发现漏洞 |
| `npm audit --omit=dev` | 未发现 runtime 漏洞 |
| `git diff --check` | 通过 |
| tracked file size audit | 最大约 1.2 MiB，无异常大文件 |

浏览器测试期间 Windows asyncio 在客户端主动断开连接时偶发输出 `ConnectionResetError` 日志，但测试进程最终 44/44 通过，未形成失败、数据残留或服务不可用。

## 8. 安全、性能和边界说明

- 判题仍属于本机开发隔离模型：进程组终止、时间/内存限制和最小环境变量可降低风险，但不等同于容器/虚拟机级强隔离；公网部署前应增加容器、只读文件系统、网络禁用和独立 worker。
- API key 继续加密保存并脱敏返回；本轮没有读取、打印或提交真实 secret、数据库、日志和临时 trace。
- AI 真实 provider 的费用型 smoke test 未在本轮重新发起；可靠性由 mock provider、SSE、取消、usage/cost 与发布链路测试覆盖，避免未经授权产生外部费用。
- 测试跳过项仅是显式 opt-in 的真实 provider/真实工具链验证，不影响默认课程验收路径。

## 9. 交付文件索引

- [`requirements-audit.md`](requirements-audit.md)：课程要求逐项严格审计；
- [`architecture.md`](architecture.md)：当前项目架构与模块边界；
- [`experiment-report.md`](experiment-report.md)：可继续微调的完整实验报告源文件；
- [`scoring-checklist.md`](scoring-checklist.md)：答辩/验收速查清单；
- `output/pdf/atelier-oj-experiment-report.pdf`：重新生成的最终 PDF；
- 本文件：本轮操作、结果和风险的完整交付记录。

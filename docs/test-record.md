# Atelier OJ v1.1.0 测试记录

记录日期：2026-09-04。以下数字来自实际命令输出，未把跳过项或 mock 结果改写成真实供应商结果。

## 自动测试

| 环境 | 结果 | 说明 |
| --- | --- | --- |
| Windows `.venv` | 88 passed，10 skipped | 10 项均标记为 Linux judge integration；Ruff 与 mypy 通过 |
| WSL2 Ubuntu / Python 3.12.3 | 98 passed，0 skipped | 实际调用系统 `g++`，执行完整 runner 与 API 测试 |
| 后端覆盖率 | 行 97.67%，分支 93.07% | 门槛分别为 90% / 85%，由 `scripts/check_coverage.py` 独立读取 coverage JSON |
| 依赖审计 | 0 known vulnerabilities | `pip-audit --local --skip-editable`；CI 同样执行 |

WSL 实际 verdict：

- Python：AC、WA、RE、TLE、MLE、UNK。
- C++14：AC、WA、CE、RE、TLE、MLE。
- 额外边界：stdout/stderr 洪泛、编译洪泛/超时、进程组回收、取消、三级限制继承、代码/输入/输出空白保真。

## API 与数据

- 统一 envelope、422→400、鉴权/业务错误优先级、Session 轮换/过期/退出/禁用。
- 题目 CRUD、原子写失败、路径安全、日志公开权限不可由普通 PUT 绕过。
- 提交组合筛选、分页、私有摘要、并发 6 次提交恰好 3 次成功/3 次 429、重测覆盖原记录、reset 取消后台任务。
- 私有/公开/本人/他人/管理员日志矩阵；200/403 访问审计与独立角色修改审计。
- 版本迁移备份、幂等升级、旧用户/提交保留；AI 密钥不回显且 `.ai-key` 可跨重启解密。
- AI 使用真正本地 HTTP/SSE 服务覆盖两阶段请求、取消、超时、坏 JSON、usage/估算/累计费用、参考解和错误解失败。

## Streamlit 与真实浏览器

| 视口 | 页面 | 实测结果 |
| --- | --- | --- |
| 1440×900 | 管理员题库/桌面工作区 | `scrollWidth=1440`；侧栏 256px、正文 16px；题库 3 道种子题、双栏清晰 |
| 1024×768 | 提交记录/管理中心/AI/编辑器 | `scrollWidth=1024`；全站筛选、角色、日志公开、重测、AI 新增/更新可操作 |
| 390×844 | 题库/手机工作区 | `scrollWidth=390`；侧栏默认收起，H1 26px，“题目/代码/结果”切换和草稿保持正常 |

真实流程：

1. 普通用户注册并登录；管理员入口不可见。
2. 从题库直接进入 `sum_2`，填写 Python 草稿并提交；Windows 本机 runner 的结果为“评测完成 · 未全部通过”，界面没有把 `success` 错标成 AC。
3. 查看仅本人提交，切换记录后回到工作区，Ace 草稿仍在。
4. 管理员查看全站记录并重测，修改普通用户角色，公开测试点日志。
5. 删除与 reset 均显示题号/`RESET` 二次输入门槛；在浏览器中取消后无副作用。真正删除/reset 由自动 API 测试执行。
6. 本地 mock 完成双阶段 AI 任务：240 input、720 output Token，按测试单价累计 $1.680000；另一个任务在 UI 中真实取消并保留 329/59 Token、$0.447000 已观察费用。
7. 通过人工审阅勾选后，新建 `ai_verified_sum`；再次选择“更新已有题目”，进入禁用题号且需二次确认的标准编辑器并保存。

浏览器和启动验收发现并修复：直接 Streamlit 启动缺仓库 `PYTHONPATH`；Windows Git 将 WSL shell 脚本转成 CRLF；同一浏览器切换账号时旧账号工作区/AI/编辑器瞬态状态可见。新增回归测试确保换账号清除、同账号 Session 过期重登仍保留草稿；修复后 WSL `scripts/run.sh` 的 API `/docs` 和 Streamlit health 均为 200，退出后端口正常释放。

## 未宣称通过的项目

- 未配置真实外部模型供应商密钥，因此真实供应商输出质量未验收。
- Windows runner 只用于 UI 状态流，不用于证明 Linux 地址空间和进程组限制。
- 没有将课程级 subprocess runner 宣称为可直接公网部署的生产沙箱。

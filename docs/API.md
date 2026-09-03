# API reference

所有 JSON 响应均为 `{"code": HTTP状态码, "msg": "...", "data": ...}`，Cookie
保存服务端 Session ID。除注册、登录、语言列表和健康检查外，业务接口均要求登录。

## 用户与会话

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/users/` | 公开 | 注册普通用户 |
| POST | `/api/users/admin` | 管理员 | 创建管理员 |
| POST | `/api/auth/login` | 公开 | 登录并设置 Session Cookie |
| POST | `/api/auth/logout` | 登录 | 立即销毁 Session |
| GET | `/api/users/{user_id}` | 本人/管理员 | 用户信息与统计 |
| PUT | `/api/users/{user_id}/role` | 管理员 | 设置 `user/admin/banned` |
| GET | `/api/users/` | 管理员 | 分页用户列表 |

## 题目与语言

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| GET/POST | `/api/problems/` | 登录 | 列表/新增 |
| GET/PUT | `/api/problems/{problem_id}` | 登录 | 详情/完整更新 |
| DELETE | `/api/problems/{problem_id}` | 管理员 | 删除题目 |
| PUT | `/api/problems/{problem_id}/log_visibility` | 管理员 | 设置测例日志公开性 |
| GET | `/api/languages/` | 公开 | 查询语言 |
| POST | `/api/languages/` | 登录 | 注册受限命令模板 |

## 提交与日志

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/submissions/` | 登录 | 异步提交，每分钟最多三次 |
| GET | `/api/submissions/` | 本人/管理员 | 按用户、题目、状态筛选和分页 |
| GET | `/api/submissions/{id}` | 本人/管理员 | 总体评测结果 |
| PUT | `/api/submissions/{id}/rejudge` | 管理员 | 覆盖并重新评测 |
| GET | `/api/submissions/{id}/log` | 本人/管理员/公开题目 | 测试点明细 |
| GET | `/api/logs/access/` | 管理员 | 日志访问审计 |
| POST | `/api/reset/` | 管理员 | 恢复确定的测试初始状态 |

提交列表至少提供 `user_id` 或 `problem_id`。若提供 `page`，必须同时提供
`page_size`；只有 `page_size` 时默认第一页；两者均省略时返回全部结果。

## AI 智能命题

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| PUT | `/api/ai/model-config` | 登录 | 保存加密的兼容模型配置与价格 |
| POST | `/api/ai/problem-tasks/` | 登录 | 创建流式命题任务 |
| GET | `/api/ai/problem-tasks/{id}` | 创建者/管理员 | 查询进度、结果、Token 与费用 |
| PUT | `/api/ai/problem-tasks/{id}/cancel` | 创建者/管理员 | 实际中断后台任务 |

提供商需兼容 `POST {provider_url}/chat/completions` 的 OpenAI 流式协议。生产环境仅
允许 HTTPS 和公网地址；本地 mock 测试可显式设置 `OJ_ALLOW_PRIVATE_AI_ENDPOINTS=true`。


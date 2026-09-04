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
| GET/POST | `/api/problems/` | 登录 | 列表/新增；列表可附带本人练习进度 |
| GET/PUT | `/api/problems/{problem_id}` | 登录 | 详情/完整更新 |
| DELETE | `/api/problems/{problem_id}` | 管理员 | 删除题目 |
| PUT | `/api/problems/{problem_id}/log_visibility` | 管理员 | 设置测例日志公开性 |
| GET | `/api/languages/` | 公开 | 查询语言 |
| POST | `/api/languages/` | 登录 | 注册受限命令模板 |

## 提交与日志

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/submissions/` | 登录 | 异步提交，每分钟最多三次 |
| GET | `/api/submissions/` | 本人/管理员 | 按用户、题目、状态、是否全过筛选和分页 |
| GET | `/api/submissions/{id}` | 本人/管理员 | 总体评测结果 |
| PUT | `/api/submissions/{id}/rejudge` | 管理员 | 覆盖并重新评测 |
| GET | `/api/submissions/{id}/log` | 本人/管理员/公开题目 | 测试点明细 |
| GET | `/api/logs/access/` | 管理员 | 日志访问审计 |
| GET | `/api/logs/roles/` | 管理员 | 角色变更审计，支持 `page/page_size`，每页最多 100 条 |
| POST | `/api/reset/` | 管理员 | 恢复确定的测试初始状态 |

提交列表至少提供 `user_id` 或 `problem_id`。若提供 `page`，必须同时提供
`page_size`；只有 `page_size` 时默认第一页；两者均省略时返回全部结果。

管理员可用 `all_users=true` 查询全站提交；`include_metadata=true` 的列表/详情增加 `username`，
列表仍不返回源码。管理员用户列表支持 `q` 按用户名子串（字面匹配）或精确用户 ID 搜索。
新版网页对应入口与权限核对见 [管理员网页覆盖表](admin-web-coverage.md)。

## AI 智能命题

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/ai/model-config` | 登录 | 有效配置来源与状态；只返回本人配置的可编辑元数据 |
| PUT | `/api/ai/model-config` | 登录 | 保存加密的兼容模型配置与价格 |
| DELETE | `/api/ai/model-config` | 登录 | 仅移除本人覆盖，回退系统默认；幂等 |
| POST | `/api/ai/problem-tasks/` | 登录 | 创建流式命题任务 |
| GET | `/api/ai/problem-tasks/` | 登录 | 最近 50 个本人任务、状态与费用 |
| GET | `/api/ai/problem-tasks/{id}` | 创建者/管理员 | 查询进度、结果、Token 与费用 |
| PUT | `/api/ai/problem-tasks/{id}/cancel` | 创建者/管理员 | 实际中断后台任务 |
| GET/POST | `/api/problem-drafts/` | 登录 | 本人命题草稿列表/创建 |
| GET/PUT/DELETE | `/api/problem-drafts/{id}` | 创建者 | 读取、乐观锁更新、归档 |
| GET | `/api/problem-drafts/{id}/revisions` | 创建者 | 完整版本快照 |
| POST | `/api/problem-drafts/{id}/publish` | 创建者 | 仅发布通过质量门禁的草稿 |

`GET /api/ai/model-config` 返回 `source`（`personal/system/none`）、
`system_configured`、`personal_configured` 和 `api_key_configured`。
使用系统默认时不返回系统地址、模型名或密钥。个人配置存在时额外返回本人模型地址、
名称、价格等可编辑元数据，不返回密钥。PUT 始终只写入当前用户的个人配置；首次覆盖
不能省略 key，已有个人配置可省略以保留自己的 key。

系统配置只从服务器环境首次初始化，无用户级系统配置写接口。
已有默认配置的非敏感模型/价格更新由服务器管理员显式运行
`python scripts/configure_system_ai.py --apply`；不覆盖密钥或历史费用。
创建任务和实际生成均按个人优先、系统回退解析配置；个人请求失败不会触发系统付费重试。

个人配置 PUT/GET 支持 `currency: "USD" | "CNY"`（默认 USD）、
`cached_input_price: number | null`（非负且有限；null 按普通输入价）。
任务详情的 `usage.currency` 及历史列表的 `currency` 为任务保存的计价币种，不隐式换汇。
`usage_details.phases` 各阶段包含 `tier`（flash/quality/personal/default）、
`routing_reason`、`cached_input_tokens`（null 表示服务商未报告）、`cost` 与 `pricing`。
`pricing` 是该阶段的 `input_price/output_price/cached_input_price/price_unit/currency` 快照；
阶段还记录 `output_token_limit` 与服务商提供的 `reasoning_tokens`（缺失时 null），
推理 Token 已包含在输出 Token 中，不额外重复计费，也不返回思维链正文。
任务总费用按各阶段单独计算后相加，不能使用顶层默认价格直接乘总 Token。
为兼容旧记录，保留 `usage_details.pricing` 默认价格；新客户端应优先使用阶段价格。

## 做题草稿

| Method | Path | 权限 | 说明 |
| --- | --- | --- | --- |
| GET/PUT/DELETE | `/api/workspace-drafts/{problem_id}/{language}` | 登录 | 按用户、题目、语言恢复、保存或删除源码草稿 |

提供商需兼容 `POST {provider_url}/chat/completions` 的 OpenAI 流式协议。生产环境仅
允许 HTTPS 和公网地址；本地 mock 测试可显式设置 `OJ_ALLOW_PRIVATE_AI_ENDPOINTS=true`。
AI 完整质量门禁要求独立暴力解与确定性数据生成器；生成器在评测资源限制中运行，
输出 20–100 组唯一输入。参考解与 oracle 全部对拍一致且 mutation score 为 100% 后，
关联命题草稿才进入 `ready` 状态。


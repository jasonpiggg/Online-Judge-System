# API reference

所有 JSON 响应均保留 `{"code": HTTP状态码, "msg": "...", "data": ...}`，Cookie
保存服务端 Session ID。除注册、登录、语言列表和健康检查外，业务接口均要求登录。
失败响应可以额外包含 `error`，其中提供稳定错误标识、面向用户的标题、修复建议、
是否适合重试及字段错误。旧客户端继续读取 `code/msg/data` 即可。

## 用户与会话

| Method | Path                        | 权限        | 说明                      |
| ------ | --------------------------- | ----------- | ------------------------- |
| POST   | `/api/users/`               | 公开        | 注册普通用户              |
| POST   | `/api/users/admin`          | 管理员      | 创建管理员                |
| POST   | `/api/auth/login`           | 公开        | 登录并设置 Session Cookie |
| POST   | `/api/auth/logout`          | 登录        | 立即销毁 Session          |
| GET    | `/api/auth/me`              | 登录        | 当前用户、角色与有效题目统计 |
| GET    | `/api/users/{user_id}`      | 本人/管理员 | 用户信息与统计            |
| PUT    | `/api/users/{user_id}/role` | 管理员      | 设置 `user/admin/banned`  |
| GET    | `/api/users/`               | 管理员      | 分页用户列表              |

## 题目与语言

| Method   | Path                                        | 权限   | 说明                              |
| -------- | ------------------------------------------- | ------ | --------------------------------- |
| GET/POST | `/api/problems/`                            | 登录   | 列表/新增；列表可附带本人练习进度 |
| GET/PUT  | `/api/problems/{problem_id}`                | 登录   | 详情/完整更新                     |
| DELETE   | `/api/problems/{problem_id}`                | 管理员 | 删除题目                          |
| PUT      | `/api/problems/{problem_id}/log_visibility` | 管理员 | 设置测例日志公开性                |
| GET      | `/api/languages/`                           | 公开   | 查询语言                          |
| POST     | `/api/languages/`                           | 登录   | 登记受限命令模板；不会安装编译器  |

语言注册只登记执行配置。服务器需事先安装相应工具；例如已有 `gcc` 时可以动态登记 C。

## 提交与日志

| Method | Path                            | 权限                 | 说明                                                     |
| ------ | ------------------------------- | -------------------- | -------------------------------------------------------- |
| POST   | `/api/submissions/`             | 登录                 | 异步提交；同一用户同一道题每分钟最多三次                                 |
| GET    | `/api/submissions/`             | 本人/管理员          | 按用户、题目、状态、是否全过筛选和分页                   |
| GET    | `/api/submissions/{id}`         | 本人/管理员          | 总体评测结果                                             |
| PUT    | `/api/submissions/{id}/rejudge` | 管理员               | 覆盖并重新评测                                           |
| GET    | `/api/submissions/{id}/log`     | 本人/管理员/公开题目 | 逐点状态；本人/管理员另含原始运行日志                   |
| GET    | `/api/logs/access/`             | 管理员               | 日志访问审计；`include_metadata=true` 返回总数和分页结果 |
| GET    | `/api/logs/roles/`              | 管理员               | 角色变更审计；支持分页，`include_metadata=true` 返回总数 |
| POST   | `/api/reset/`                   | 管理员               | 恢复确定的测试初始状态                                   |

提交列表至少提供 `user_id` 或 `problem_id`。若提供 `page`，必须同时提供
`page_size`；只有 `page_size` 时默认第一页；两者均省略时返回全部结果。

管理员可用 `all_users=true` 查询全站提交；`include_metadata=true` 的列表/详情增加 `username`，
列表仍不返回源码。管理员用户列表支持 `q` 按用户名子串（字面匹配）或精确用户 ID 搜索。
访问审计同样要求 `user_id` 或 `problem_id` 至少一项，二者都为空返回 400。
删除题目会给旧提交加上 `problem_deleted` 标记：记录和源码保留用于审计，但不再计入
`submit_count`、`resolve_count` 或题库进度；重新创建同题号不会恢复旧成绩，旧提交禁止重测。

日志响应始终包含 `status/score/counts/details/can_view_raw_logs`。只有提交者本人和管理员
会收到 `raw_logs.compile_info/run_info/error_info`；公开日志查看者即使获得 200，也只收到
逐点状态，不会收到源码、隐藏输入、标准输出或可能带源码上下文的编译日志。成功和拒绝访问
继续分别写入 200/403 访问审计。

新版网页对应入口与权限核对见 [管理员网页覆盖表](admin-web-coverage.md)。
完整实验功能入口见 [实验功能与 React 网页覆盖核对](web-scoring-coverage.md)。

## AI 智能命题

| Method         | Path                                  | 权限          | 说明                                             |
| -------------- | ------------------------------------- | ------------- | ------------------------------------------------ |
| GET            | `/api/ai/model-config`                | 登录          | 有效配置来源与状态；只返回本人配置的可编辑元数据 |
| PUT            | `/api/ai/model-config`                | 登录          | 保存加密的兼容模型配置与价格                     |
| DELETE         | `/api/ai/model-config`                | 登录          | 仅移除本人覆盖，回退系统默认；幂等               |
| POST           | `/api/ai/problem-tasks/`              | 登录          | 创建流式命题任务                                 |
| GET            | `/api/ai/problem-tasks/`              | 登录          | 本人任务；可分页并排除已归档任务                 |
| GET            | `/api/ai/problem-tasks/{id}`          | 创建者/管理员 | 查询进度、结果、Token 与费用                     |
| PUT            | `/api/ai/problem-tasks/{id}/cancel`   | 创建者/管理员 | 实际中断后台任务                                 |
| DELETE         | `/api/ai/problem-tasks/{id}`          | 创建者/管理员 | 取消运行任务后归档；重复操作幂等                 |
| POST           | `/api/ai/problem-tasks/{id}/save-draft` | 创建者      | 零费用把失败/取消任务的可用成果另存为草稿        |
| POST           | `/api/ai/conversations/`              | 登录          | 获取当前题目的本人做题会话                       |
| GET/POST       | `/api/ai/conversations/{id}/messages` | 创建者        | 分页读取或发送做题助手消息                       |
| POST           | `/api/ai/conversations/{id}/new`      | 创建者        | 开始不继承旧上下文的新话题                       |
| GET/POST       | `/api/problem-drafts/`                | 登录          | 本人草稿列表/创建；支持分页与归档筛选            |
| GET/PUT/DELETE | `/api/problem-drafts/{id}`            | 创建者        | 读取、部分草稿乐观锁更新、归档                   |
| GET            | `/api/problem-drafts/{id}/revisions`  | 创建者        | 完整版本快照                                     |
| POST           | `/api/problem-drafts/{id}/verify`     | 创建者        | 本地检查；请求体可选 `basic` 或 `full`           |
| POST           | `/api/problem-drafts/{id}/publish`    | 创建者        | 仅发布通过质量门禁的草稿                         |

`GET /api/ai/model-config` 返回 `source`（`personal/system/none`）、
`system_configured`、`personal_configured` 和 `api_key_configured`。
使用系统默认时不返回系统地址、模型名或密钥。个人配置存在时额外返回本人模型地址、
名称、价格等可编辑元数据，不返回密钥。PUT 始终只写入当前用户的个人配置；首次覆盖
不能省略 key，已有个人配置可省略以保留自己的 key。

做题助手消息接口默认保留旧版最近 50 条列表响应；传入 `include_metadata=true` 时按
`page/page_size` 返回 `messages/total/page`。新话题通过递增服务端上下文代次保留旧任务
及其用量记录，但后续请求不会再发送此前对话；有回答仍在生成时拒绝切换话题。同一话题
最多携带最近 4 轮、20,000 字节历史，当前问题、当前代码和结构化评测不受历史裁剪影响。

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

网页将命题任务显式分为三类：`revise` 只修改所选白名单区域并返回 `section_patch`；
`review` 审查完整题面和已有资产并返回 `review_patch`，其中包含不可变的 `baseline`、
`proposal`、`review` 与 `source_draft_revision`；`generate/all` 可补全整题并运行完整质量
门禁。不完整草稿不会从局部修改或审查静默升级为完整生成。任务详情另返回
`source_draft_id`，客户端据此回到原草稿并用 revision 乐观锁采纳 Patch。

## 做题草稿

| Method         | Path                                            | 权限 | 说明                                       |
| -------------- | ----------------------------------------------- | ---- | ------------------------------------------ |
| GET/PUT/DELETE | `/api/workspace-drafts/{problem_id}/{language}` | 登录 | 按用户、题目、语言恢复、保存或删除源码草稿 |

提供商需兼容 `POST {provider_url}/chat/completions` 的 OpenAI 流式协议。生产环境仅
允许 HTTPS 和公网地址；本地 mock 测试可显式设置 `OJ_ALLOW_PRIVATE_AI_ENDPOINTS=true`。
AI 完整质量门禁要求独立暴力解与确定性数据生成器；生成器在评测资源限制中运行，
输出 20–100 组唯一输入。参考解与 oracle 全部对拍一致且 mutation score 为 100% 后，
关联命题草稿才进入 `ready` 状态。

`POST /api/problem-drafts/{id}/verify` 的 `{"mode":"basic"}` 检查题目 Schema、题号、
限制、样例、测试与 Markdown/LaTeX；有参考解时还会实际运行全部样例和测试点，未提供
参考解时返回明确警告但允许发布手工题。`{"mode":"full"}` 继续执行错误解检测、独立
oracle 和 20–100 组随机对拍。省略请求体保持旧客户端的 `full` 行为。草稿响应中的
`verification_level` 与 `verification_summary` 只对应被检查的 revision；任何编辑都会清除
旧验证结论并重新阻止发布。


命题草稿和任务列表不带 `include_metadata` 时保持旧数组响应。新版网页使用独立分页和归档筛选。命题验证前及失败后始终保留版本化 `candidate` 信封；失败成果可零费用另存为未验证草稿，恢复草稿仍须通过发布检查。

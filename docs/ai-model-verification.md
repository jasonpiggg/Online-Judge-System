# 双模型接入验证记录（2026-09-04）

## 实际连接与端到端结果

使用服务器 `.env` 的凭据调用真实服务，不回显 API key、主密钥或服务地址。
初始最小 JSON 调用：GLM-5.3-Flash 和 GLM-5.3 均 HTTP 200，返回正确结果。

最终真实端到端测试使用独立临时数据库，未发布测试题到正式题库：

| 阶段 | 模型 | 输入 Token | 输出 Token（含推理） | 缓存命中 | 费用估算 CNY |
| --- | --- | ---: | ---: | ---: | ---: |
| 初稿 | glm-5.3-flash | 420 | 2328 | 0 | 0.0034272 |
| 完整复审 | glm-5.3 | 2110 | 2601 | 0 | 0.0897080 |
| 合计 | 分阶段单独计价 | 2530 | 4929 | 0 | 0.0931352 |

最终状态 completed，quality_gate_passed=true。参考解通过 3 个样例和 20 个测试点；
独立 oracle 对拍 20 组输入全部一致；两个典型错误算法都被有效卡错，mutation score=100%。
这是该次生成结果的验证证据，不代表所有未来题目都一定正确或服务永不超时。
表中费用仅是这一次成功测试的费用，其他诊断调用亦消耗 Token，以服务商账单为准。

## 发现及处理的问题

1. 首轮默认推理设置下，Flash 流持续输出，但在 240 秒阶段超时后中止；保留估算用量，
   未自动重试。当前两档显式设置 reasoning_effort=high，阶段/全任务上限 300/900 秒。
2. 两次真实生成进入本地验证，但生成器源代码出现 `import ` / `.dumps`，未获发布许可。
   最小同输入对照复现：开启 GLM-5.3 `response_format={"type":"json_object"}` 时，
   `import json\nprint(json.dumps([1,2]))` 中的 `json` 被删除；不发送该参数时完整保留。
   当前系统两档关闭该参数，仍要求 JSON，并严格执行解析、Schema 验证和全部本地质量门禁。
3. 数据生成器现在使用独立的 3 秒 / 128 MB 受限预算，避免错误地继承极小的解题资源限制。
   参考解、错误解、oracle 的题目资源限制不因此放宽。这是额外的隔离改进，不将其误记为
   上述 `json` 标识符缺失的根因。

## 已生效的策略及价格

系统配置在当前数据库已同步，存储的加密凭据与 `.env` 匹配；未修改密钥。
个人配置优先；系统分流不接管个人模型，也不在个人调用失败时转用服务器密钥。

- Flash：明确的入门题初稿、简单题面润色。
- GLM-5.3：复杂/难度不明确的命题、算法修改、测试设计、正式审核、第二阶段完整复审。
- 路由是保守规则，结合需求及原题/草稿 difficulty、tags，不是额外的模型分类调用。
- 判题与质量门禁仍由本地评测器执行，不让模型代替判题。

| 模型 | 输入 CNY / 百万 Token | 输出 | 缓存命中输入 |
| --- | ---: | ---: | ---: |
| glm-5.3-flash | 0.4 | 1.4 | 0.115 |
| glm-5.3 | 8 | 28 | 2 |

价格来自用户提供的截图。Flash 为限时折扣，原价 0.8 / 2.8 / 0.23；确切截止日期未知，
不自动推测或换价。截图缓存存储暂免；无存储时长指标时不另计存储费用。
支持 USD/CNY，不隐式换汇；旧记录保留 USD 和原金额，各阶段保存币种/价格快照。
缓存输入量是总输入的子集，按官方 `usage.prompt_tokens_details.cached_tokens` 解析，
不重复收取普通输入费用；未报告缓存量时按普通输入价估算。

## 回归覆盖与复现

最终回归：127 passed、10 skipped（78.18 秒）；Ruff、mypy 和 git diff --check 均通过。

覆盖了难度/动作路由、个人覆盖、流式双模型调用、缓存折扣、USD/CNY API 与前端表单、
阶段费率展示、v4→v5 备份迁移、历史 USD 保留、显式同步不覆盖密钥、输出截断不重试、
生成器独立预算、严格 JSON 解析和源码保真。Windows 上 Linux 专属评测测试按条件跳过。

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check src frontend tests scripts/configure_system_ai.py scripts/check_ai_authoring.py
.venv\Scripts\python.exe -m mypy src/oj

# 显式同步非敏感配置；不发起模型请求
.venv\Scripts\python.exe scripts/configure_system_ai.py --apply

# 只有明确需要再次真实测试时运行：会付费，无自动重试
.venv\Scripts\python.exe scripts/check_ai_authoring.py --paid
```

`.env` 继续被 Git 忽略；本轮未执行 commit、push 或发布操作。

参考：[官方缓存指标](https://docs.bigmodel.cn/cn/guide/capabilities/cache)、
[官方推理参数](https://docs.bigmodel.cn/cn/guide/start/concept-param)。

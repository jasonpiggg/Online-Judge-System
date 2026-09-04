import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, json, errorText, queryClient } from "../api";
import type { Problem, User } from "../types";
import { Button } from "../components/ui/button";
import { Code, RichText } from "../components/Markdown";
import { Statement } from "../components/Statement";
import { TaskProgress, terminal, useTask } from "../components/AI";
type Draft = {
  id: string;
  base_problem_id: string | null;
  status: string;
  requirement: string;
  problem: Problem;
  reference_solution: string;
  brute_solution: string;
  generator_code: string;
  review: Record<string, any>;
  revision: number;
};
const sample = z.object({ input: z.string(), output: z.string() });
const problemSchema = z.object({
  id: z
    .string()
    .regex(/^[A-Za-z0-9_-]{1,64}$/, "题号只能包含字母、数字、下划线和连字符"),
  title: z.string().min(1, "请填写标题"),
  description: z.string().min(1, "请填写题面"),
  input_description: z.string().min(1),
  output_description: z.string().min(1),
  constraints: z.string().min(1),
  hint: z.string(),
  source: z.string(),
  author: z.string(),
  difficulty: z.string(),
  tags: z.array(z.string()),
  samples: z.array(sample).min(1),
  testcases: z.array(sample).min(1),
  time_limit: z.number().nullable(),
  memory_limit: z.number().nullable(),
  public_cases: z.boolean(),
});
type FormProblem = z.infer<typeof problemSchema>;
const empty: FormProblem = {
  id: "",
  title: "",
  description: "",
  input_description: "",
  output_description: "",
  constraints: "",
  hint: "",
  source: "",
  author: "",
  difficulty: "",
  tags: [],
  samples: [{ input: "", output: "" }],
  testcases: [{ input: "", output: "" }],
  time_limit: null,
  memory_limit: null,
  public_cases: false,
};
function clean(p: Problem): FormProblem {
  return {
    ...empty,
    ...p,
    time_limit: p.limit_inheritance?.time_limit ? null : (p.time_limit ?? null),
    memory_limit: p.limit_inheritance?.memory_limit
      ? null
      : (p.memory_limit ?? null),
  };
}
export function Authoring() {
  const navigate = useNavigate();
  const [requirement, setRequirement] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const pending = useRef<{ text: string; key: string } | undefined>(undefined);
  const drafts = useQuery({
    queryKey: ["drafts"],
    queryFn: () => api<Draft[]>("/problem-drafts/"),
  });
  const tasks = useQuery({
    queryKey: ["tasks"],
    queryFn: () => api<Record<string, any>[]>("/ai/problem-tasks/"),
    refetchInterval: (q) =>
      q.state.data?.some((t) => !terminal(t.status)) ? 5000 : false,
  });
  const create = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const d = await api<Draft>("/problem-drafts/", json("POST", {}));
      navigate("/authoring/drafts/" + d.id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const generate = async () => {
    if (busy || requirement.trim().length < 10) return;
    setBusy(true);
    setError("");
    if (pending.current?.text !== requirement)
      pending.current = { text: requirement, key: crypto.randomUUID() };
    try {
      const r = await api<{ task_id: string }>("/ai/problem-tasks/", {
        ...json("POST", { requirement, workflow_version: 2 }),
        headers: { "Idempotency-Key": pending.current.key },
      });
      pending.current = undefined;
      navigate("/authoring/tasks/" + r.task_id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page">
      <div className="row">
        <h1>命题中心</h1>
        <Button onClick={() => void create()} disabled={busy}>
          手动创建题目
        </Button>
      </div>
      <section className="author-compose">
        <h2>描述你想出的题目</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void generate();
          }}
        >
          <textarea
            aria-label="命题需求"
            value={requirement}
            onChange={(e) => setRequirement(e.target.value)}
            placeholder="例如：面向初学者的前缀和题目，使用生活场景，包含清晰的样例和边界测试。"
            minLength={10}
            required
          />
          <div className="row">
            <p className="muted">
              题面与解法 → 测试设计 →
              复审验证。必要时最多自动修复一次，将产生模型调用费用。
            </p>
            <Button
              variant="default"
              disabled={busy || requirement.trim().length < 10}
            >
              开始生成
            </Button>
          </div>
        </form>
      </section>
      {error && <p role="alert">{error}</p>}
      <h2>我的草稿</h2>
      <div className="draft-list">
        {drafts.data
          ?.filter((d) => d.status !== "archived")
          .map((d) => (
            <Link
              className="draft-row"
              key={d.id}
              to={"/authoring/drafts/" + d.id}
            >
              <strong>{d.problem?.title || "未命名题目"}</strong>
              <span className="muted">
                {
                  (
                    {
                      ready: "可发布",
                      published: "已发布",
                      draft: "编辑中",
                      verifying: "验证中",
                    } as Record<string, string>
                  )[d.status]
                }{" "}
                · 版本 {d.revision}
              </span>
            </Link>
          ))}
        {drafts.data?.length === 0 && (
          <p className="muted">生成或创建一道题，草稿会保存在这里。</p>
        )}
      </div>
      <h2>AI 任务</h2>
      {tasks.data?.map((t) => (
        <Link className="draft-row" key={t.id} to={"/authoring/tasks/" + t.id}>
          <span>{t.progress}</span>
          <span className="muted">
            {new Date(t.created_at).toLocaleString()}
          </span>
        </Link>
      ))}
    </div>
  );
}
export function DraftPage({ user }: { user: User }) {
  const { id } = useParams();
  const { data, error } = useQuery({
    queryKey: ["draft", id],
    queryFn: () => api<Draft>("/problem-drafts/" + id),
    refetchOnMount: "always",
  });
  return error ? (
    <p role="alert">{error.message}</p>
  ) : data ? (
    <DraftEditor key={id + ":" + data.revision} draft={data} user={user} />
  ) : (
    <p className="skeleton">正在读取草稿…</p>
  );
}
function DraftEditor({ draft, user }: { draft: Draft; user: User }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const step = params.get("step") || "题面与样例";
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [requirement, setRequirement] = useState(""),
    [target, setTarget] = useState("statement"),
    [reference, setReference] = useState(draft.reference_solution),
    [brute, setBrute] = useState(draft.brute_solution),
    [generator, setGenerator] = useState(draft.generator_code),
    [raw, setRaw] = useState(""),
    [preview, setPreview] = useState(false);
  const version = useRef(draft.revision);
  const pending = useRef<{ hash: string; key: string } | undefined>(undefined);
  const backup = `oj-author-${user.user_id}-${draft.id}`;
  const local = useRef(localStorage.getItem(backup));
  const [backupConflict, setBackupConflict] = useState(() => {
    try {
      return (
        !!local.current && JSON.parse(local.current).revision !== draft.revision
      );
    } catch {
      return false;
    }
  });
  let initial = clean(draft.problem || ({} as Problem));
  if (local.current) {
    try {
      const saved = JSON.parse(local.current);
      if (saved.revision === draft.revision) initial = saved.problem;
    } catch {
      /* Keep server draft if local backup is malformed. */
    }
  }
  const form = useForm<FormProblem>({
    resolver: zodResolver(problemSchema),
    defaultValues: initial,
  });
  const samples = useFieldArray({ control: form.control, name: "samples" }),
    cases = useFieldArray({ control: form.control, name: "testcases" });
  const values = form.watch();
  const [reviewAssets, setReviewAssets] = useState<Record<string, any>>(() => ({
    review: "人工编辑的题目，需经本地验证。",
    coverage: { basic: "", boundary: "", scale: "" },
    wrong_solutions: [
      { code: "", reason: "" },
      { code: "", reason: "" },
    ],
    ...draft.review,
  }));
  const savedContent = useRef(
    JSON.stringify({
      problem: clean(draft.problem || ({} as Problem)),
      reference: draft.reference_solution,
      brute: draft.brute_solution,
      generator: draft.generator_code,
      review: draft.review,
    }),
  );
  const content = JSON.stringify({
    problem: values,
    reference,
    brute,
    generator,
    review: reviewAssets,
  });
  const dirty = content !== savedContent.current;
  useEffect(() => {
    if (!local.current) return;
    try {
      const saved = JSON.parse(local.current);
      if (saved.revision !== draft.revision) {
        setBackupConflict(true);
        return;
      }
      if (saved.reference !== undefined) setReference(saved.reference);
      if (saved.brute !== undefined) setBrute(saved.brute);
      if (saved.generator !== undefined) setGenerator(saved.generator);
      if (saved.review) setReviewAssets(saved.review);
    } catch {
      /* Invalid backups never replace the server draft. */
    }
  }, []);
  useEffect(() => {
    if (dirty && !backupConflict) {
      try {
        localStorage.setItem(
          backup,
          JSON.stringify({ revision: version.current, ...JSON.parse(content) }),
        );
      } catch {
        setError("本机备份失败，请保存草稿或复制内容。");
      }
    }
  }, [content, backup, dirty, backupConflict]);
  const save = async (p: FormProblem) => {
    if (backupConflict) throw new Error("请先处理本机与云端草稿的版本冲突");
    if (!dirty) return { ...draft, revision: version.current };
    const body = {
      base_problem_id: draft.base_problem_id,
      requirement: draft.requirement,
      problem: p,
      reference_solution: reference,
      brute_solution: brute,
      generator_code: generator,
      review: reviewAssets,
      revision: version.current,
    };
    const d = await api<Draft>(
      "/problem-drafts/" + draft.id,
      json("PUT", body),
    );
    version.current = d.revision;
    savedContent.current = JSON.stringify({
      problem: p,
      reference,
      brute,
      generator,
      review: reviewAssets,
    });
    form.reset(p);
    localStorage.removeItem(backup);
    queryClient.setQueryData(["draft", draft.id], d);
    await queryClient.invalidateQueries({ queryKey: ["drafts"] });
    setMessage("草稿已保存");
    return d;
  };
  const runAI = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const p = problemSchema.parse(form.getValues());
      const saved = await save(p);
      const body = {
        draft_id: draft.id,
        problem_id: draft.base_problem_id,
        requirement:
          requirement || "请严格检查当前草稿，修复错误并完善质量验证。",
        action:
          target === "review"
            ? "review"
            : target === "all"
              ? "generate"
              : "revise",
        target_section: target,
        workflow_version: 2,
      };
      const hash = JSON.stringify({ ...body, revision: saved.revision });
      if (pending.current?.hash !== hash)
        pending.current = { hash, key: crypto.randomUUID() };
      const t = await api<{ task_id: string }>("/ai/problem-tasks/", {
        ...json("POST", body),
        headers: { "Idempotency-Key": pending.current.key },
      });
      navigate("/authoring/tasks/" + t.task_id);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const array = (name: "samples" | "testcases") => {
    const list = name === "samples" ? samples : cases;
    return (
      <section>
        <h3>{name === "samples" ? "公开样例" : "评测测试点"}</h3>
        {list.fields.map((f, i) => (
          <div className="sample-editor" key={f.id}>
            <div className="row">
              <h4>
                {name === "samples" ? "样例" : "测试点"} {i + 1}
              </h4>
              <Button
                type="button"
                variant="ghost"
                disabled={list.fields.length === 1}
                onClick={() => list.remove(i)}
              >
                移除
              </Button>
            </div>
            <div className="samples">
              <label>
                输入
                <textarea {...form.register(`${name}.${i}.input`)} />
              </label>
              <label>
                输出
                <textarea {...form.register(`${name}.${i}.output`)} />
              </label>
            </div>
          </div>
        ))}
        <Button
          type="button"
          onClick={() => list.append({ input: "", output: "" })}
        >
          添加{name === "samples" ? "样例" : "测试点"}
        </Button>
      </section>
    );
  };
  return (
    <div className="page">
      <Link to="/authoring">← 命题中心</Link>
      <div className="row">
        <h1>{values.title || "创建题目"}</h1>
        <Button onClick={() => setPreview(!preview)}>
          {preview ? "继续编辑" : "预览题面"}
        </Button>
      </div>
      <div className="step-tabs">
        {["题面与样例", "测试与解法", "检查与发布"].map((t) => (
          <Button
            key={t}
            variant={step === t ? "default" : "ghost"}
            onClick={() => setParams({ step: t })}
          >
            {t}
          </Button>
        ))}
      </div>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {backupConflict && (
        <section className="notice">
          <h3>本机还有不同版本的草稿</h3>
          <p>云端版本已更新。展开对比并选择保留内容，所有修改会重新验证。</p>
          <details>
            <summary>查看本机备份</summary>
            <Code text={local.current || ""} />
          </details>
          <Button
            onClick={() => {
              const saved = JSON.parse(local.current!);
              form.reset(saved.problem, { keepDefaultValues: true });
              setReference(saved.reference ?? reference);
              setBrute(saved.brute ?? brute);
              setGenerator(saved.generator ?? generator);
              setReviewAssets(saved.review ?? reviewAssets);
              setBackupConflict(false);
            }}
          >
            恢复本机内容
          </Button>
          <Button
            onClick={() => {
              sessionStorage.setItem(backup + "-conflict", local.current!);
              localStorage.removeItem(backup);
              setBackupConflict(false);
            }}
          >
            继续使用云端版本
          </Button>
        </section>
      )}
      {preview ? (
        <Statement problem={values as Problem} />
      ) : (
        <form
          className="form-grid"
          onSubmit={form.handleSubmit(
            async (p) => {
              setBusy(true);
              setError("");
              try {
                await save(p);
              } catch (e) {
                setError(errorText(e));
              } finally {
                setBusy(false);
              }
            },
            () => setError("请完善题号、标题、题面、输入输出格式和数据范围。"),
          )}
        >
          {step === "题面与样例" && (
            <>
              <div className="samples">
                <label>
                  题号
                  <input {...form.register("id")} />
                </label>
                <label>
                  标题
                  <input {...form.register("title")} />
                </label>
              </div>
              <div className="samples">
                <label>
                  难度
                  <input {...form.register("difficulty")} />
                </label>
                <label>
                  标签（逗号分隔）
                  <input
                    value={values.tags.join(", ")}
                    onChange={(e) =>
                      form.setValue(
                        "tags",
                        e.target.value
                          .split(",")
                          .map((v) => v.trim())
                          .filter(Boolean),
                        { shouldDirty: true },
                      )
                    }
                  />
                </label>
              </div>
              {(
                [
                  ["description", "题目描述"],
                  ["input_description", "输入格式"],
                  ["output_description", "输出格式"],
                  ["constraints", "数据范围"],
                  ["hint", "解题提示"],
                ] as const
              ).map(([key, title]) => (
                <label key={key}>
                  {title}
                  <textarea
                    {...form.register(key)}
                    rows={key === "description" ? 8 : 3}
                  />
                  <span className="muted">支持 Markdown 和数学公式</span>
                </label>
              ))}
              {array("samples")}
            </>
          )}
          {step === "测试与解法" && (
            <>
              {array("testcases")}
              <label>
                参考解（Python）
                <textarea
                  className="source-input"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                  rows={10}
                />
              </label>
              <details>
                <summary>独立对拍与资源限制</summary>
                <p className="muted">
                  本地验证会运行独立 oracle、生成器和典型错误解，不调用模型。
                </p>
                {["basic", "boundary", "scale"].map((key, i) => (
                  <label key={key}>
                    {["基本测试覆盖", "边界测试覆盖", "规模测试覆盖"][i]}
                    <textarea
                      value={reviewAssets.coverage?.[key] || ""}
                      onChange={(e) =>
                        setReviewAssets({
                          ...reviewAssets,
                          coverage: {
                            ...reviewAssets.coverage,
                            [key]: e.target.value,
                          },
                        })
                      }
                    />
                  </label>
                ))}
                {reviewAssets.wrong_solutions?.map(
                  (wrong: { code: string; reason: string }, i: number) => (
                    <section key={i}>
                      <h4>典型错误解 {i + 1}</h4>
                      <label>
                        错误原因
                        <input
                          value={wrong.reason}
                          onChange={(e) =>
                            setReviewAssets({
                              ...reviewAssets,
                              wrong_solutions: reviewAssets.wrong_solutions.map(
                                (v: unknown, j: number) =>
                                  j === i
                                    ? { ...wrong, reason: e.target.value }
                                    : v,
                              ),
                            })
                          }
                        />
                      </label>
                      <label>
                        代码
                        <textarea
                          className="source-input"
                          value={wrong.code}
                          onChange={(e) =>
                            setReviewAssets({
                              ...reviewAssets,
                              wrong_solutions: reviewAssets.wrong_solutions.map(
                                (v: unknown, j: number) =>
                                  j === i
                                    ? { ...wrong, code: e.target.value }
                                    : v,
                              ),
                            })
                          }
                        />
                      </label>
                    </section>
                  ),
                )}
                <label>
                  独立 oracle
                  <textarea
                    className="source-input"
                    value={brute}
                    onChange={(e) => setBrute(e.target.value)}
                  />
                </label>
                <label>
                  随机输入生成器
                  <textarea
                    className="source-input"
                    value={generator}
                    onChange={(e) => setGenerator(e.target.value)}
                  />
                </label>
                <div className="samples">
                  <label>
                    时间限制（秒，留空继承）
                    <input
                      type="number"
                      step="any"
                      value={values.time_limit ?? ""}
                      onChange={(e) =>
                        form.setValue(
                          "time_limit",
                          e.target.value ? Number(e.target.value) : null,
                          { shouldDirty: true },
                        )
                      }
                    />
                  </label>
                  <label>
                    内存限制（MB，留空继承）
                    <input
                      type="number"
                      value={values.memory_limit ?? ""}
                      onChange={(e) =>
                        form.setValue(
                          "memory_limit",
                          e.target.value ? Number(e.target.value) : null,
                          { shouldDirty: true },
                        )
                      }
                    />
                  </label>
                </div>
                {user.role === "admin" && (
                  <label className="check">
                    <input type="checkbox" {...form.register("public_cases")} />
                    公开测试点日志
                  </label>
                )}
              </details>
            </>
          )}
          {step === "检查与发布" && (
            <>
              <h2>
                {draft.status === "ready"
                  ? "验证已通过"
                  : "草稿尚未通过完整验证"}
              </h2>
              <p>发布前需要参考解评测、错误解检测及独立对拍全部通过。</p>
              {draft.review?.review && <RichText text={draft.review.review} />}
              <Button
                type="button"
                variant="default"
                disabled={
                  busy || draft.status !== "ready" || dirty || backupConflict
                }
                onClick={async () => {
                  setBusy(true);
                  try {
                    const result = await api<{ id: string }>(
                      `/problem-drafts/${draft.id}/publish`,
                      json("POST"),
                    );
                    navigate("/problems/" + result.id);
                  } catch (e) {
                    setError(errorText(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                发布题目
              </Button>
              <Button
                type="button"
                disabled={busy || backupConflict}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    const saved = await save(
                      problemSchema.parse(form.getValues()),
                    );
                    const hash = "verify:" + saved.revision;
                    if (pending.current?.hash !== hash)
                      pending.current = { hash, key: crypto.randomUUID() };
                    const t = await api<{ task_id: string }>(
                      `/problem-drafts/${draft.id}/verify`,
                      {
                        ...json("POST"),
                        headers: { "Idempotency-Key": pending.current.key },
                      },
                    );
                    navigate("/authoring/tasks/" + t.task_id);
                  } catch (e) {
                    setError(errorText(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                运行本地验证（不调用 AI）
              </Button>
              <details>
                <summary>高级：JSON 导入与导出</summary>
                <Code text={JSON.stringify(values, null, 2)} />
                <label>
                  导入题目 JSON
                  <textarea
                    value={raw}
                    onChange={(e) => setRaw(e.target.value)}
                  />
                </label>
                <Button
                  type="button"
                  onClick={() => {
                    try {
                      const p = problemSchema.parse(clean(JSON.parse(raw)));
                      form.reset(p, { keepDefaultValues: true });
                      setMessage("已载入，保存后生效");
                    } catch (e) {
                      setError(errorText(e));
                    }
                  }}
                >
                  载入 JSON
                </Button>
              </details>
            </>
          )}
          <div className="sticky-actions">
            <span className="muted">
              版本 {version.current} · {dirty ? "修改已保留在本机" : "已同步"}
            </span>
            <Button variant="default" disabled={busy} type="submit">
              保存草稿
            </Button>
          </div>
        </form>
      )}
      <details className="ai-inline" open>
        <summary>AI 辅助当前草稿</summary>
        <div className="filters">
          <select
            aria-label="AI 修改范围"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            {Object.entries({
              statement: "润色题面",
              samples: "完善样例",
              constraints: "改进约束",
              testcases: "设计测试",
              review: "仅审查",
              all: "完善整题并验证",
            }).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <input
            aria-label="AI 修改要求"
            value={requirement}
            onChange={(e) => setRequirement(e.target.value)}
            placeholder="补充你的要求，无需再次粘贴题目"
          />
          <Button disabled={busy} onClick={() => void runAI()}>
            开始
          </Button>
        </div>
        <p className="muted">
          使用当前已保存草稿；局部修改需采纳后重新验证。调用产生费用，最多自动修复一次。
        </p>
      </details>
    </div>
  );
}
export function AuthoringTask() {
  const { id } = useParams();
  const { data: t, error, disconnected } = useTask(id);
  const navigate = useNavigate();
  const [actionError, setActionError] = useState(""),
    [busy, setBusy] = useState(false);
  if (!t) return <p className="skeleton">{error?.message || "读取任务…"}</p>;
  const result = t.result,
    preview = t.preview || {};
  const accept = async () => {
    if (!result || !t.draft_id) return;
    setBusy(true);
    try {
      const current = await api<Draft>("/problem-drafts/" + t.draft_id);
      if (current.revision !== result.source_draft_revision)
        throw new Error("草稿已在别处修改，请比较后手动合并建议。");
      const updated = await api<Draft>(
        "/problem-drafts/" + t.draft_id,
        json("PUT", {
          base_problem_id: current.base_problem_id,
          requirement: current.requirement,
          problem: result.problem,
          reference_solution: current.reference_solution,
          brute_solution: current.brute_solution,
          generator_code: current.generator_code,
          review: current.review,
          revision: current.revision,
          change_summary: "采纳 AI 局部建议",
        }),
      );
      queryClient.setQueryData(["draft", t.draft_id], updated);
      navigate("/authoring/drafts/" + t.draft_id);
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page">
      <Link to="/authoring">← 命题中心</Link>
      <h1>AI 命题</h1>
      <p>{t.requirement}</p>
      <TaskProgress task={t} disconnected={disconnected} />
      {!terminal(t.status) && (
        <p className="muted">
          生成中 · 以下内容尚未验证，完成前不能发布。离开页面后任务仍会继续。
        </p>
      )}
      {t.status === "completed" &&
        t.draft_id &&
        result?.verification?.quality_gate_passed && (
          <Button variant="default" asChild>
            <Link to={"/authoring/drafts/" + t.draft_id + "?step=检查与发布"}>
              打开已验证草稿
            </Link>
          </Button>
        )}
      {result?.kind === "section_patch" && (
        <>
          <p className="muted">局部建议已复审，尚未通过整题验证。</p>
          <RichText text={result.review} />
          <details>
            <summary>查看修改前后差异</summary>
            <div className="samples">
              <div>
                <h3>修改前</h3>
                <Statement problem={result.baseline} />
              </div>
              <div>
                <h3>修改后</h3>
                <Statement problem={result.problem} />
              </div>
            </div>
          </details>
          <Button
            disabled={busy || t.status !== "completed" || !t.draft_id}
            variant="default"
            onClick={() => void accept()}
          >
            采纳到草稿
          </Button>
        </>
      )}
      {result?.kind === "review" && <RichText text={result.review} />}
      {result?.initial_problem && (
        <details>
          <summary>查看复审前后的题面</summary>
          <div className="samples">
            <div>
              <h3>初稿</h3>
              <Statement problem={result.initial_problem} />
            </div>
            <div>
              <h3>最终版本</h3>
              <Statement problem={result.problem} />
            </div>
          </div>
        </details>
      )}
      <div className="generated-preview">
        {result?.problem ? (
          <>
            <h2>{result.problem.title}</h2>
            <Statement problem={result.problem} />
          </>
        ) : (
          <>
            {preview.title && <h2>{preview.title}</h2>}
            {[
              "description",
              "input_description",
              "output_description",
              "constraints",
            ].map((k) => preview[k] && <RichText key={k} text={preview[k]} />)}
            {preview.samples?.map(
              (s: { input: string; output: string }, i: number) => (
                <div className="samples" key={i}>
                  <Code text={s.input} />
                  <Code text={s.output} />
                </div>
              ),
            )}
          </>
        )}
        {(result?.reference_solution || preview.reference_solution) && (
          <details>
            <summary>参考解</summary>
            <Code
              text={result?.reference_solution || preview.reference_solution}
            />
          </details>
        )}
        {result?.review &&
          result.kind !== "section_patch" &&
          result.kind !== "review" && (
            <details>
              <summary>审查意见</summary>
              <RichText text={result.review} />
            </details>
          )}
      </div>
      {["failed", "cancelled"].includes(t.status) && (
        <div className="notice">
          <p>已保留当前成果。重新生成会创建新任务并产生费用。</p>
          <Button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await api<{ task_id: string }>("/ai/problem-tasks/", {
                  ...json("POST", {
                    requirement: t.requirement,
                    problem_id: t.problem_id,
                    draft_id: t.draft_id,
                    workflow_version: 2,
                    action: t.action === "verify" ? "generate" : t.action,
                    target_section: t.target_section,
                    resume_task_id:
                      result?.kind === "candidate" ? t.task_id : undefined,
                  }),
                  headers: { "Idempotency-Key": crypto.randomUUID() },
                });
                navigate("/authoring/tasks/" + r.task_id);
              } catch (e) {
                setActionError(errorText(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {result?.kind === "candidate" ? "从已完成阶段继续" : "重新生成"}
          </Button>
        </div>
      )}
      {actionError && <p role="alert">{actionError}</p>}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, json, errorText, queryClient } from "../api";
import { RichText } from "./Markdown";
import { Button } from "./ui/button";
import { Pagination } from "./Pagination";
import { ErrorNotice } from "./ErrorNotice";
import { DiffView } from "./DiffView";
export type Task = {
  task_id: string;
  action?: string;
  target_section?: string;
  kind?: string;
  status: string;
  stage: string;
  progress: string;
  created_at: string;
  updated_at: string;
  requirement: string;
  draft_id?: string;
  problem_id?: string;
  result?: Record<string, any>;
  preview?: Record<string, any>;
  error?: string;
  code_snapshot?: string;
  language?: string;
  submission_id?: number;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cost: number;
    currency: string;
    source: string;
  };
  usage_details?: unknown;
};
export const terminal = (status?: string) =>
  ["completed", "failed", "cancelled"].includes(status || "");

export type CodeSuggestion = {
  code: string;
  language: string;
  canApply: boolean;
  reason: string;
};

export function extractCodeSuggestion(
  answer: string,
  currentCode: string,
  request: string,
): CodeSuggestion | null {
  const matches = [...answer.matchAll(/```([^\n`]*)\n([\s\S]*?)```/g)].filter(
    (match) => /^(?:python|py|cpp|c\+\+|c|java|javascript|js|typescript|ts|go|rust)\b/i.test(match[1].trim()),
  );
  const candidate = matches.at(-1);
  if (!candidate) return null;
  const code = candidate[2].trimEnd();
  if (!code.trim()) return null;
  const prefix = answer.slice(Math.max(0, (candidate.index || 0) - 120), candidate.index);
  const explicitlyComplete = /(?:^|\n)(?:#{1,6}\s*)?(?:\*\*)?完整替换代码[：:](?:\*\*)?\s*$/.test(prefix);
  const userRequestedCode = /完整.{0,8}(?:代码|题解|解法|实现)|(?:给|写|提供|生成|修复|修改|改正|重写).{0,8}(?:代码|程序)|直接.{0,6}(?:代码|实现)/i.test(request);
  const lines = code.split(/\r?\n/).filter((line) => line.trim()).length;
  const looksExecutable =
    /\b(?:int\s+main|public\s+static\s+void\s+main)\b/.test(code) ||
    ((/\b(?:input\s*\(|stdin|readline\s*\()/i.test(code) || /\bdef\s+main\s*\(/.test(code)) &&
      /\bprint\s*\(|stdout|cout\s*<</i.test(code));
  const substantial = lines >= (currentCode.trim() ? 3 : 2) &&
    (!currentCode.trim() || code.length >= Math.min(120, currentCode.trim().length * 0.35));
  const unchanged = code.trim() === currentCode.trim();
  const canApply = explicitlyComplete && userRequestedCode && looksExecutable && substantial && !unchanged;
  let reason = "模型标注为完整替换代码，尚未编译或评测；请先检查差异，应用后重新提交验证。";
  if (unchanged) reason = "建议代码与当前代码相同，无需替换。";
  else if (!userRequestedCode) reason = "你没有要求替换完整程序，此代码块按讲解片段展示，不会覆盖编辑器。";
  else if (!explicitlyComplete || !looksExecutable || !substantial)
    reason = "该代码块不像完整、可运行的解答，已禁止一键覆盖；可复制需要的片段手动修改。";
  const fenceLanguage = candidate[1].trim().toLowerCase();
  return { code, language: ({ py: "python", "c++": "cpp" } as Record<string, string>)[fenceLanguage] || fenceLanguage, canApply, reason };
}
export function useTask(id?: string) {
  const [disconnected, setDisconnected] = useState(false);
  const query = useQuery({
    queryKey: ["task", id],
    queryFn: () => api<Task>(`/ai/problem-tasks/${id}`),
    enabled: !!id,
    refetchInterval: (q) =>
      !terminal(q.state.data?.status) ? (disconnected ? 2000 : 10000) : false,
  });
  useEffect(() => {
    if (!id || terminal(query.data?.status)) return;
    const source = new EventSource(`/api/ai/problem-tasks/${id}/events`);
    source.onopen = () => setDisconnected(false);
    source.onerror = () => setDisconnected(true);
    const update = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      if (data.access_lost) {
        source.close();
        window.dispatchEvent(new Event("session-expired"));
        return;
      }
      queryClient.setQueryData(["task", id], data);
      if (terminal(data.status)) source.close();
    };
    for (const name of [
      "stage",
      "preview",
      "delta",
      "usage",
      "completed",
      "failed",
      "cancelled",
    ])
      source.addEventListener(name, update as EventListener);
    return () => source.close();
  }, [id, query.data?.status]);
  return { ...query, disconnected };
}
export function TaskProgress({
  task,
  disconnected = false,
}: {
  task: Task;
  disconnected?: boolean;
}) {
  const [, tick] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    if (terminal(task.status)) return;
    const t = setInterval(() => tick((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [task.status]);
  const elapsed = Math.max(
    0,
    Math.floor(
      (Date.parse(
        terminal(task.status) ? task.updated_at : new Date().toISOString(),
      ) -
        Date.parse(task.created_at)) /
        1000,
    ),
  );
  return (
    <div className="task-status">
      <div className="row">
        <strong role="status">{task.progress}</strong>
        {!terminal(task.status) && (
          <Button
            onClick={async () => {
              try {
                await api(
                  `/ai/problem-tasks/${task.task_id}/cancel`,
                  json("PUT"),
                );
                await queryClient.invalidateQueries({
                  queryKey: ["task", task.task_id],
                });
              } catch (e) {
                setError(errorText(e));
              }
            }}
          >
            停止
          </Button>
        )}
      </div>
      <p className="muted">
        {elapsed} 秒{disconnected ? " · 连接恢复中，正在读取已保存进度" : ""}
      </p>
      {(task.error || error) && <ErrorNotice title="任务没有完成" message={task.error || error} />}
      <details>
        <summary>用量与费用</summary>
        <p className="muted">
          输入 {task.usage.input_tokens.toLocaleString()} · 输出{" "}
          {task.usage.output_tokens.toLocaleString()} Token ·{" "}
          {task.usage.currency} {task.usage.cost.toFixed(5)}（
          {task.usage.source === "provider" ? "服务商用量" : "估算用量"}）
        </p>
        <p className="muted">费用按配置单价估算；单价未配置不表示免费。</p>
      </details>
    </div>
  );
}
type Message = {
  task_id: string;
  message: string;
  status: string;
  text: string;
  code_snapshot: string;
  language?: string;
  submission_id?: number;
};
type MessagePage = { messages: Message[]; total: number; page: number };
export function Assistant({
  problemId,
  code,
  language,
  submissionId,
  onApply,
}: {
  problemId: string;
  code: string;
  language: string;
  submissionId?: string | null;
  onApply: (code: string) => void;
}) {
  const [conversation, setConversation] = useState(""),
    [contextGeneration, setContextGeneration] = useState(0),
    [active, setActive] = useState<string>(),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [proposed, setProposed] = useState<(CodeSuggestion & { baseline: string; editorLanguage: string }) | null>(null),
    [applied, setApplied] = useState<{ before: string; after: string; language: string } | null>(null),
    [copyMessage, setCopyMessage] = useState(""),
    [historyPage, setHistoryPage] = useState(1),
    [topicMessage, setTopicMessage] = useState("");
  const pending = useRef<{ hash: string; key: string } | undefined>(undefined);
  const { data: task, disconnected } = useTask(active);
  const history = useQuery({
    queryKey: ["conversation", conversation, contextGeneration, historyPage],
    queryFn: () =>
      api<MessagePage>(
        `/ai/conversations/${conversation}/messages?include_metadata=true&page=${historyPage}&page_size=5`,
      ),
    enabled: !!conversation,
  });
  useEffect(() => {
    let gone = false;
    api<{ id: string; context_generation: number }>(
      "/ai/conversations/",
      json("POST", { problem_id: problemId }),
    )
      .then((r) => {
        if (!gone) {
          setConversation(r.id);
          setContextGeneration(r.context_generation);
          setActive(undefined);
          setHistoryPage(1);
          setTopicMessage("");
        }
      })
      .catch((e) => setError(errorText(e)));
    return () => {
      gone = true;
    };
  }, [problemId]);
  useEffect(() => {
    const latest =
      historyPage === 1 ? history.data?.messages.at(-1) : undefined;
    if (latest && !active) setActive(latest.task_id);
  }, [history.data, active, historyPage]);
  useEffect(() => {
    if (task && terminal(task.status))
      void queryClient.invalidateQueries({
        queryKey: ["conversation", conversation],
      });
  }, [task?.status, conversation]);
  const send = async (text = message) => {
    if (
      busy ||
      !conversation ||
      !text.trim() ||
      (task && !terminal(task.status))
    )
      return;
    setBusy(true);
    setError("");
    setTopicMessage("");
    const payload = {
      message: text,
      code,
      language,
      submission_id: submissionId ? Number(submissionId) : null,
    };
    const hash = JSON.stringify(payload);
    if (pending.current?.hash !== hash)
      pending.current = { hash, key: crypto.randomUUID() };
    try {
      const r = await api<{ task_id: string }>(
        `/ai/conversations/${conversation}/messages`,
        {
          ...json("POST", payload),
          headers: { "Idempotency-Key": pending.current.key },
        },
      );
      setActive(r.task_id);
      setMessage("");
      setHistoryPage(1);
      pending.current = undefined;
      await queryClient.invalidateQueries({
        queryKey: ["conversation", conversation],
      });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const newTopic = async () => {
    if (busy || !conversation || (task && !terminal(task.status))) return;
    setBusy(true);
    setError("");
    try {
      const started = await api<{ context_generation: number }>(
        `/ai/conversations/${conversation}/new`,
        json("POST"),
      );
      setActive(undefined);
      setContextGeneration(started.context_generation);
      setHistoryPage(1);
      setProposed(null);
      pending.current = undefined;
      setTopicMessage("已开始新对话，后续回答不会携带此前对话内容。");
      await queryClient.invalidateQueries({
        queryKey: ["conversation", conversation],
      });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const submission = useQuery({
    queryKey: ["submission", submissionId],
    queryFn: () =>
      api<import("../types").Submission>(
        `/submissions/${submissionId}?include_metadata=true`,
      ),
    enabled: !!submissionId,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 1000 : false),
  });
  const answer = task?.result?.text || task?.preview?.text || "";
  const showAnswer = (
    text: string,
    snapshot: string,
    snapshotLanguage?: string,
    request = "",
    status = "completed",
  ) => {
    const suggestion = extractCodeSuggestion(text, code, request);
    return (
      <>
        <div className="ai-answer-card">
          <span className="eyebrow">AI 回答</span>
          <RichText text={text} />
        </div>
        {(snapshot !== code ||
          (snapshotLanguage && snapshotLanguage !== language)) && (
          <p className="version-note">此回答基于较早的代码版本，请勿把旧评测结论直接套用到当前代码。</p>
        )}
        {suggestion && (
          <Button disabled={status !== "completed"} onClick={() => {
            const matchesSnapshot = snapshot === code && snapshotLanguage === language && suggestion.language === language;
            setProposed({ ...suggestion, baseline: code, editorLanguage: language,
              canApply: suggestion.canApply && matchesSnapshot,
              reason: matchesSnapshot ? suggestion.reason : "当前代码或语言与回答快照不同，已禁止覆盖。请基于当前版本重新提问，或复制片段手动合并。",
            });
          }}>
            审查回答中的代码
          </Button>
        )}
      </>
    );
  };
  return (
    <div className="assistant">
      <h3>AI 做题助手</h3>
      <div className="assistant-intro">
        <p className="muted">
          先给提示；每次最多携带当前话题最近 4
          轮。需要完整题解时，可以直接告诉我。
        </p>
        <Button
          disabled={busy || !conversation || (!!task && !terminal(task.status))}
          onClick={() => void newTopic()}
        >
          新对话
        </Button>
      </div>
      <div className="quick-actions">
        {["给我一个渐进提示", "解释我当前的代码", "分析本次评测"].map((t) => (
          <Button
            key={t}
            disabled={busy || (!!task && !terminal(task.status))}
            onClick={() => void send(t)}
          >
            {t}
          </Button>
        ))}
      </div>
      {submission.data && (
        <p className="context-summary">
          评测依据：提交 #{submissionId} ·{" "}
          {submission.data.evaluation?.all_passed
            ? "全部通过"
            : submission.data.status === "pending"
              ? "评测中"
              : "已记录评测结果"}
          {submission.data.evaluation?.total_cases != null &&
            ` · ${submission.data.evaluation.passed_cases ?? "—"} / ${submission.data.evaluation.total_cases} 个测试点通过`}
          {submission.data.code !== code ||
          submission.data.language !== language
            ? "。当前代码或语言已有变化，AI 将区分提交版本与编辑版本。"
            : "，对应当前代码。"}
        </p>
      )}
      {topicMessage && <p role="status">{topicMessage}</p>}
      <form
        className="assistant-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label>
          你的问题
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="例如：为什么边界情况会出错？"
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send();
              }
            }}
          />
        </label>
        <div className="assistant-send-row">
          <p className="muted">
            将附带当前题目、{language} 代码（{code.length} 字符）
            {submissionId ? "和本次评测结果" : ""}。
          </p>
          <Button
            variant="default"
            disabled={
              busy ||
              !conversation ||
              !message.trim() ||
              (!!task && !terminal(task.status))
            }
          >
            {busy ? "发送中…" : "发送"}
          </Button>
        </div>
      </form>
      {error && <ErrorNotice message={error} />}
      <div className="current-answer">
        {task && (
          <section>
            <p className="user-message">{task.requirement}</p>
            <TaskProgress task={task} disconnected={disconnected} />
            {answer
              ? showAnswer(answer, task.code_snapshot || "", task.language, task.requirement, task.status)
              : !terminal(task.status) && (
                  <p className="skeleton">
                    正在组织回答，内容生成后会显示在这里…
                  </p>
                )}
          </section>
        )}
      </div>
      {(history.data?.total || 0) > (active ? 1 : 0) && (
        <details className="assistant-history">
          <summary>
            历史对话（
            {Math.max(0, (history.data?.total || 0) - (active ? 1 : 0))} 轮）
          </summary>
          <div className="messages">
            {history.data?.messages
              .filter((item) => item.task_id !== active)
              .map((item) => (
                <details className="history-turn" key={item.task_id}>
                  <summary>
                    <span>{item.message}</span>
                    <small>
                      {item.language || "代码快照"}
                      {item.submission_id
                        ? ` · 提交 #${item.submission_id}`
                        : ""}
                    </small>
                  </summary>
                  <div className="history-answer">
                    {showAnswer(item.text, item.code_snapshot, item.language, item.message, item.status)}
                  </div>
                </details>
              ))}
          </div>
          {(history.data?.total || 0) > 5 && (
            <Pagination
              page={historyPage}
              totalPages={Math.ceil((history.data?.total || 0) / 5)}
              label="AI 历史对话分页"
              onChange={setHistoryPage}
            />
          )}
        </details>
      )}
      {proposed && (
        <section className="code-review-card">
          <div className="section-heading">
            <div><span className="eyebrow">代码审查</span><h3>应用前检查修改</h3></div>
          </div>
          <p className={proposed.canApply ? "status-good" : "notice-inline"}>{proposed.reason}</p>
          <DiffView before={{ code: proposed.baseline }} after={{ code: proposed.code }} />
          {(code !== proposed.baseline || language !== proposed.editorLanguage) && <p className="notice-inline">审查打开后代码或语言已改变。请关闭并重新审查，当前内容不会被覆盖。</p>}
          <div className="review-actions">
            {proposed.canApply && (
              <Button
                variant="default"
                disabled={code !== proposed.baseline || language !== proposed.editorLanguage}
                onClick={() => {
                  if (code !== proposed.baseline || language !== proposed.editorLanguage) return;
                  setApplied({ before: code, after: proposed.code, language });
                  onApply(proposed.code);
                  setProposed(null);
                }}
              >
                应用完整代码
              </Button>
            )}
            <Button onClick={async () => {
              try { await navigator.clipboard.writeText(proposed.code); setCopyMessage("建议代码已复制。"); }
              catch { setCopyMessage("复制失败，请在差异区选中并手动复制代码。"); }
            }}>复制建议代码</Button>
            <Button onClick={() => setProposed(null)}>关闭审查</Button>
          </div>
        </section>
      )}
      {copyMessage && <p role="status">{copyMessage}</p>}
      {applied && <div className="notice"><p>AI 建议已应用，原代码仍保留，可撤销本次替换。</p><Button disabled={code !== applied.after || language !== applied.language} onClick={() => { onApply(applied.before); setApplied(null); }}>撤销 AI 替换</Button>{(code !== applied.after || language !== applied.language) && <p className="muted">代码已继续编辑或语言已切换，为保留新内容，已停用撤销。</p>}</div>}
    </div>
  );
}

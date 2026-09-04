import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, json, errorText, queryClient } from "../api";
import { RichText, Code } from "./Markdown";
import { Button } from "./ui/button";
import { Pagination } from "./Pagination";
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
      {(task.error || error) && <p role="alert">{task.error || error}</p>}
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
    [proposed, setProposed] = useState(""),
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
      setProposed("");
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
  ) => {
    const matches = [
      ...text.matchAll(/```(?:python|cpp|c\+\+|c)?\s*\n([\s\S]*?)```/g),
    ];
    return (
      <>
        <RichText text={text} />
        {(snapshot !== code ||
          (snapshotLanguage && snapshotLanguage !== language)) && (
          <p className="muted">此回答基于较早的代码版本。</p>
        )}
        {matches.length > 0 && (
          <Button onClick={() => setProposed(matches[matches.length - 1][1])}>
            查看建议代码并比较
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
      {error && <p role="alert">{error}</p>}
      <div className="current-answer">
        {task && (
          <section>
            <p className="user-message">{task.requirement}</p>
            <TaskProgress task={task} disconnected={disconnected} />
            {answer
              ? showAnswer(answer, task.code_snapshot || "", task.language)
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
                    {showAnswer(item.text, item.code_snapshot, item.language)}
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
        <div className="notice">
          <h4>应用前比较</h4>
          <div className="samples">
            <div>
              <h4>当前代码</h4>
              <Code text={code} />
            </div>
            <div>
              <h4>建议代码</h4>
              <Code text={proposed} />
            </div>
          </div>
          <Button
            variant="default"
            onClick={() => {
              onApply(proposed);
              setProposed("");
            }}
          >
            应用到编辑器
          </Button>
          <Button onClick={() => setProposed("")}>取消</Button>
        </div>
      )}
    </div>
  );
}

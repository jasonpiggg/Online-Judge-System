import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, json, errorText, queryClient } from "../api";
import { RichText, Code } from "./Markdown";
import { Button } from "./ui/button";
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
};
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
    [active, setActive] = useState<string>(),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [proposed, setProposed] = useState("");
  const pending = useRef<{ hash: string; key: string } | undefined>(undefined);
  const { data: task, disconnected } = useTask(active);
  const history = useQuery({
    queryKey: ["conversation", conversation],
    queryFn: () => api<Message[]>(`/ai/conversations/${conversation}/messages`),
    enabled: !!conversation,
  });
  useEffect(() => {
    let gone = false;
    api<{ id: string }>(
      "/ai/conversations/",
      json("POST", { problem_id: problemId }),
    )
      .then((r) => {
        if (!gone) setConversation(r.id);
      })
      .catch((e) => setError(errorText(e)));
    return () => {
      gone = true;
    };
  }, [problemId]);
  useEffect(() => {
    const running = history.data?.find((m) => !terminal(m.status));
    if (running && !active) setActive(running.task_id);
  }, [history.data, active]);
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
  const answer = task?.result?.text || task?.preview?.text || "";
  const showAnswer = (text: string, snapshot: string) => {
    const matches = [
      ...text.matchAll(/```(?:python|cpp|c\+\+|c)?\s*\n([\s\S]*?)```/g),
    ];
    return (
      <>
        <RichText text={text} />
        {snapshot !== code && (
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
      <p className="muted">先给提示。需要完整题解时，可以直接告诉我。</p>
      <div className="quick-actions">
        {["给我一个渐进提示", "解释我当前的代码", "分析本次提交的问题"].map(
          (t) => (
            <Button
              key={t}
              disabled={busy || (!!task && !terminal(task.status))}
              onClick={() => void send(t)}
            >
              {t}
            </Button>
          ),
        )}
      </div>
      <div className="messages">
        {history.data
          ?.filter((m) => m.task_id !== active)
          .map((m) => (
            <section key={m.task_id}>
              <p className="user-message">{m.message}</p>
              {showAnswer(m.text, m.code_snapshot)}
            </section>
          ))}
        {task && (
          <section>
            <p className="user-message">{task.requirement}</p>
            <TaskProgress task={task} disconnected={disconnected} />
            {answer
              ? showAnswer(answer, task.code_snapshot || "")
              : !terminal(task.status) && (
                  <p className="skeleton">
                    正在组织回答，内容生成后会显示在这里…
                  </p>
                )}
          </section>
        )}
      </div>
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
      <form
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
        <p className="muted">
          将附带当前题目、{language} 代码（{code.length} 字符）
          {submissionId ? "和本次评测结果" : ""}。
        </p>
        {error && <p role="alert">{error}</p>}
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
      </form>
    </div>
  );
}

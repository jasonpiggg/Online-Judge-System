import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api, json, errorText, queryClient } from "../api";
import type { Problem, User, Submission } from "../types";
import { Statement } from "../components/Statement";
import { CodeEditor } from "../components/Editor";
import { Code, logText } from "../components/Markdown";
import { Button } from "../components/ui/button";
import { Assistant } from "../components/AI";
import { readBackup, writeBackup, clearBackup } from "../draft-backup";
export function Result({ id }: { id: string }) {
  const { data, error } = useQuery({
    queryKey: ["submission", id],
    queryFn: () => api<Submission>(`/submissions/${id}?include_metadata=true`),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 1000 : false),
  });
  useEffect(() => {
    if (data && data.status !== "pending") {
      void queryClient.invalidateQueries({ queryKey: ["problems"] });
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    }
  }, [data?.status]);
  return (
    <section className="result">
      <h3>评测结果</h3>
      {error ? (
        <p role="alert">{error.message}</p>
      ) : !data || data.status === "pending" ? (
        <p role="status">正在评测…</p>
      ) : (
        <>
          <strong
            className={
              data.score === data.counts && data.status === "success"
                ? "success"
                : "failure"
            }
          >
            {data.status === "error"
              ? "评测错误"
              : data.score === data.counts
                ? "全部通过"
                : `通过 ${data.score} / ${data.counts}`}
          </strong>
          {["compile_info", "run_info", "error_info"].map((k) =>
            data[k as keyof Submission] ? (
              <Code key={k} text={logText(data[k as keyof Submission])} />
            ) : null,
          )}
          <p>
            <Link to={`/submissions/${id}`}>查看提交详情 →</Link>
          </p>
        </>
      )}
    </section>
  );
}
export function Workspace({ user }: { user: User }) {
  const { id = "" } = useParams();
  const { data: p, error } = useQuery({
    queryKey: ["problem", id],
    queryFn: () => api<Problem>(`/problems/${id}`),
  });
  return error ? (
    <p role="alert">{error.message}</p>
  ) : p ? (
    <Work key={id} problem={p} user={user} />
  ) : (
    <div className="skeleton">正在打开题目…</div>
  );
}
function Work({ problem: p, user }: { problem: Problem; user: User }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const state = location.state as {
    listSearch?: string;
    ids?: string[];
  } | null;
  const [language, setLanguage] = useState(
    localStorage.getItem("oj-language") || "python",
  );
  const [size, setSize] = useState(16);
  const [code, setCode] = useState("");
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState<{
    code: string;
    revision: number;
  } | null>(null);
  const revision = useRef(0);
  const synced = useRef("");
  const latest = useRef(code);
  latest.current = code;
  const generation = useRef(0);
  const loadedBackup = useRef("");
  const inFlight = useRef(false);
  const [saveTick, setSaveTick] = useState(0);
  const submitting = useRef(false);
  const [ratio, setRatio] = useState(48);
  const split = useRef<HTMLDivElement>(null);
  const backup = `oj-draft-${user.user_id}-${p.id}-${language}`;
  const tab = params.get("tab") || "题目";
  const submission = params.get("submission");
  const index = state?.ids?.indexOf(p.id) ?? -1;
  const languages = useQuery({
    queryKey: ["languages"],
    queryFn: () => api<{ name: string[] }>("/languages/"),
  });
  useEffect(() => {
    generation.current += 1;
    let cancelled = false;
    setReady(false);
    setConflict(null);
    api<{ code: string; revision: number } | null>(
      `/workspace-drafts/${p.id}/${language}`,
    )
      .then((d) => {
        if (cancelled) return;
        revision.current = d?.revision || 0;
        synced.current = d?.code || "";
        const saved = readBackup(backup);
        setCode(saved?.code ?? d?.code ?? "");
        if (
          saved &&
          saved.code !== (d?.code || "") &&
          saved.revision !== revision.current
        )
          setConflict({ code: d?.code || "", revision: revision.current });
        loadedBackup.current = backup;
        setReady(true);
      })
      .catch((e) => setError(errorText(e)));
    return () => {
      cancelled = true;
      generation.current += 1;
    };
  }, [p.id, language, backup]);
  useEffect(() => {
    if (!ready || loadedBackup.current !== backup) return;
    try {
      if (code !== synced.current) writeBackup(backup, code, revision.current);
    } catch {
      setError("本机存储空间不足，请下载或复制代码备份。");
    }
    if (code === synced.current) {
      setSaving("已保存");
      return;
    }
    setSaving("等待保存…");
    if (conflict || inFlight.current) return;
    const epoch = generation.current;
    const timer = setTimeout(() => {
      setSaving("正在保存…");
      inFlight.current = true;
      api<{ revision: number; code: string }>(
        `/workspace-drafts/${p.id}/${language}`,
        json("PUT", { code, expected_revision: revision.current }),
      )
        .then((d) => {
          if (generation.current !== epoch) return;
          revision.current = d.revision;
          synced.current = code;
          clearBackup(backup, code);
          setSaving(latest.current === code ? "已保存" : "等待保存…");
        })
        .catch(async (e) => {
          if (generation.current !== epoch) return;
          if (e.status === 409) {
            const remote = await api<{ code: string; revision: number }>(
              `/workspace-drafts/${p.id}/${language}`,
            ).catch(() => null);
            if (remote && generation.current === epoch) setConflict(remote);
          }
          setSaving("已保留本地备份");
          setError(errorText(e));
        })
        .finally(() => {
          inFlight.current = false;
          if (generation.current !== epoch || latest.current !== code)
            setSaveTick((v) => v + 1);
        });
    }, 800);
    return () => {
      clearTimeout(timer);
    };
  }, [code, ready, backup, p.id, language, conflict, saveTick]);
  const submit = useCallback(async () => {
    if (submitting.current || !ready || !latest.current.trim()) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      const d = await api<{ submission_id: string }>(
        "/submissions/",
        json("POST", { problem_id: p.id, language, code: latest.current }),
      );
      setParams({
        ...Object.fromEntries(params),
        submission: d.submission_id,
        tab: "结果",
      });
    } catch (e) {
      setError(errorText(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }, [ready, language, p.id, params, setParams]);
  const drag = (e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const move = (event: PointerEvent) => {
      const r = split.current!.getBoundingClientRect();
      setRatio(
        Math.max(30, Math.min(65, ((event.clientX - r.left) / r.width) * 100)),
      );
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  return (
    <div className="workpage">
      <div className="work-nav">
        <Link
          to={"/problems" + (state?.listSearch ? "?" + state.listSearch : "")}
          onClick={() => sessionStorage.setItem("oj-return-library", "1")}
        >
          ← 题库
        </Link>
        <div>
          {index > 0 && (
            <Link to={`/problems/${state!.ids![index - 1]}`} state={state}>
              上一题
            </Link>
          )}
          {index >= 0 && index < (state?.ids?.length || 0) - 1 && (
            <Link to={`/problems/${state!.ids![index + 1]}`} state={state}>
              下一题 →
            </Link>
          )}
        </div>
      </div>
      <div className="work-heading">
        <h1>{p.title}</h1>
        <p className="muted">
          {p.id} · {p.difficulty || "未分级"} · {p.time_limit} 秒 ·{" "}
          {p.memory_limit} MB
        </p>
      </div>
      <details className="problem-tools">
        <summary>题目操作</summary>
        <Button
          onClick={async () => {
            try {
              const editable = { ...p };
              const limit_inheritance = p.limit_inheritance;
              delete editable.limit_inheritance;
              delete editable.progress;
              const draft = await api<{ id: string }>(
                "/problem-drafts/",
                json("POST", {
                  base_problem_id: p.id,
                  problem: {
                    ...editable,
                    time_limit: limit_inheritance?.time_limit
                      ? null
                      : p.time_limit,
                    memory_limit: limit_inheritance?.memory_limit
                      ? null
                      : p.memory_limit,
                  },
                }),
              );
              navigate("/authoring/drafts/" + draft.id);
            } catch (e) {
              setError(errorText(e));
            }
          }}
        >
          编辑题目
        </Button>
        {user.role === "admin" && (
          <Button
            onClick={async () => {
              if (
                window.prompt(`删除后无法恢复，请输入题号 ${p.id} 确认`) !==
                p.id
              )
                return;
              try {
                await api(`/problems/${p.id}`, json("DELETE"));
                navigate("/problems");
              } catch (e) {
                setError(errorText(e));
              }
            }}
          >
            删除题目
          </Button>
        )}
      </details>
      <div className="mobile-tabs">
        {["题目", "代码", "结果", "AI"].map((t) => (
          <Button
            key={t}
            variant={tab === t ? "default" : "ghost"}
            onClick={() => setParams({ ...Object.fromEntries(params), tab: t })}
          >
            {t}
          </Button>
        ))}
      </div>
      <div
        className="workspace"
        ref={split}
        style={{
          gridTemplateColumns: `minmax(0,${ratio}fr) 12px minmax(0,${100 - ratio}fr)`,
        }}
      >
        <section
          className={`statement-pane mobile-${tab === "题目" ? "show" : "hide"}`}
        >
          <Statement problem={p} />
        </section>
        <div
          className="resize"
          role="separator"
          aria-label="调整题目与代码宽度"
          aria-valuenow={ratio}
          tabIndex={0}
          onPointerDown={drag}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setRatio(Math.max(30, ratio - 2));
            if (e.key === "ArrowRight") setRatio(Math.min(65, ratio + 2));
          }}
        />
        <section
          className={`editor-pane mobile-${tab !== "题目" ? "show" : "hide"}`}
        >
          <div
            className={`code-area mobile-${tab === "代码" ? "show" : "hide"}`}
          >
            <div className="editor-toolbar">
              <select
                aria-label="编程语言"
                value={language}
                onChange={(e) => {
                  localStorage.setItem("oj-language", e.target.value);
                  setLanguage(e.target.value);
                }}
              >
                {(languages.data?.name || ["python"]).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
              <label className="font-control">
                字号{" "}
                <select
                  aria-label="代码字号"
                  value={size}
                  onChange={(e) => setSize(Number(e.target.value))}
                >
                  {[14, 16, 18, 20, 24].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
            </div>
            {ready ? (
              <CodeEditor
                value={code}
                onChange={setCode}
                language={language}
                size={size}
                onSubmit={() => void submit()}
              />
            ) : (
              <div className="skeleton">读取草稿…</div>
            )}
            <div className="editor-footer">
              <span className="muted" role="status">
                {saving}
              </span>
              <Button
                variant="default"
                disabled={busy || !ready || !code.trim()}
                onClick={() => void submit()}
              >
                {busy ? "提交中…" : "提交评测"}
              </Button>
            </div>
          </div>
          {error && (
            <p role="alert">
              {error}{" "}
              {!conflict && ready && (
                <Button
                  onClick={() => {
                    setError("");
                    setSaveTick((v) => v + 1);
                  }}
                >
                  重试保存
                </Button>
              )}
            </p>
          )}
          {conflict && (
            <div className="notice">
              <h3>草稿在其他页面已更新</h3>
              <p>本地代码已保留。选择要继续编辑的版本。</p>
              <h4>本地版本</h4>
              <Code text={code} />
              <h4>云端版本</h4>
              <Code text={conflict.code} />
              <Button
                onClick={() => {
                  sessionStorage.setItem(backup + "-conflict", code);
                  clearBackup(backup, code);
                  revision.current = conflict.revision;
                  synced.current = conflict.code;
                  setCode(conflict.code);
                  setConflict(null);
                  setError("");
                }}
              >
                使用云端版本
              </Button>
              <Button
                onClick={() => {
                  revision.current = conflict.revision;
                  setConflict(null);
                  setError("");
                }}
              >
                保留我的版本并保存
              </Button>
            </div>
          )}
          <div className={`mobile-${tab === "结果" ? "show" : "hide"}`}>
            {submission ? (
              <Result id={submission} />
            ) : (
              <p className="muted empty">提交后，评测结果会显示在这里。</p>
            )}
          </div>
          <details
            className={`assistant-panel mobile-${tab === "AI" ? "show" : "hide"}`}
            open={tab === "AI"}
          >
            <summary>AI 做题助手</summary>
            <Assistant
              problemId={p.id}
              code={code}
              language={language}
              submissionId={submission}
              onApply={setCode}
            />
          </details>
        </section>
      </div>
    </div>
  );
}

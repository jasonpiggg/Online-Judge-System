import { createEditingDraft } from "../problem-actions";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api, json, errorText } from "../api";
import type { Problem, User } from "../types";
import { Statement } from "../components/Statement";
import { CodeEditor } from "../components/Editor";
import { Code } from "../components/Markdown";
import { Button } from "../components/ui/button";
import { Assistant } from "../components/AI";
import { ResultPanel } from "../components/Evaluation";
import { Icon } from "../components/Icon";
import { readBackup, writeBackup, clearBackup } from "../draft-backup";
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
  const [size, setSize] = useState(14);
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
  const assistantPanel = useRef<HTMLDetailsElement>(null);
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
  const jump = useCallback((target: string) => {
    if (target === "AI" && assistantPanel.current)
      assistantPanel.current.open = true;
    document
      .getElementById(`section-${target}`)
      ?.scrollIntoView({ block: "start", behavior: "instant" });
  }, []);
  useEffect(() => {
    if (params.get("tab")) requestAnimationFrame(() => jump(tab));
  }, [tab, submission, jump, params]);
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
      <div className="work-heading-row">
        <div className="work-heading">
          <span className="eyebrow">
            <Icon name="book" /> 编程练习
          </span>
          <h1>{p.title}</h1>
          <p className="muted">
            {p.id} · <DifficultyBadge value={p.difficulty} /> · {p.time_limit}{" "}
            秒 · {p.memory_limit} MB
          </p>
        </div>
        <div className="problem-actions" aria-label="题目操作">
          <Button
            onClick={async () => {
              try {
                const draft = await createEditingDraft(p);
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
              variant="destructive"
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
        </div>
      </div>
      <nav className="section-nav" aria-label="做题快捷跳转">
        {["题目", "代码", "结果", "AI"].map((t) => (
          <Button
            key={t}
            variant={tab === t ? "default" : "ghost"}
            onClick={() => {
              setParams(
                { ...Object.fromEntries(params), tab: t },
                { replace: true },
              );
              jump(t);
            }}
          >
            <Icon
              name={
                t === "题目"
                  ? "book"
                  : t === "代码"
                    ? "code"
                    : t === "结果"
                      ? "chart"
                      : "spark"
              }
            />
            {t === "题目" ? "题面" : t}
          </Button>
        ))}
      </nav>
      <div className="workspace">
        <section id="section-题目" className="statement-pane surface">
          <Statement problem={p} />
        </section>
        <section className="editor-pane">
          <div id="section-代码" className="code-area surface">
            <div className="section-title">
              <Icon name="code" />
              <h2>编写代码</h2>
              <span className="muted">Ctrl / ⌘ + Enter 提交</span>
            </div>
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
          <div id="section-结果" className="surface result-surface">
            {submission ? (
              <ResultPanel id={submission} />
            ) : (
              <p className="muted empty">提交后，评测结果会显示在这里。</p>
            )}
          </div>
          <details
            id="section-AI"
            ref={assistantPanel}
            className="assistant-panel surface"
          >
            <summary>
              <Icon name="spark" /> AI 做题助手
              <span className="muted">提示、解释与评测分析</span>
            </summary>
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
import { DifficultyBadge } from "../components/Difficulty";

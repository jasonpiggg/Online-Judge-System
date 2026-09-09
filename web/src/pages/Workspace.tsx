import { localTime } from "../datetime";
import { useLanguages } from "../languages";
import { CodeImport } from "../components/CodeImport";
import { editingDraftPath } from "../problem-actions";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api, json, errorText, queryClient } from "../api";
import type { Problem, Submission, User } from "../types";
import { Statement } from "../components/Statement";
import { CodeEditor } from "../components/Editor";
import { Code } from "../components/Markdown";
import { Button } from "../components/ui/button";
import { Assistant } from "../components/AI";
import { ResultPanel, VerdictBadge } from "../components/Evaluation";
import { Icon } from "../components/Icon";
import { readBackup, writeBackup, clearBackup } from "../draft-backup";
import { BackLink } from "../components/BackLink";
import {
  TaskAction,
  TaskLink,
  useActivity,
  useRecoverUnavailableTask,
  useRegisterActivity,
} from "../components/Activity";
import { ErrorNotice } from "../components/ErrorNotice";
import { Pagination } from "../components/Pagination";
export const DEFAULT_EDITOR_FONT_SIZE = 14;
export function Workspace({ user }: { user: User }) {
  const { id = "" } = useParams();
  const { data: p, error } = useQuery({
    queryKey: ["problem", id],
    queryFn: () => api<Problem>(`/problems/${id}`),
  });
  useRecoverUnavailableTask(error);
  return error ? (
    <ErrorNotice title="题目暂时无法打开" message={error.message} />
  ) : p ? (
    <Work key={id} problem={p} user={user} />
  ) : (
    <div className="skeleton">正在打开题目…</div>
  );
}
function Work({ problem: p, user }: { problem: Problem; user: User }) {
  const navigate = useNavigate();
  const {
    activeSlot,
    replaceCurrent,
    findEditingDraft,
    remove: removeActivity,
  } = useActivity();
  const location = useLocation();
  const [params] = useSearchParams();
  const state = location.state as {
    listSearch?: string;
    ids?: string[];
  } | null;
  const [language, setLanguage] = useState(
    localStorage.getItem("oj-language") || "python",
  );
  const [size, setSize] = useState(DEFAULT_EDITOR_FONT_SIZE);
  const [code, setCode] = useState("");
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [backupFailed, setBackupFailed] = useState(false);
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
  const [historyPage, setHistoryPage] = useState(1);
  const submitting = useRef(false);
  const assistantPanel = useRef<HTMLDetailsElement>(null);
  const backup = `oj-draft-${user.user_id}-${p.id}-${language}`;
  const sections = ["题目", "代码", "结果", "AI"] as const;
  type Section = (typeof sections)[number];
  const scrollTarget = useRef<Section | null>(null);
  const passiveNavigation = useRef("");
  const manualScroll = useRef(false);
  const restoredSlot = useRef<string | undefined>(undefined);
  const requestedTab = params.get("tab");
  const tab: Section = sections.includes(requestedTab as Section)
    ? (requestedTab as Section)
    : "题目";
  const submission = params.get("submission");
  const index = state?.ids?.indexOf(p.id) ?? -1;
  const languages = useLanguages();
  const history = useQuery({
    queryKey: ["problem-submissions", p.id, user.user_id, historyPage],
    queryFn: () =>
      api<{ total: number; submissions: Submission[] }>(
        `/submissions/?${new URLSearchParams({
          problem_id: p.id,
          user_id: String(user.user_id),
          page: String(historyPage),
          page_size: "10",
          include_metadata: "true",
        })}`,
      ),
    refetchInterval: (query) =>
      query.state.data?.submissions.some((item) => item.status === "pending")
        ? 2000
        : false,
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
      .catch((e) => {
        if (!cancelled) setError(errorText(e));
      });
    return () => {
      cancelled = true;
      generation.current += 1;
    };
  }, [p.id, language, backup]);
  useEffect(() => {
    if (!ready || loadedBackup.current !== backup) return;
    try {
      if (code !== synced.current) writeBackup(backup, code, revision.current);
      setBackupFailed(false);
    } catch {
      setBackupFailed(true);
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
  useRegisterActivity({
    id: `problem:${p.id}`,
    kind: "problem",
    title: `${p.id} · ${p.title}`,
    path: `/problems/${p.id}${location.search}`,
    status: busy ? "提交中" : saving || "编辑中",
    unsafeToClose: backupFailed || !!conflict,
    closeMessage: conflict
      ? "代码草稿存在尚未解决的版本冲突，确认关闭任务入口？内容仍会保留。"
      : "本机代码备份失败，请先复制代码。仍要关闭任务入口吗？",
  });
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
      setHistoryPage(1);
      await queryClient.invalidateQueries({
        queryKey: ["problem-submissions", p.id, user.user_id],
      });
      const next = new URLSearchParams(params);
      next.set("submission", d.submission_id);
      next.set("tab", "结果");
      scrollTarget.current = "结果";
      replaceCurrent(`${location.pathname}?${next}`, location.state as object);
    } catch (e) {
      setError(errorText(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }, [
    ready,
    language,
    p.id,
    params,
    replaceCurrent,
    location.pathname,
    location.state,
    user.user_id,
  ]);
  useEffect(() => {
    // Keep the requested page while React Query is loading the new query key.
    if (!history.data) return;
    const pages = Math.max(1, Math.ceil(history.data.total / 10));
    if (historyPage > pages) setHistoryPage(pages);
  }, [history.data?.total, historyPage]);
  const jump = useCallback((target: Section, smooth = false) => {
    manualScroll.current = false;
    scrollTarget.current = target;
    if (target === "AI" && assistantPanel.current)
      assistantPanel.current.open = true;
    const nav = document.querySelector(".section-nav")?.getBoundingClientRect();
    const node = document.getElementById(`section-${target}`);
    if (node)
      node.style.scrollMarginTop = `${Math.max(0, nav?.bottom || 0) + 16}px`;
    document.getElementById(`section-${target}`)?.scrollIntoView({
      block: "start",
      behavior:
        smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "smooth"
          : "auto",
    });
  }, []);
  useLayoutEffect(() => {
    if (!activeSlot) return;
    const path = location.pathname + location.search;
    if (passiveNavigation.current === path) {
      passiveNavigation.current = "";
      return;
    }
    if (restoredSlot.current !== activeSlot.id) {
      restoredSlot.current = activeSlot.id;
      if (tab === "AI" && assistantPanel.current)
        assistantPanel.current.open = true;
      const saved = activeSlot.current.scrollY;
      if (typeof saved === "number" && Number.isFinite(saved)) {
        window.scrollTo({ top: saved, behavior: "instant" });
        return;
      }
    }
    jump(tab);
  }, [activeSlot?.id, location.key, p.id]);
  useEffect(() => {
    if (!activeSlot) return;
    let frame = 0;
    const cancelJump = () => {
      manualScroll.current = true;
      if (scrollTarget.current)
        window.scrollTo({ top: window.scrollY, behavior: "instant" });
      scrollTarget.current = null;
    };
    const keyboard = (event: KeyboardEvent) => {
      if (
        (event.target as HTMLElement)?.closest(
          "input,textarea,select,[contenteditable=true],.monaco-editor",
        )
      )
        return;
      if (
        [
          "ArrowUp",
          "ArrowDown",
          "PageUp",
          "PageDown",
          "Home",
          "End",
          " ",
        ].includes(event.key)
      )
        cancelJump();
    };
    const sync = () => {
      frame = 0;
      if (scrollTarget.current || submitting.current || !manualScroll.current)
        return;
      const nav = document
        .querySelector(".section-nav")
        ?.getBoundingClientRect();
      const threshold = Math.max(0, nav?.bottom || 0) + 24;
      let current: Section = "题目";
      for (const section of sections) {
        const node = document.getElementById(`section-${section}`);
        if (node && node.getBoundingClientRect().top <= threshold)
          current = section;
      }
      // Read the committed browser URL so a delayed scroll frame cannot erase
      // a submission/section navigation that happened after this effect rendered.
      const next = new URLSearchParams(window.location.search);
      if (window.location.pathname !== location.pathname) return;
      if (current !== (next.get("tab") || "题目")) {
        next.set("tab", current);
        const path = `${location.pathname}?${next}`;
        // Updating the address while scrolling must never reposition the viewport.
        passiveNavigation.current = path;
        replaceCurrent(path, location.state as object);
      }
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(sync);
    };
    const scrollEnd = () => {
      scrollTarget.current = null;
    };
    window.addEventListener("wheel", cancelJump, { passive: true });
    window.addEventListener("touchstart", cancelJump, { passive: true });
    window.addEventListener("pointerdown", cancelJump, { passive: true });
    window.addEventListener("keydown", keyboard);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("scrollend", scrollEnd);
    return () => {
      window.removeEventListener("wheel", cancelJump);
      window.removeEventListener("touchstart", cancelJump);
      window.removeEventListener("pointerdown", cancelJump);
      window.removeEventListener("keydown", keyboard);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("scrollend", scrollEnd);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [
    activeSlot?.id,
    location.pathname,
    location.search,
    location.state,
    replaceCurrent,
  ]);
  return (
    <div className="workpage">
      <div className="work-nav">
        <div className="work-back">
          <BackLink />
        </div>
        {index >= 0 && (
          <div className="problem-switcher" aria-label="相邻题目">
            {index > 0 ? (
              <Button asChild size="compact">
                <TaskLink
                  to={`/problems/${state!.ids![index - 1]}`}
                  state={state}
                >
                  <Icon name="chevronLeft" /> 上一题
                </TaskLink>
              </Button>
            ) : (
              <Button size="compact" disabled>
                <Icon name="chevronLeft" /> 上一题
              </Button>
            )}
            {index >= 0 && index < (state?.ids?.length || 0) - 1 ? (
              <Button asChild size="compact">
                <TaskLink
                  to={`/problems/${state!.ids![index + 1]}`}
                  state={state}
                >
                  下一题 <Icon name="chevronRight" />
                </TaskLink>
              </Button>
            ) : (
              <Button size="compact" disabled>
                下一题 <Icon name="chevronRight" />
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="work-heading-row">
        <div className="work-heading">
          <h1>{p.title}</h1>
          <p className="muted">
            {p.id} · <DifficultyBadge value={p.difficulty} /> · {p.time_limit}{" "}
            秒 · {p.memory_limit} MB
          </p>
        </div>
        <details
          className="problem-actions-menu"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.currentTarget.open = false;
              event.currentTarget.querySelector("summary")?.focus();
            }
          }}
        >
          <summary>
            题目操作 <Icon name="chevronDown" />
          </summary>
          <div className="problem-actions" aria-label="题目操作">
            <TaskAction
              label="编辑题目"
              onError={(e) => setError(errorText(e))}
              resolve={() => editingDraftPath(p, findEditingDraft(p.id))}
            />
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
                    removeActivity(`problem:${p.id}`);
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
        </details>
      </div>
      <nav className="section-nav" aria-label="做题快捷跳转">
        {sections.map((t) => (
          <Button
            key={t}
            variant={tab === t ? "default" : "ghost"}
            aria-current={tab === t ? "location" : undefined}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("tab", t);
              passiveNavigation.current = `${location.pathname}?${next}`;
              replaceCurrent(
                passiveNavigation.current,
                location.state as object,
              );
              jump(t, true);
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
                {(languages.data?.name || []).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
              <div className="code-import">
                <CodeImport
                  language={language}
                  disabled={
                    !ready || backupFailed || !!conflict || inFlight.current
                  }
                  onApply={async (target, imported) => {
                    // Persist both source and target backups before changing editor language.
                    // Target loading then reads this backup after establishing its server revision.
                    const epoch = generation.current;
                    const destination = `oj-draft-${user.user_id}-${p.id}-${target}`;
                    const remote = await api<{
                      code: string;
                      revision: number;
                    } | null>(`/workspace-drafts/${p.id}/${target}`);
                    if (generation.current !== epoch)
                      throw new Error("页面或语言已变化，请重新导入。");
                    const existing = readBackup(destination);
                    if (
                      existing &&
                      existing.code !== (remote?.code || "") &&
                      existing.revision !== (remote?.revision || 0)
                    )
                      throw new Error(
                        "目标语言草稿存在版本冲突，请切换到该语言处理后再导入。",
                      );
                    writeBackup(backup, latest.current, revision.current);
                    writeBackup(destination, imported, remote?.revision || 0);
                    if (target === language) {
                      revision.current = remote?.revision || 0;
                      synced.current = remote?.code || "";
                      setCode(imported);
                    } else {
                      setReady(false);
                      localStorage.setItem("oj-language", target);
                      setLanguage(target);
                    }
                  }}
                />
              </div>
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
            <div className="editor-body">
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
          </div>
          {error && (
            <div className="error-recovery">
              <ErrorNotice
                title={conflict ? "代码版本需要选择" : "代码草稿未能同步"}
                message={error}
              />
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
            </div>
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
              <ResultPanel
                id={submission}
                taskLink
                detailFrom={`/problems/${p.id}?${new URLSearchParams({
                  submission,
                  tab: "结果",
                })}`}
              />
            ) : (
              <p className="muted empty">提交后，评测结果会显示在这里。</p>
            )}
            <section
              className="problem-submission-history"
              aria-labelledby="problem-submission-history-title"
            >
              <div className="section-title">
                <Icon name="chart" />
                <h2 id="problem-submission-history-title">本题提交记录</h2>
                {history.data && (
                  <span className="muted">共 {history.data.total} 条</span>
                )}
              </div>
              {history.error ? (
                <ErrorNotice
                  title="提交记录暂时无法读取"
                  message={history.error.message}
                />
              ) : history.isPending ? (
                <p className="skeleton">正在读取本题提交记录…</p>
              ) : history.data?.submissions.length ? (
                <>
                  <div className="submission-history-list">
                    {history.data.submissions.map((item) => {
                      const selected = item.submission_id === submission;
                      const returnTo = `/problems/${p.id}?${new URLSearchParams(
                        {
                          submission: item.submission_id,
                          tab: "结果",
                        },
                      )}`;
                      return (
                        <article
                          className={`submission-history-row${selected ? " selected" : ""}`}
                          key={item.submission_id}
                          aria-current={selected ? "true" : undefined}
                        >
                          <div>
                            <strong>提交 #{item.submission_id}</strong>
                            <span className="muted">
                              {item.language} ·{" "}
                              {localTime(item.created_at)}
                            </span>
                          </div>
                          <VerdictBadge submission={item} />
                          <span className="submission-score">
                            {item.evaluation?.score ?? item.score ?? "—"} /{" "}
                            {item.evaluation?.max_score ?? item.counts ?? "—"}{" "}
                            分
                          </span>
                          <Button asChild size="compact">
                            <TaskLink
                              to={`/submissions/${item.submission_id}?${new URLSearchParams(
                                {
                                  from: returnTo,
                                },
                              )}`}
                            >
                              查看详情 <Icon name="arrow" />
                            </TaskLink>
                          </Button>
                        </article>
                      );
                    })}
                  </div>
                  <Pagination
                    page={historyPage}
                    totalPages={Math.ceil(history.data.total / 10)}
                    label="本题提交记录分页"
                    onChange={setHistoryPage}
                  />
                </>
              ) : (
                <p className="muted empty">
                  还没有提交记录，完成代码后提交第一次评测。
                </p>
              )}
            </section>
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

import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useParams,
  useSearchParams,
  useLocation,
} from "react-router-dom";
import { useState } from "react";
import { api, json, errorText, queryClient } from "../api";
import type { User, Submission } from "../types";
import { Code } from "../components/Markdown";
import { Button } from "../components/ui/button";
import { ResultPanel, VerdictBadge } from "../components/Evaluation";
import { SearchInput } from "../components/SearchInput";
import { Icon } from "../components/Icon";
import { Pagination } from "../components/Pagination";
import { BackLink } from "../components/BackLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { DisclosureCard } from "../components/DisclosureCard";
import { useRegisterActivity } from "../components/Activity";

export function submissionBackPath(
  from: string,
  submission: Submission | undefined,
  isAdmin: boolean,
) {
  if (from.startsWith("/submissions?")) return from;
  if (isAdmin && from.startsWith("/admin?")) return from;
  if (submission && !submission.problem_deleted) {
    const problemPath = `/problems/${submission.problem_id}`;
    if (from === problemPath || from.startsWith(problemPath + "?")) return from;
  }
  return "/submissions";
}

export function Records({
  user,
  adminView = false,
}: {
  user: User;
  adminView?: boolean;
}) {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const isAdmin = adminView && user.role === "admin";
  const Heading = adminView ? "h2" : "h1";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const query = new URLSearchParams({
    page: String(page),
    page_size: "20",
    include_metadata: "true",
  });
  if (isAdmin) {
    query.set("all_users", "true");
    if (params.get("user_id")) query.set("user_id", params.get("user_id")!);
  } else query.set("user_id", String(user.user_id));
  for (const key of ["outcome", "problem_id", "status"])
    if (params.get(key)) query.set(key, params.get(key)!);
  const { data, error, isPending } = useQuery({
    queryKey: ["records", query.toString()],
    queryFn: () =>
      api<{ total: number; submissions: Submission[] }>(
        "/submissions/?" + query,
      ),
    refetchInterval: (q) =>
      q.state.data?.submissions.some((s) => s.status === "pending")
        ? 2000
        : false,
  });
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next, { replace: key === "user_id" || key === "problem_id" });
  };
  const returnTo = location.pathname + location.search;
  return (
    <div className={adminView ? "records-section" : "page"}>
      <div className="page-heading">
        <div>
          <Heading>
            <Icon name="chart" />
            {isAdmin ? "全站提交" : "我的提交"}
          </Heading>
          <p className="muted">
            {isAdmin
              ? "查看用户代码、评测明细，或按用户与题号定位记录。"
              : "每一次尝试，都离答案更近一步。"}
          </p>
        </div>
        {!adminView && user.role === "admin" && (
          <Button asChild>
            <Link to="/admin?tab=提交">
              查看全站提交 <Icon name="arrow" />
            </Link>
          </Button>
        )}
      </div>
      <div className="filters filter-panel">
        {isAdmin && (
          <SearchInput
            label="提交用户 ID"
            navigationKey={location.key}
            placeholder="用户 ID（留空查看全部）"
            value={params.get("user_id") || ""}
            onCommit={(value) => update("user_id", value)}
          />
        )}
        <SearchInput
          label="按题号筛选"
          navigationKey={location.key}
          placeholder="按题号筛选"
          value={params.get("problem_id") || ""}
          onCommit={(value) => update("problem_id", value)}
        />
        <select
          aria-label="提交结果"
          value={params.get("outcome") || ""}
          onChange={(e) => update("outcome", e.target.value)}
        >
          <option value="">全部结果</option>
          <option value="passed">已通过</option>
          <option value="not_passed">未通过</option>
        </select>
        <select
          aria-label="评测状态"
          value={params.get("status") || ""}
          onChange={(e) => update("status", e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="pending">评测中</option>
          <option value="success">评测完成</option>
          <option value="error">系统错误</option>
        </select>
      </div>
      {error && <p role="alert">{error.message}</p>}
      {isPending ? (
        <div className="skeleton">正在读取提交记录…</div>
      ) : (
        data && (
          <>
            <p className="list-summary">
              共 <strong>{data.total}</strong> 条记录
            </p>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>提交编号</th>
                    <th>结果</th>
                    {isAdmin && <th>提交用户</th>}
                    <th>题号</th>
                    <th>语言</th>
                    <th>提交时间</th>
                  </tr>
                </thead>
                <tbody>
                  {data.submissions.map((s) => (
                    <tr key={s.submission_id}>
                      <td>
                        <Link
                          to={`/submissions/${s.submission_id}?${new URLSearchParams({ from: returnTo })}`}
                        >
                          #{s.submission_id}
                        </Link>
                      </td>
                      <td>
                        <Link
                          to={`/submissions/${s.submission_id}?${new URLSearchParams({ from: returnTo })}`}
                        >
                          <VerdictBadge submission={s} />
                        </Link>
                      </td>
                      {isAdmin && (
                        <td>
                          <Link to={`/admin?tab=用户&user_id=${s.user_id}`}>
                            {s.username || `用户 ${s.user_id}`}
                          </Link>
                          <small className="cell-note">ID {s.user_id}</small>
                        </td>
                      )}
                      <td>
                        {s.problem_deleted ? (
                          <span>{s.problem_id} <small className="cell-note">题目已删除</small></span>
                        ) : (
                          <Link to={`/problems/${s.problem_id}`}>{s.problem_id}</Link>
                        )}
                      </td>
                      <td>
                        <span className="language-tag">{s.language}</span>
                      </td>
                      <td className="time-cell">
                        {new Date(s.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.total === 0 && (
              <p className="empty">
                没有匹配的提交记录。
                {!isAdmin && (
                  <Button asChild size="compact">
                    <Link to="/problems">去做一道题 <Icon name="arrow" /></Link>
                  </Button>
                )}
              </p>
            )}
            <Pagination
              page={page}
              totalPages={Math.ceil(data.total / 20)}
              label="提交记录分页"
              onChange={(next) =>
                setParams({
                  ...Object.fromEntries(params),
                  page: String(next),
                })
              }
            />
          </>
        )
      )}
    </div>
  );
}
export function SubmissionPage({ user }: { user: User }) {
  const { id } = useParams();
  const location = useLocation();
  const [params] = useSearchParams();
  const from = params.get("from") || "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { data: s, error: loadError } = useQuery({
    queryKey: ["submission", id],
    queryFn: () => api<Submission>(`/submissions/${id}?include_metadata=true`),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 1000 : false),
  });
  const back = submissionBackPath(from, s, user.role === "admin");
  const backLabel = back.startsWith("/problems/")
    ? "返回原题"
    : back.startsWith("/admin?")
      ? "返回管理提交"
      : "返回提交列表";
  useRegisterActivity({
    id: `submission:${id}`,
    kind: "submission",
    title: `提交 #${id}`,
    path: `/submissions/${id}${location.search}`,
    status: s?.status === "pending" ? "评测中" : s ? "已完成" : "读取中",
  });
  return (
    <div className="page">
      <BackLink to={back}>{backLabel}</BackLink>
      <h1>提交 #{id}</h1>
      {loadError && <ErrorNotice title="无法读取提交详情" message={loadError.message} />}
      {s && (
        <>
          <div className="row">
            <span className="eyebrow">
              <Icon name="chart" /> 提交详情
            </span>
            {!s.problem_deleted && (
              <Button asChild>
                <Link to={`/problems/${s.problem_id}?submission=${id}&tab=代码`}>
                  返回题目继续修改
                </Link>
              </Button>
            )}
          </div>
          <p className="muted">
            题号 {s.problem_id} · {s.username || `用户 ${s.user_id}`} ·{" "}
            {s.language} · {new Date(s.created_at).toLocaleString()}
            {s.problem_deleted ? " · 题目已删除（保留此提交供审计）" : ""}
          </p>
          <ResultPanel id={id!} detailLink={false} />
          <DisclosureCard summary="提交代码" open>
            <Code text={s.code || ""} />
          </DisclosureCard>
          {user.role === "admin" && (
            <Button
              disabled={busy || s.status === "pending" || s.problem_deleted}
              onClick={async () => {
                if (busy) return;
                setBusy(true);
                setError("");
                try {
                  await api(`/submissions/${id}/rejudge`, json("PUT"));
                  await queryClient.invalidateQueries({
                    queryKey: ["submission", id],
                  });
                } catch (e) {
                  setError(errorText(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy ? "正在发起…" : "重新评测"}
            </Button>
          )}
        </>
      )}
      {error && <ErrorNotice message={error} />}
    </div>
  );
}

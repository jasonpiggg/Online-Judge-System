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
export function Records({ user }: { user: User }) {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const query = new URLSearchParams({
    user_id: user.user_id,
    page: String(page),
    page_size: "20",
    include_metadata: "true",
  });
  if (params.get("outcome")) query.set("outcome", params.get("outcome")!);
  if (params.get("problem_id"))
    query.set("problem_id", params.get("problem_id")!);
  const { data, error } = useQuery({
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
  return (
    <div className="page">
      <h1>
        <Icon name="chart" />
        我的提交
      </h1>
      <div className="filters">
        <SearchInput
          label="按题号筛选"
          navigationKey={location.key}
          placeholder="按题号筛选"
          value={params.get("problem_id") || ""}
          onCommit={(value) =>
            setParams(
              {
                ...Object.fromEntries(params),
                problem_id: value,
                page: "1",
              },
              { replace: true },
            )
          }
        />
        <select
          aria-label="提交结果"
          value={params.get("outcome") || ""}
          onChange={(e) =>
            setParams({
              ...Object.fromEntries(params),
              outcome: e.target.value,
              page: "1",
            })
          }
        >
          <option value="">全部结果</option>
          <option value="passed">已通过</option>
          <option value="not_passed">未通过</option>
        </select>
      </div>
      {error && <p role="alert">{error.message}</p>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>结果</th>
              <th>题目</th>
              <th>语言</th>
              <th>提交时间</th>
            </tr>
          </thead>
          <tbody>
            {data?.submissions.map((s) => (
              <tr key={s.submission_id}>
                <td>
                  <Link to={`/submissions/${s.submission_id}`}>
                    <VerdictBadge submission={s} />
                  </Link>
                </td>
                <td>
                  <Link to={`/problems/${s.problem_id}`}>{s.problem_id}</Link>
                </td>
                <td>{s.language}</td>
                <td>{new Date(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data?.total === 0 && (
        <p className="empty">
          还没有提交记录。<Link to="/problems">去做一道题 →</Link>
        </p>
      )}
      <div className="pagination">
        <Button
          disabled={page === 1}
          onClick={() =>
            setParams({ ...Object.fromEntries(params), page: String(page - 1) })
          }
        >
          上一页
        </Button>
        <span>第 {page} 页</span>
        <Button
          disabled={page * 20 >= (data?.total || 0)}
          onClick={() =>
            setParams({ ...Object.fromEntries(params), page: String(page + 1) })
          }
        >
          下一页
        </Button>
      </div>
    </div>
  );
}
export function SubmissionPage({ user }: { user: User }) {
  const { id } = useParams();
  const [error, setError] = useState("");
  const { data: s, error: loadError } = useQuery({
    queryKey: ["submission", id],
    queryFn: () => api<Submission>(`/submissions/${id}?include_metadata=true`),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 1000 : false),
  });
  return (
    <div className="page">
      <Link to="/submissions">← 我的提交</Link>
      <h1>提交 #{id}</h1>
      {loadError && <p role="alert">{loadError.message}</p>}
      {s && (
        <>
          <div className="row">
            <span className="eyebrow">
              <Icon name="chart" /> 提交详情
            </span>
            <Button asChild>
              <Link to={`/problems/${s.problem_id}?submission=${id}&tab=代码`}>
                返回题目继续修改
              </Link>
            </Button>
          </div>
          <p className="muted">
            {s.problem_id} · {s.language} ·{" "}
            {new Date(s.created_at).toLocaleString()}
          </p>
          <ResultPanel id={id!} detailLink={false} />
          <details open>
            <summary>提交代码</summary>
            <Code text={s.code || ""} />
          </details>
          {user.role === "admin" && (
            <Button
              onClick={async () => {
                try {
                  await api(`/submissions/${id}/rejudge`, json("PUT"));
                  await queryClient.invalidateQueries({
                    queryKey: ["submission", id],
                  });
                } catch (e) {
                  setError(errorText(e));
                }
              }}
            >
              重新评测
            </Button>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

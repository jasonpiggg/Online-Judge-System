import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { api, json, queryClient, errorText } from "../api";
import type { Problem } from "../types";
import { Button } from "../components/ui/button";
import { SearchInput } from "../components/SearchInput";
import { DifficultyBadge } from "../components/Difficulty";
import { Pagination } from "../components/Pagination";
import { Statement } from "../components/Statement";
import { Code } from "../components/Markdown";
import { createEditingDraft } from "../problem-actions";
import { useActionReveal } from "../components/useActionReveal";
import { DisclosureCard } from "../components/DisclosureCard";

export function AdminProblems({ adminView = false }: { adminView?: boolean }) {
  const [params, setParams] = useSearchParams();
  const location = useLocation(),
    navigate = useNavigate();
  const id = params.get("problem_id"),
    q = params.get("q") || "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [visibility, setVisibility] = useState<{
    id: string;
    value: boolean;
  } | null>(null);
  const detailReveal = useActionReveal<HTMLElement>();
  const problems = useQuery({
    queryKey: ["admin-problems"],
    queryFn: () => api<Problem[]>("/problems/?include_metadata=true"),
  });
  const detail = useQuery({
    queryKey: ["admin-problem", id],
    queryFn: () => api<Problem>(`/problems/${id}`),
    enabled: !!id,
  });
  const filtered = problems.data?.filter((p) =>
    `${p.id} ${p.title} ${p.tags.join(" ")}`
      .toLowerCase()
      .includes(q.toLowerCase()),
  );
  const p = detail.data;
  const action = async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
      await queryClient.invalidateQueries();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section>
      <div className="section-heading">
        <div>
          <h2>{adminView ? "题目管理" : "题目资源"}</h2>
          <p className="muted">
            按题号定位，查看完整信息并{adminView ? "管理" : "编辑"}题目。
          </p>
        </div>
        <Button asChild>
          <Link to="/authoring">创建题目</Link>
        </Button>
      </div>
      <SearchInput
        label="管理题目搜索"
        placeholder="搜索题号、标题或标签"
        navigationKey={location.key}
        value={q}
        onCommit={(value) =>
          setParams({ tab: "题目", q: value }, { replace: true })
        }
      />
      {(error || problems.error || detail.error) && (
        <p role="alert">
          {error || problems.error?.message || detail.error?.message}
        </p>
      )}
      {problems.isPending ? (
        <p className="skeleton">正在加载题库…</p>
      ) : (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>题号</th>
                  <th>标题</th>
                  <th>难度</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered?.slice((page - 1) * 20, page * 20).map((problem) => (
                  <tr
                    key={problem.id}
                    className={id === problem.id ? "selected-row" : ""}
                  >
                    <td className="identifier">{problem.id}</td>
                    <td className="wrap-cell">{problem.title}</td>
                    <td>
                      <DifficultyBadge value={problem.difficulty} />
                    </td>
                    <td>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setError("");
                          detailReveal.reveal();
                          setParams({
                            ...Object.fromEntries(params),
                            problem_id: problem.id,
                          });
                        }}
                      >
                        查看详情
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!filtered?.length && <p className="empty">没有匹配的题目。</p>}
          <Pagination
            page={page}
            totalPages={Math.ceil((filtered?.length || 0) / 20)}
            label="题目管理分页"
            onChange={(next) =>
              setParams({
                ...Object.fromEntries(params),
                page: String(next),
              })
            }
          />
        </>
      )}
      {id && detail.isPending && <p className="skeleton">正在读取题目详情…</p>}
      {p && (
        <section ref={detailReveal.ref} className="admin-detail reveal-target" aria-label="题目详细信息">
          <div className="section-heading">
            <div>
              <span className="eyebrow">题目详情</span>
              <h2>{p.title}</h2>
            </div>
            <DifficultyBadge value={p.difficulty} />
          </div>
          <dl className="metadata-grid">
            <div>
              <dt>题号</dt>
              <dd>{p.id}</dd>
            </div>
            <div>
              <dt>作者</dt>
              <dd>{p.author || "未填写"}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>{p.source || "未填写"}</dd>
            </div>
            <div>
              <dt>时间限制</dt>
              <dd>
                {p.time_limit} 秒
                {p.limit_inheritance?.time_limit && "（继承语言默认值）"}
              </dd>
            </div>
            <div>
              <dt>内存限制</dt>
              <dd>
                {p.memory_limit} MB
                {p.limit_inheritance?.memory_limit && "（继承语言默认值）"}
              </dd>
            </div>
            <div>
              <dt>样例 / 测试点</dt>
              <dd>
                {p.samples.length} / {p.testcases.length}
              </dd>
            </div>
          </dl>
          <div className="action-group">
            <Button asChild>
              <Link to={`/problems/${p.id}`}>打开做题页</Link>
            </Button>
            <Button
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  const draft = await createEditingDraft(p);
                  navigate(`/authoring/drafts/${draft.id}`);
                })
              }
            >
              编辑题目
            </Button>
            <Button asChild>
              <Link
                to={
                  adminView
                    ? `/admin?tab=提交&problem_id=${p.id}`
                    : `/submissions?problem_id=${p.id}`
                }
              >
                {adminView ? "查看该题全部提交" : "查看我的提交"}
              </Link>
            </Button>
            {adminView && (
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => {
                  if (
                    window.prompt(`删除后无法恢复，请输入题号 ${p.id} 确认`) ===
                    p.id
                  )
                    void action(async () => {
                      await api(`/problems/${p.id}`, json("DELETE"));
                      setParams({ tab: "题目" });
                    });
                }}
              >
                删除题目
              </Button>
            )}
          </div>
          {adminView && (
            <div className="setting-row">
              <div>
                <strong>公开评测日志</strong>
                <p className="muted">
                  允许其他登录用户查看逐点状态、耗时和内存，不公开提交代码。
                </p>
              </div>
              <label className="check">
                <input
                  type="checkbox"
                  checked={
                    visibility?.id === p.id ? visibility.value : p.public_cases
                  }
                  disabled={busy}
                  onChange={(e) => {
                    const checked = e.target.checked;
                    setVisibility({ id: p.id, value: checked });
                    void action(() =>
                      api(
                        `/problems/${p.id}/log_visibility`,
                        json("PUT", { public_cases: checked }),
                      ),
                    ).finally(() => setVisibility(null));
                  }}
                />
                公开日志
              </label>
            </div>
          )}
          <DisclosureCard summary="完整题面与样例">
            <Statement problem={p} />
          </DisclosureCard>
          <DisclosureCard summary={`测试数据（${p.testcases.length} 个）`}>
            {p.testcases.map((c, i) => (
              <DisclosureCard summary={`测试点 ${i + 1}`} key={i}>
                <div className="samples">
                  <div>
                    <h4>输入</h4>
                    <Code text={c.input} />
                  </div>
                  <div>
                    <h4>期望输出</h4>
                    <Code text={c.output} />
                  </div>
                </div>
              </DisclosureCard>
            ))}
          </DisclosureCard>
          <DisclosureCard summary="原始题目 JSON">
            <Code text={JSON.stringify(p, null, 2)} />
          </DisclosureCard>
        </section>
      )}
    </section>
  );
}

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, queryClient } from "../api";
import type { Submission, CaseResult } from "../types";
import { Code, logText } from "./Markdown";
import { Icon } from "./Icon";
import { Button } from "./ui/button";
import { Pagination } from "./Pagination";

const labels: Record<string, string> = {
  AC: "全部通过",
  WA: "答案错误",
  TLE: "运行超时",
  MLE: "内存超限",
  RE: "运行错误",
  CE: "编译失败",
  UNK: "未知结果",
  pending: "正在评测",
  error: "评测系统错误",
  partial: "部分通过",
  failed: "未通过",
  empty: "没有测试点",
  unknown: "结果信息不完整",
};
const tone = (v: string) => (Object.hasOwn(labels, v) ? v : "unknown");
const icon = (v: string) =>
  v === "AC"
    ? "check"
    : ["pending", "TLE", "MLE"].includes(v)
      ? "clock"
      : "cross";
const advice: Record<string, string> = {
  WA: "程序正常运行，但输出与标准答案不同。优先检查边界条件、输入解析和输出格式。",
  TLE: "程序超过时间限制。检查循环终止条件，并考虑降低算法时间复杂度。",
  MLE: "程序使用内存过多。检查大型数组、递归深度和是否保存了不必要的数据。",
  RE: "程序运行时异常。检查数组下标、除零、空输入和递归深度；展开日志查看异常位置。",
  CE: "代码未能编译。根据下方诊断定位首个错误，修正语法、类型或缺失依赖后重新提交。",
  UNK: "评测器无法识别本次异常。保留代码并重试，持续出现时联系管理员查看服务状态。",
  error: "评测服务没有完成本次任务。代码已保留，可以稍后重新提交或请管理员重新评测。",
};
export function VerdictBadge({ submission: s }: { submission: Submission }) {
  const v =
    s.evaluation?.verdict ||
    (s.status === "pending"
      ? "pending"
      : s.status === "error"
        ? "error"
        : "unknown");
  return (
    <span className={`badge tone-${tone(v)}`}>
      <Icon name={icon(v)} />
      <span>{labels[v] || "未知结果"}</span>
    </span>
  );
}
export function EvaluationView({
  submission: s,
  cases,
  caseError,
}: {
  submission: Submission;
  cases?: CaseResult[];
  caseError?: string;
}) {
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const e = s.evaluation;
  const compiled = e?.verdict === "CE";
  const available = compiled ? [] : cases?.filter((c) => c.result !== "CE");
  const filtered = available?.filter((c) => !onlyFailed || c.result !== "AC");
  const pages = Math.max(1, Math.ceil((filtered?.length || 0) / 50));
  const current = Math.min(page, pages);
  const chosen = available?.find((c) => c.id === selected);
  const ratio =
    e && e.total_cases && e.passed_cases !== null
      ? Math.min(100, (100 * e.passed_cases) / e.total_cases)
      : null;
  return (
    <>
      <div className="evaluation-summary" aria-live="polite">
        <VerdictBadge submission={s} />
        {s.status === "success" && (
          <div className="evaluation-numbers">
            <div>
              <strong>
                {e?.passed_cases ?? "—"}
                <small> / {e?.total_cases ?? "—"}</small>
              </strong>
              <span>测试点通过</span>
            </div>
            <div>
              <strong>
                {e?.score ?? "—"}
                <small> / {e?.max_score ?? "—"}</small>
              </strong>
              <span>得分</span>
            </div>
          </div>
        )}
        {s.status === "pending" ? (
          <div className="indeterminate" role="status">
            正在编译与运行，请稍候…
          </div>
        ) : (
          ratio !== null && (
            <progress aria-label="测试点通过比例" max="100" value={ratio} />
          )
        )}
      </div>
      {advice[e?.verdict || s.status] && (
        <p className="outcome-advice">{advice[e?.verdict || s.status]}</p>
      )}
      {compiled && (
        <div className="compile-diagnostic">
          <h3>编译诊断</h3>
          <p>代码未能编译，测试点尚未执行。</p>
          <Code text={logText(s.compile_info)} />
        </div>
      )}
      {s.status === "error" && (
        <p role="alert">评测服务未能完成本次运行，请稍后重试。</p>
      )}
      {s.status === "success" && !compiled && (
        <div className="case-section">
          <div className="row">
            <h3>测试点</h3>
            <div className="segmented">
              <Button
                aria-pressed={!onlyFailed}
                onClick={() => {
                  setOnlyFailed(false);
                  setPage(1);
                }}
              >
                全部
              </Button>
              <Button
                aria-pressed={onlyFailed}
                onClick={() => {
                  setOnlyFailed(true);
                  setPage(1);
                }}
              >
                未通过
              </Button>
            </div>
          </div>
          {caseError ? (
            <p role="alert">测试点详情加载失败：{caseError}</p>
          ) : !cases ? (
            <p className="skeleton">读取测试点…</p>
          ) : (
            <>
              <div className="case-grid">
                {filtered?.slice((current - 1) * 50, current * 50).map((c) => (
                  <button
                    key={c.id}
                    className={`case-tile tone-${tone(c.result)}`}
                    aria-pressed={selected === c.id}
                    aria-label={`测试点 ${c.id} ${c.result}`}
                    onClick={() => setSelected(c.id)}
                  >
                    <span className="case-id">#{c.id}</span>
                    <Icon name={icon(c.result)} />
                    <strong>{c.result}</strong>
                    <span>
                      {c.result === "AC"
                        ? "通过"
                        : labels[c.result] || "未知结果"}
                    </span>
                  </button>
                ))}
              </div>
              {!filtered?.length && (
                <p className="empty compact">
                  {onlyFailed
                    ? "没有未通过的测试点。"
                    : "没有可展示的测试点记录。"}
                </p>
              )}
              {pages > 1 && (
                <Pagination
                  page={current}
                  totalPages={pages}
                  label="测试点分页"
                  onChange={setPage}
                />
              )}
            </>
          )}
          {chosen && (
            <div className="case-detail" aria-live="polite">
              <strong>
                测试点 #{chosen.id} · {labels[chosen.result] || "未知结果"}
              </strong>
              <span>耗时 {chosen.time} 秒</span>
              <span>内存 {chosen.memory} MB</span>
            </div>
          )}
        </div>
      )}
      {s.status !== "pending" && (
        <details className="raw-logs">
          <summary>原始运行日志</summary>
          {["compile_info", "run_info", "error_info"].map((k) =>
            s[k as keyof Submission] ? (
              <Code key={k} text={logText(s[k as keyof Submission])} />
            ) : null,
          )}
        </details>
      )}
    </>
  );
}
export function ResultPanel({
  id,
  detailLink = true,
}: {
  id: string;
  detailLink?: boolean;
}) {
  const { data, error } = useQuery({
    queryKey: ["submission", id],
    queryFn: () => api<Submission>(`/submissions/${id}?include_metadata=true`),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 1000 : false),
  });
  const log = useQuery({
    queryKey: ["log", id, data?.status],
    queryFn: () => api<{ details: CaseResult[] }>(`/submissions/${id}/log`),
    enabled: !!data && data.status !== "pending",
    staleTime: 0,
  });
  useEffect(() => {
    if (data && data.status !== "pending")
      for (const key of ["problems", "me", "records"])
        void queryClient.invalidateQueries({ queryKey: [key] });
  }, [data?.status]);
  return (
    <section className="result">
      <div className="section-title">
        <Icon name="chart" />
        <h2>评测结果</h2>
      </div>
      {error ? (
        <p role="alert">{error.message}</p>
      ) : data ? (
        <EvaluationView
          key={id + data.status}
          submission={data}
          cases={log.data?.details}
          caseError={log.error?.message}
        />
      ) : (
        <p className="skeleton">读取评测结果…</p>
      )}
      {detailLink && (
        <Link className="detail-link" to={`/submissions/${id}`}>
          查看提交详情 →
        </Link>
      )}
    </section>
  );
}

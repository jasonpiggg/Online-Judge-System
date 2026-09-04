import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api";
import type { CaseResult, Evaluation, Submission } from "../types";
import { BackLink } from "../components/BackLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { EvaluationView } from "../components/Evaluation";
import { Icon } from "../components/Icon";
import { useRegisterActivity } from "../components/Activity";

type PublicLogResult = { details: CaseResult[]; score: number | null; counts: number | null };

export function PublicLog() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["public-log", id],
    queryFn: () => api<PublicLogResult>(`/submissions/${id}/log`),
  });
  useRegisterActivity({ id: `submission:${id}`, kind: "submission", title: `日志 #${id}`, path: `/logs/submissions/${id}`, status: query.isPending ? "读取中" : query.error ? "不可查看" : "已加载" });
  const data = query.data;
  const counts = data?.details.reduce<Record<string, number>>((all, item) => {
    all[item.result] = (all[item.result] || 0) + 1;
    return all;
  }, {}) || {};
  const total = data?.details.length ?? null;
  const passed = data ? counts.AC || 0 : null;
  const allPassed = !!total && passed === total;
  const verdict = allPassed ? "AC" : data ? (data.details.find((item) => item.result !== "AC")?.result || "unknown") : "unknown";
  const evaluation: Evaluation = {
    status: data ? "success" : "pending",
    verdict,
    score: data?.score ?? null,
    max_score: data?.counts ?? null,
    executed_cases: total,
    passed_cases: passed,
    total_cases: total,
    all_passed: allPassed,
    result_counts: counts,
  };
  const submission: Submission = { submission_id: id, problem_id: "", language: "", status: data ? "success" : "pending", score: data?.score || 0, counts: data?.counts || 0, created_at: "", evaluation };
  return (
    <div className="page public-log-page">
      <BackLink to="/resources?tab=公开日志">返回公开日志查询</BackLink>
      <div className="page-heading"><div><h1><Icon name="chart" />提交 #{id} 的评测日志</h1><p className="muted">此页面只展示服务器允许当前账号查看的测试点状态，不包含提交者源码、输入或标准输出。</p></div></div>
      {query.error ? <ErrorNotice title="无法查看这份评测日志" message={query.error.message} /> : data ? <EvaluationView submission={submission} cases={data.details} /> : <p className="skeleton">正在检查权限并读取日志…</p>}
    </div>
  );
}

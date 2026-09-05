import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../api";
import type { CaseResult, Evaluation, Submission, User } from "../types";
import { BackLink } from "../components/BackLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { EvaluationView } from "../components/Evaluation";
import { Icon } from "../components/Icon";
import { useRegisterActivity } from "../components/Activity";

type PublicLogResult = {
  details: CaseResult[];
  status: string;
  score: number | null;
  counts: number | null;
  can_view_raw_logs: boolean;
  raw_logs?: Pick<Submission, "compile_info" | "run_info" | "error_info">;
};

export function PublicLog({ user }: { user: User }) {
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
  const allPassed = data?.status === "success" && !!total && passed === total;
  const verdict =
    data?.status === "pending"
      ? "pending"
      : data?.status === "error"
        ? "error"
        : allPassed
          ? "AC"
          : data
            ? data.details.find((item) => item.result !== "AC")?.result || "unknown"
            : "unknown";
  const evaluation: Evaluation = {
    status: data?.status || "pending",
    verdict,
    score: data?.score ?? null,
    max_score: data?.counts ?? null,
    executed_cases: total,
    passed_cases: passed,
    total_cases: total,
    all_passed: allPassed,
    result_counts: counts,
  };
  const submission: Submission = {
    submission_id: id,
    problem_id: "",
    language: "",
    status: data?.status || "pending",
    score: data?.score || 0,
    counts: data?.counts || 0,
    created_at: "",
    evaluation,
    ...data?.raw_logs,
  };
  return (
    <div className="page public-log-page">
      <BackLink to={user.role === "admin" ? "/admin?tab=提交" : "/resources?tab=公开日志"}>
        {user.role === "admin" ? "返回管理 → 提交" : "返回资源 → 公开日志"}
      </BackLink>
      <div className="page-heading"><div><h1><Icon name="chart" />提交 #{id} 的评测日志</h1><p className="muted">逐点状态按题目日志策略开放；提交者本人和管理员还可查看原始编译与运行日志。</p></div></div>
      {query.error ? (
        <ErrorNotice title="无法查看这份评测日志" message={query.error.message} />
      ) : data ? (
        <>
          <EvaluationView submission={submission} cases={data.details} />
          {!data.can_view_raw_logs && (
            <p className="permission-note">
              <Icon name="shield" /> 按实验权限，此公开视图不包含源码、隐藏输入、标准输出或原始编译日志。
            </p>
          )}
        </>
      ) : (
        <p className="skeleton">正在检查权限并读取日志…</p>
      )}
    </div>
  );
}

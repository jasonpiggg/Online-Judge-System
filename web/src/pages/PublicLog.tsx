import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import type { CaseResult, Evaluation, Submission, User } from "../types";
import { BackLink } from "../components/BackLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { EvaluationView } from "../components/Evaluation";
import { Icon } from "../components/Icon";
import { useRecoverUnavailableTask, useRegisterActivity } from "../components/Activity";

type PublicLogResult = {
  details: CaseResult[];
  score: number | null;
  counts: number | null;
};

export function PublicLog({ user: _user }: { user: User }) {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["public-log", id],
    queryFn: () => api<PublicLogResult>(`/submissions/${id}/log`),
  });
  useRecoverUnavailableTask(query.error);
  useRegisterActivity({ id: `submission:${id}`, kind: "submission", title: `日志 #${id}`, path: `/logs/submissions/${id}`, status: query.isPending ? "读取中" : query.error ? "不可查看" : "已加载" });
  const data = query.data;
  const counts = data?.details.reduce<Record<string, number>>((all, item) => {
    all[item.result] = (all[item.result] || 0) + 1;
    return all;
  }, {}) || {};
  const total = data?.details.length ?? null;
  const passed = data ? counts.AC || 0 : null;
  const complete = data?.score != null;
  const allPassed = complete && !!total && passed === total;
  const verdict =
    !complete
      ? "pending"
      : allPassed
          ? "AC"
          : data
            ? data.details.find((item) => item.result !== "AC")?.result || "unknown"
            : "unknown";
  const evaluation: Evaluation = {
    status: complete ? "success" : "pending",
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
    status: complete ? "success" : "pending",
    score: data?.score || 0,
    counts: data?.counts || 0,
    created_at: "",
    evaluation,
  };
  const unavailable = query.error instanceof ApiError ? query.error.status : 0;
  return (
    <div className="page public-log-page">
      <BackLink />
      <div className="page-heading"><div><h1><Icon name="chart" />提交 #{id} 的评测日志</h1><p className="muted">课程评测日志只展示逐测试点结果、时间、内存与总分；编译、运行或任务错误请从有权限的提交详情查看。</p></div></div>
      {query.error ? (
        <>
          <ErrorNotice
            title={unavailable === 403 ? "这份日志当前不可见" : unavailable === 404 ? "没有找到这份提交" : "无法查看这份评测日志"}
            message={query.error.message}
          />
          <p className="permission-note">
            {unavailable === 403
              ? "你只能查看自己的提交；第三方提交需由管理员在题目设置中开启公开日志。"
              : unavailable === 404
                ? "请检查提交编号是否正确。"
                : "评测尚未完成时请稍后重试。"}
          </p>
          <Link to="/submissions">前往我的提交</Link>
        </>
      ) : data ? (
        <>
          <EvaluationView submission={submission} cases={data.details} />
          <p className="permission-note">
            <Icon name="shield" /> 此日志不包含源码、隐藏输入、标准输出、HTTP 响应、后台代码或原始编译诊断。
          </p>
        </>
      ) : (
        <p className="skeleton">正在检查权限并读取日志…</p>
      )}
    </div>
  );
}

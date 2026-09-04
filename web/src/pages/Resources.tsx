import { useSearchParams } from "react-router-dom";
import { AdminProblems } from "./AdminProblems";
import { LanguageSettings } from "../components/LanguageSettings";
import { Button } from "../components/ui/button";
import { Icon } from "../components/Icon";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

export function Resources() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [submissionId, setSubmissionId] = useState("");
  const tab = ["语言", "公开日志"].includes(params.get("tab") || "")
    ? params.get("tab")!
    : "题目";
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1>
            <Icon name="code" />
            资源管理
          </h1>
          <p className="muted">
            查看和维护实验允许普通用户管理的题目与评测语言。
          </p>
        </div>
      </div>
      <div className="step-tabs" aria-label="资源类型">
        {["题目", "语言", "公开日志"].map((value) => (
          <Button
            key={value}
            variant={tab === value ? "default" : "ghost"}
            onClick={() => setParams({ tab: value })}
          >
            {value}
          </Button>
        ))}
      </div>
      {tab === "题目" ? (
        <AdminProblems />
      ) : tab === "语言" ? (
        <LanguageSettings />
      ) : (
        <section className="resource-panel public-log-lookup">
          <div className="section-title"><Icon name="chart" /><h2>查看公开评测日志</h2></div>
          <p>输入已知提交编号。只有本人、管理员或题目已开启公开日志时才能查看测试点明细。</p>
          <form onSubmit={(event) => {
            event.preventDefault();
            if (submissionId.trim()) navigate(`/logs/submissions/${submissionId.trim()}`);
          }}>
            <label>提交编号<input inputMode="numeric" pattern="[0-9]+" value={submissionId} onChange={(event) => setSubmissionId(event.target.value)} placeholder="例如 1024" required /></label>
            <Button variant="default">查看日志</Button>
          </form>
        </section>
      )}
    </div>
  );
}

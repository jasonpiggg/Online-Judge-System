import { useSearchParams } from "react-router-dom";
import { AdminProblems } from "./AdminProblems";
import { LanguageSettings } from "../components/LanguageSettings";
import { Button } from "../components/ui/button";
import { Icon } from "../components/Icon";

export function Resources() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "语言" ? "语言" : "题目";
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
        {["题目", "语言"].map((value) => (
          <Button
            key={value}
            variant={tab === value ? "default" : "ghost"}
            onClick={() => setParams({ tab: value })}
          >
            {value}
          </Button>
        ))}
      </div>
      {tab === "题目" ? <AdminProblems /> : <LanguageSettings />}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { api, errorText, json, queryClient } from "../api";
import { readProblemFile } from "../file-import";
import { useActivity } from "./Activity";
import { Button } from "./ui/button";

export function ProblemImport() {
  const { openRoot } = useActivity();
  const input = useRef<HTMLInputElement>(null);
  const epoch = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(
    () => () => {
      epoch.current++;
    },
    [],
  );
  return (
    <span className="problem-import">
      <input
        ref={input}
        hidden
        type="file"
        accept=".json"
        aria-label="选择题目 JSON"
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          const current = ++epoch.current;
          setBusy(true);
          setError("");
          try {
            const problem = await readProblemFile(file);
            if (current !== epoch.current) return;
            if (typeof problem.id === "string" && problem.id) {
              try {
                await api(`/problems/${encodeURIComponent(problem.id)}`);
                throw new Error(
                  "题号已存在，请修改 JSON 中的 id 后重新导入；现有题目未被修改。",
                );
              } catch (e) {
                if ((e as { status?: number }).status !== 404) throw e;
              }
            }
            if (current !== epoch.current) return;
            const draft = await api<{ id: string }>(
              "/problem-drafts/",
              json("POST", { problem }),
            );
            await queryClient.invalidateQueries({ queryKey: ["drafts"] });
            if (current === epoch.current)
              openRoot(`/authoring/drafts/${draft.id}`);
          } catch (e) {
            if (current === epoch.current) setError(errorText(e));
          } finally {
            if (current === epoch.current) setBusy(false);
          }
        }}
      />
      <Button
        type="button"
        disabled={busy}
        onClick={() => input.current?.click()}
      >
        {busy ? "正在导入…" : "导入 JSON"}
      </Button>
      <Button asChild>
        <a href="/examples/problem.json" download>
          下载示例
        </a>
      </Button>
      {error && (
        <span role="alert" className="field-error">
          {error}
        </span>
      )}
    </span>
  );
}

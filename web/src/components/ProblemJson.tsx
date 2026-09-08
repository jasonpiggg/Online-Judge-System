import { useEffect, useRef, useState } from "react";
import { readProblemFile } from "../file-import";
import { errorText } from "../api";
import { Button } from "./ui/button";
import { Code } from "./Markdown";

export function ProblemJson({
  value,
  onLoad,
}: {
  value: { id: string };
  onLoad: (value: unknown) => void;
}) {
  const [raw, setRaw] = useState("");
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const epoch = useRef(0);
  useEffect(
    () => () => {
      epoch.current++;
    },
    [],
  );
  const serialized = JSON.stringify(value, null, 2);
  return (
    <div className="problem-json">
      <p className="muted">
        导出当前表单内容（含未保存修改）。导入会替换当前表单，保存草稿后生效。
      </p>
      <div className="action-group">
        <Button
          type="button"
          onClick={() => {
            const url = URL.createObjectURL(
              new Blob([serialized + "\n"], {
                type: "application/json;charset=utf-8",
              }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = `${value.id.replace(/[^a-zA-Z0-9_-]/g, "_") || "problem"}.json`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
        >
          下载 JSON
        </Button>
        <Button
          type="button"
          disabled={reading}
          onClick={() => input.current?.click()}
        >
          {reading ? "正在读取…" : "导入本地 JSON"}
        </Button>
        <input
          ref={input}
          hidden
          type="file"
          accept=".json,application/json"
          aria-label="导入当前草稿 JSON"
          onChange={async (event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            const current = ++epoch.current;
            setReading(true);
            setError("");
            try {
              const parsed = await readProblemFile(file);
              if (current === epoch.current) onLoad(parsed);
            } catch (e) {
              if (current === epoch.current) setError(errorText(e));
            } finally {
              if (current === epoch.current) setReading(false);
            }
          }}
        />
      </div>
      <details>
        <summary>查看当前 JSON</summary>
        <Code text={serialized} />
      </details>
      <label>
        或粘贴题目 JSON
        <textarea
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
        />
      </label>
      <Button
        type="button"
        disabled={reading || !raw.trim()}
        onClick={() => {
          setError("");
          try {
            onLoad(JSON.parse(raw.replace(/^\uFEFF/, "")));
          } catch (e) {
            setError(errorText(e));
          }
        }}
      >
        载入 JSON
      </Button>
      {error && (
        <p role="alert" className="field-error">
          {error}
        </p>
      )}
    </div>
  );
}

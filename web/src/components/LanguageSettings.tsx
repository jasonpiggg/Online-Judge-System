import { useState } from "react";
import { api, errorText, json, queryClient } from "../api";
import { Button } from "./ui/button";
import { useQuery } from "@tanstack/react-query";

export function LanguageSettings({ heading = true }: { heading?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const languages = useQuery({
    queryKey: ["language-details"],
    queryFn: () =>
      api<{ languages: Record<string, any>[] }>(
        "/languages/?include_metadata=true",
      ),
  });
  return (
    <section className="language-settings">
      {heading && <h2>评测语言</h2>}
      <p className="muted">
        查看当前执行配置，或登记课程要求的评测语言。注册操作不会安装编译器；请先在服务器预装对应运行环境。已有 gcc 时可通过配置动态加入 C。
      </p>
      {languages.isPending && <p className="skeleton">正在读取语言配置…</p>}
      {languages.error && <p role="alert">{languages.error.message}</p>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>语言</th>
              <th>时间</th>
              <th>内存</th>
              <th>执行配置</th>
            </tr>
          </thead>
          <tbody>
            {languages.data?.languages.map((language) => (
              <tr key={language.name}>
                <td>{language.name}</td>
                <td>{language.time_limit} 秒</td>
                <td>{language.memory_limit} MB</td>
                <td>
                  <details>
                    <summary>查看命令</summary>
                    <dl>
                      <dt>扩展名</dt>
                      <dd>{language.file_ext}</dd>
                      <dt>编译命令</dt>
                      <dd>
                        <code>{language.compile_cmd || "无需编译"}</code>
                      </dd>
                      <dt>运行命令</dt>
                      <dd>
                        <code>{language.run_cmd}</code>
                      </dd>
                    </dl>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>注册语言 / 更新配置</summary>
        <form
          className="form-grid narrow"
          onSubmit={async (event) => {
            event.preventDefault();
            if (busy) return;
            const fields = new FormData(event.currentTarget);
            setBusy(true);
            setMessage("");
            setError("");
            try {
              await api(
                "/languages/",
                json("POST", {
                  name: fields.get("name"),
                  file_ext: fields.get("file_ext"),
                  compile_cmd: fields.get("compile_cmd") || null,
                  run_cmd: fields.get("run_cmd"),
                  time_limit: Number(fields.get("time_limit")),
                  memory_limit: Number(fields.get("memory_limit")),
                }),
              );
              setMessage("语言配置已保存");
              await queryClient.invalidateQueries({
                queryKey: ["language-details"],
              });
            } catch (exception) {
              setError(errorText(exception));
            } finally {
              setBusy(false);
            }
          }}
        >
          {[
            ["name", "语言名称"],
            ["file_ext", "文件扩展名"],
            ["compile_cmd", "编译命令（可留空）"],
            ["run_cmd", "运行命令"],
          ].map(([name, label]) => (
            <label key={name}>
              {label}
              <input name={name} required={name !== "compile_cmd"} />
            </label>
          ))}
          <label>
            时间限制（秒）
            <input
              name="time_limit"
              type="number"
              step="any"
              defaultValue={3}
            />
          </label>
          <label>
            内存限制（MB）
            <input name="memory_limit" type="number" defaultValue={128} />
          </label>
          <Button disabled={busy}>保存语言</Button>
        </form>
      </details>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

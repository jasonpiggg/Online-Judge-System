import { Icon } from "../components/Icon";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api, json, errorText, queryClient } from "../api";
import type { User } from "../types";
import { Button } from "../components/ui/button";
export function Admin() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "用户";
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [confirm, setConfirm] = useState("");
  const page = Math.max(1, Number(params.get("page")) || 1);
  const users = useQuery({
    queryKey: ["users", page],
    queryFn: () =>
      api<{ users: User[]; total: number }>(
        `/users/?page=${page}&page_size=20`,
      ),
    enabled: tab === "用户",
  });
  const languages = useQuery({
    queryKey: ["language-details"],
    queryFn: () =>
      api<{ languages: Record<string, any>[] }>(
        "/languages/?include_metadata=true",
      ),
    enabled: tab === "语言",
  });
  const logs = useQuery({
    queryKey: ["audit", page, params.get("user_id"), params.get("problem_id")],
    queryFn: () =>
      api<Record<string, any>[]>(
        `/logs/access/?page=${page}&page_size=20${params.get("user_id") ? "&user_id=" + encodeURIComponent(params.get("user_id")!) : ""}${params.get("problem_id") ? "&problem_id=" + encodeURIComponent(params.get("problem_id")!) : ""}`,
      ),
    enabled: tab === "访问审计",
  });
  const action = async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
      setMessage("已保存");
      await queryClient.invalidateQueries();
    } catch (e) {
      setError(errorText(e));
    }
  };
  return (
    <div className="page">
      <h1>
        <Icon name="chart" />
        管理
      </h1>
      <div className="step-tabs">
        {["用户", "语言", "访问审计", "系统设置"].map((v) => (
          <Button
            key={v}
            variant={v === tab ? "default" : "ghost"}
            onClick={() => setParams({ tab: v })}
          >
            {v}
          </Button>
        ))}
      </div>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {tab === "用户" && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>角色</th>
                  <th>通过 / 提交</th>
                  <th>修改角色</th>
                </tr>
              </thead>
              <tbody>
                {users.data?.users.map((u) => (
                  <tr key={u.user_id}>
                    <td>{u.username}</td>
                    <td>{u.role}</td>
                    <td>
                      {u.resolve_count} / {u.submit_count}
                    </td>
                    <td>
                      <form
                        className="row"
                        onSubmit={(e) => {
                          e.preventDefault();
                          const f = new FormData(e.currentTarget);
                          void action(() =>
                            api(
                              `/users/${u.user_id}/role`,
                              json("PUT", { role: f.get("role") }),
                            ),
                          );
                        }}
                      >
                        <select
                          name="role"
                          aria-label={`${u.username}的角色`}
                          defaultValue={u.role}
                        >
                          <option value="user">学习者</option>
                          <option value="admin">管理员</option>
                          <option value="banned">禁用</option>
                        </select>
                        <Button>保存</Button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>创建用户</summary>
            <form
              className="form-grid narrow"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void action(() =>
                  api(
                    f.get("role") === "admin" ? "/users/admin" : "/users/",
                    json("POST", {
                      username: f.get("username"),
                      password: f.get("password"),
                    }),
                  ),
                );
              }}
            >
              <label>
                用户名
                <input name="username" minLength={3} required />
              </label>
              <label>
                初始密码
                <input
                  type="password"
                  name="password"
                  minLength={6}
                  required
                  autoComplete="new-password"
                />
              </label>
              <label>
                角色
                <select name="role">
                  <option value="user">学习者</option>
                  <option value="admin">管理员</option>
                </select>
              </label>
              <Button>创建</Button>
            </form>
          </details>
        </>
      )}
      {tab === "语言" && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>语言</th>
                  <th>时间</th>
                  <th>内存</th>
                </tr>
              </thead>
              <tbody>
                {languages.data?.languages.map((l) => (
                  <tr key={l.name}>
                    <td>{l.name}</td>
                    <td>{l.time_limit} 秒</td>
                    <td>{l.memory_limit} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>注册语言 / 更新配置</summary>
            <form
              className="form-grid narrow"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void action(() =>
                  api(
                    "/languages/",
                    json("POST", {
                      name: f.get("name"),
                      file_ext: f.get("file_ext"),
                      compile_cmd: f.get("compile_cmd") || null,
                      run_cmd: f.get("run_cmd"),
                      time_limit: Number(f.get("time_limit")),
                      memory_limit: Number(f.get("memory_limit")),
                    }),
                  ),
                );
              }}
            >
              {[
                ["name", "语言名称"],
                ["file_ext", "文件扩展名"],
                ["compile_cmd", "编译命令（可留空）"],
                ["run_cmd", "运行命令"],
              ].map(([n, l]) => (
                <label key={n}>
                  {l}
                  <input name={n} required={n !== "compile_cmd"} />
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
              <Button>保存语言</Button>
            </form>
          </details>
        </>
      )}
      {tab === "访问审计" && (
        <>
          <div className="filters">
            <input
              aria-label="审计用户 ID"
              placeholder="用户 ID"
              value={params.get("user_id") || ""}
              onChange={(e) =>
                setParams(
                  {
                    ...Object.fromEntries(params),
                    user_id: e.target.value,
                    page: "1",
                  },
                  { replace: true },
                )
              }
            />
            <input
              aria-label="审计题号"
              placeholder="题号"
              value={params.get("problem_id") || ""}
              onChange={(e) =>
                setParams(
                  {
                    ...Object.fromEntries(params),
                    problem_id: e.target.value,
                    page: "1",
                  },
                  { replace: true },
                )
              }
            />
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  <th>题目</th>
                  <th>操作</th>
                  <th>状态</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {logs.data?.map((l, i) => (
                  <tr key={i}>
                    <td>{l.user_id}</td>
                    <td>{l.problem_id}</td>
                    <td>{l.action}</td>
                    <td>{l.status}</td>
                    <td>{l.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {["用户", "访问审计"].includes(tab) && (
        <div className="pagination">
          <Button
            disabled={page === 1}
            onClick={() =>
              setParams({
                ...Object.fromEntries(params),
                page: String(page - 1),
              })
            }
          >
            上一页
          </Button>
          <span>{page}</span>
          <Button
            disabled={
              tab === "用户"
                ? page * 20 >= (users.data?.total || 0)
                : (logs.data?.length || 0) < 20
            }
            onClick={() =>
              setParams({
                ...Object.fromEntries(params),
                page: String(page + 1),
              })
            }
          >
            下一页
          </Button>
        </div>
      )}
      {tab === "系统设置" && (
        <details>
          <summary>恢复初始实验数据</summary>
          <p>
            此操作会清除运行数据、重置账户和题目，并退出所有会话。输入 RESET
            确认。
          </p>
          <input
            aria-label="重置确认"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          <Button
            variant="destructive"
            disabled={confirm !== "RESET"}
            onClick={() =>
              void action(async () => {
                await api("/reset/", json("POST"));
                queryClient.clear();
                window.location.assign("/problems");
              })
            }
          >
            重置数据
          </Button>
        </details>
      )}
    </div>
  );
}

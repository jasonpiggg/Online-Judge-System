import { Icon } from "../components/Icon";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { SearchInput } from "../components/SearchInput";
import { AdminProblems } from "./AdminProblems";
import { Records } from "./Records";
import { api, json, errorText, queryClient } from "../api";
import type { User } from "../types";
import { Button } from "../components/ui/button";
import { Pagination } from "../components/Pagination";
import { LanguageSettings } from "../components/LanguageSettings";
import { useActionReveal } from "../components/useActionReveal";
import { DisclosureCard } from "../components/DisclosureCard";

type AuditPage = { logs: Record<string, any>[]; total: number };
export function Admin({ user }: { user: User }) {
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "用户";
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [confirm, setConfirm] = useState(""),
    [busy, setBusy] = useState(false),
    [auditUserId, setAuditUserId] = useState(params.get("user_id") || ""),
    [auditProblemId, setAuditProblemId] = useState(params.get("problem_id") || "");
  const profileReveal = useActionReveal<HTMLElement>();
  const tabReveal = useActionReveal<HTMLDivElement>();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const hasAuditScope = !!(params.get("user_id") || params.get("problem_id"));
  useEffect(() => {
    if (tab !== "访问审计") return;
    setAuditUserId(params.get("user_id") || "");
    setAuditProblemId(params.get("problem_id") || "");
  }, [location.search, tab]);
  const users = useQuery({
    queryKey: ["users", page, params.get("q")],
    queryFn: () =>
      api<{ users: User[]; total: number }>(
        `/users/?page=${page}&page_size=20&q=${encodeURIComponent(params.get("q") || "")}`,
      ),
    enabled: tab === "用户",
  });
  const logs = useQuery({
    queryKey: ["audit", page, params.get("user_id"), params.get("problem_id")],
    queryFn: () =>
      api<AuditPage>(
        `/logs/access/?page=${page}&page_size=20&include_metadata=true${params.get("user_id") ? "&user_id=" + encodeURIComponent(params.get("user_id")!) : ""}${params.get("problem_id") ? "&problem_id=" + encodeURIComponent(params.get("problem_id")!) : ""}`,
      ),
    enabled: tab === "访问审计" && hasAuditScope,
  });
  const profile = useQuery({
    queryKey: ["admin-user", params.get("user_id")],
    queryFn: () => api<User>(`/users/${params.get("user_id")}`),
    enabled: tab === "用户" && !!params.get("user_id"),
  });
  const roleLogs = useQuery({
    queryKey: ["role-audit", page],
    queryFn: () =>
      api<AuditPage>(
        `/logs/roles/?page=${page}&page_size=20&include_metadata=true`,
      ),
    enabled: tab === "角色审计",
  });
  const action = async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await fn();
      setMessage("已保存");
      await queryClient.invalidateQueries();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const loadError =
    tab === "用户"
      ? users.error || profile.error
      : tab === "访问审计"
        ? logs.error
        : tab === "角色审计"
          ? roleLogs.error
          : null;
  const paginationTotal =
    tab === "用户"
      ? users.data?.total
      : tab === "角色审计"
        ? roleLogs.data?.total
        : tab === "访问审计"
          ? logs.data?.total
          : undefined;
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1>
            <Icon name="shield" />
            管理中心
          </h1>
          <p className="muted">题目、用户与评测，集中管理。</p>
        </div>
        <span className="badge admin-badge">管理员工作台</span>
      </div>
      <div className="step-tabs">
        {[
          "用户",
          "题目",
          "提交",
          "语言",
          "访问审计",
          "角色审计",
          "系统设置",
        ].map((v) => (
          <Button
            key={v}
            variant={v === tab ? "default" : "ghost"}
            onClick={() => {
              setError("");
              setMessage("");
              setParams({ tab: v });
              tabReveal.reveal();
            }}
          >
            {v}
          </Button>
        ))}
      </div>
      <div ref={tabReveal.ref} className="admin-tab-panel reveal-target">
      {(error || loadError) && (
        <p role="alert">{error || loadError?.message}</p>
      )}
      {tab === "题目" && <AdminProblems adminView />}
      {tab === "提交" && <Records user={user} adminView />}
      {tab === "角色审计" && (
        <>
          <h2>角色变更记录</h2>
          {roleLogs.isPending && <p className="skeleton">正在加载…</p>}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>操作人</th>
                  <th>目标用户</th>
                  <th>变更前</th>
                  <th>变更后</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                {roleLogs.data?.logs.map((l) => (
                  <tr key={l.id}>
                    <td>
                      {l.actor_name} <small>#{l.actor_id}</small>
                    </td>
                    <td>
                      {l.target_name} <small>#{l.target_id}</small>
                    </td>
                    <td>{roleLabel(l.old_role)}</td>
                    <td>{roleLabel(l.new_role)}</td>
                    <td>{new Date(l.time).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {roleLogs.data?.total === 0 && (
            <p className="empty">尚无角色变更记录。</p>
          )}
        </>
      )}
      {message && <p role="status">{message}</p>}
      {tab === "用户" && (
        <>
          <div className="section-heading">
            <h2>用户管理</h2>
            <Button asChild>
              <Link to="/admin?tab=提交">
                查看全站提交 <Icon name="arrow" />
              </Link>
            </Button>
          </div>
          <SearchInput
            label="搜索用户"
            placeholder="搜索用户名或用户 ID"
            value={params.get("q") || ""}
            navigationKey={location.key}
            onCommit={(value) =>
              setParams({ tab: "用户", q: value }, { replace: true })
            }
          />
          {users.isPending && <p className="skeleton">正在加载用户…</p>}
          {profile.isPending && params.get("user_id") && (
            <p className="skeleton">正在读取用户资料…</p>
          )}
          {profile.data && (
            <section ref={profileReveal.ref} className="admin-detail reveal-target" aria-label="用户资料">
              <div className="section-heading">
                <h2>{profile.data.username}</h2>
                <Button asChild>
                  <Link to={`/admin?tab=提交&user_id=${profile.data.user_id}`}>
                    查看此用户提交
                  </Link>
                </Button>
              </div>
              <dl className="metadata-grid">
                <div>
                  <dt>用户 ID</dt>
                  <dd>{profile.data.user_id}</dd>
                </div>
                <div>
                  <dt>角色</dt>
                  <dd>{roleLabel(profile.data.role)}</dd>
                </div>
                <div>
                  <dt>加入时间</dt>
                  <dd>{profile.data.join_time}</dd>
                </div>
                <div>
                  <dt>通过题目 / 提交次数</dt>
                  <dd>
                    {profile.data.resolve_count} / {profile.data.submit_count}
                  </dd>
                </div>
              </dl>
            </section>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>用户</th>
                  <th>角色</th>
                  <th>通过 / 提交</th>
                  <th>修改角色</th>
                  <th>查看</th>
                </tr>
              </thead>
              <tbody>
                {users.data?.users.map((u) => (
                  <tr key={u.user_id}>
                    <td>
                      <strong>{u.username}</strong>
                      <small className="cell-note">ID {u.user_id}</small>
                    </td>
                    <td>
                      <span className={`badge role-${u.role}`}>
                        {roleLabel(u.role)}
                      </span>
                    </td>
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
                        <Button disabled={busy}>保存</Button>
                      </form>
                    </td>
                    <td>
                      <div className="action-group">
                        <Button asChild size="compact" variant="ghost">
                          <Link onClick={profileReveal.reveal} to={`/admin?tab=用户&user_id=${u.user_id}`}>
                            资料
                          </Link>
                        </Button>
                        <Button asChild size="compact">
                          <Link to={`/admin?tab=提交&user_id=${u.user_id}`}>
                            提交记录
                          </Link>
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {users.data?.total === 0 && <p className="empty">没有匹配的用户。</p>}
          <DisclosureCard summary="创建用户">
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
              <div className="form-actions">
                <Button disabled={busy}>创建</Button>
              </div>
            </form>
          </DisclosureCard>
        </>
      )}
      {tab === "语言" && <LanguageSettings />}
      {tab === "访问审计" && (
        <>
          <form
            className="filters filter-panel audit-filter-form"
            onSubmit={(event) => {
              event.preventDefault();
              const userId = auditUserId.trim();
              const problemId = auditProblemId.trim();
              if (!userId && !problemId) {
                setError("请至少填写用户 ID 或题号。");
                return;
              }
              setError("");
              setParams({
                tab: "访问审计",
                ...(userId ? { user_id: userId } : {}),
                ...(problemId ? { problem_id: problemId } : {}),
                page: "1",
              });
            }}
          >
            <label>
              用户 ID
              <input
                aria-label="审计用户 ID"
                inputMode="numeric"
                pattern="[0-9]+"
                value={auditUserId}
                onChange={(event) => setAuditUserId(event.target.value)}
                placeholder="例如 12"
              />
            </label>
            <label>
              题号
              <input
                aria-label="审计题号"
                value={auditProblemId}
                onChange={(event) => setAuditProblemId(event.target.value)}
                placeholder="例如 sum_2"
              />
            </label>
            <Button variant="default">查询审计</Button>
          </form>
          {!hasAuditScope && (
            <p className="empty">请至少填写用户 ID 或题号，再查询访问审计。</p>
          )}
          {logs.isPending && <p className="skeleton">正在读取访问审计…</p>}
          {logs.data?.total === 0 && (
            <p className="empty">没有匹配的访问记录。</p>
          )}
          {hasAuditScope && <div className="table-scroll">
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
                {logs.data?.logs.map((l, i) => (
                  <tr key={i}>
                    <td>
                      <Link to={`/admin?tab=用户&user_id=${l.user_id}`}>
                        用户 {l.user_id}
                      </Link>
                    </td>
                    <td>
                      <Link to={`/admin?tab=题目&problem_id=${l.problem_id}`}>
                        {l.problem_id}
                      </Link>
                    </td>
                    <td>
                      {l.action === "view_logs" ? "查看评测日志" : l.action}
                    </td>
                    <td>
                      <span
                        className={
                          String(l.status) === "200"
                            ? "badge tone-AC"
                            : "badge tone-WA"
                        }
                      >
                        {String(l.status) === "200" ? "允许访问" : "拒绝访问"} ·{" "}
                        {l.status}
                      </span>
                    </td>
                    <td>{new Date(l.time).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
        </>
      )}
      {paginationTotal !== undefined && (
        <Pagination
          page={page}
          totalPages={Math.ceil(paginationTotal / 20)}
          label={`${tab}分页`}
          onChange={(next) =>
            setParams({
              ...Object.fromEntries(params),
              page: String(next),
            })
          }
        />
      )}
      {tab === "系统设置" && (
        <DisclosureCard summary="恢复初始实验数据">
          <p>
            此操作会清除运行数据、重置账户和题目，并退出所有会话。输入 RESET
            确认。
          </p>
          <label>
            输入 RESET 确认
            <input
              aria-label="重置确认"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </label>
          <div className="form-actions">
            <Button
              variant="destructive"
              disabled={busy || confirm !== "RESET"}
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
          </div>
        </DisclosureCard>
      )}
      </div>
    </div>
  );
}

function roleLabel(role: string) {
  return (
    (
      { user: "学习者", admin: "管理员", banned: "已禁用" } as Record<
        string,
        string
      >
    )[role] || role
  );
}

import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { api, ApiError, json, errorText, queryClient, setApiUser } from "./api";
import type { User } from "./types";
import { Library } from "./pages/Library";
import { Button } from "./components/ui/button";
import { Records, SubmissionPage } from "./pages/Records";
import { Account } from "./pages/Account";
import { Admin } from "./pages/Admin";
import { Authoring, DraftPage, AuthoringTask } from "./pages/Authoring";
import { Resources } from "./pages/Resources";
import "./style.css";
import { Icon } from "./components/Icon";
import { ActivityBar, ActivityProvider } from "./components/Activity";
import { PublicLog } from "./pages/PublicLog";
import { useNavigationBoundary } from "./components/BackLink";
const Workspace = lazy(() =>
  import("./pages/Workspace").then((m) => ({ default: m.Workspace })),
);
export function Login() {
  const loginTab = useRef<HTMLButtonElement>(null);
  const registerTab = useRef<HTMLButtonElement>(null);
  const usernameInput = useRef<HTMLInputElement>(null);
  const passwordInput = useRef<HTMLInputElement>(null);
  const [register, setRegister] = useState(false),
    [username, setUsername] = useState(""),
    [error, setError] = useState(""),
    [errorId, setErrorId] = useState(""),
    [fieldErrors, setFieldErrors] = useState<Record<string, string>>({}),
    [busy, setBusy] = useState(false),
    [password, setPassword] = useState(""),
    [confirmation, setConfirmation] = useState(""),
    [showPassword, setShowPassword] = useState(false),
    [showConfirmation, setShowConfirmation] = useState(false),
    [retrySeconds, setRetrySeconds] = useState(0);
  useEffect(() => {
    if (errorId === "user_not_found" || errorId === "account_disabled") usernameInput.current?.focus();
    else if (errorId === "incorrect_password") passwordInput.current?.focus();
  }, [errorId]);
  useEffect(() => {
    if (!retrySeconds) return;
    const timer = window.setInterval(() => setRetrySeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [retrySeconds > 0]);
  const clearField = (field: string) => {
    setFieldErrors((current) => {
      if (!current[field]) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
    setError("");
    setErrorId("");
  };
  const changeMode = (next: boolean) => {
    if (busy || next === register) return;
    setRegister(next);
    setError("");
    setErrorId("");
    setFieldErrors({});
    setPassword("");
    setConfirmation("");
    setShowPassword(false);
    setShowConfirmation(false);
  };
  return (
    <main className="login">
      <Link className="brand" to="/">
        Atelier <span>OJ</span>
      </Link>
      <div
        className="auth-mode"
        role="tablist"
        aria-label="账户操作"
        onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "ArrowRight";
          changeMode(next);
          (next ? registerTab : loginTab).current?.focus();
        }}
      >
        <Button
          ref={loginTab}
          type="button"
          role="tab"
          aria-selected={!register}
          tabIndex={!register ? 0 : -1}
          variant={!register ? "default" : "ghost"}
          onClick={() => changeMode(false)}
          disabled={busy}
        >
          登录
        </Button>
        <Button
          ref={registerTab}
          type="button"
          role="tab"
          aria-selected={register}
          tabIndex={register ? 0 : -1}
          variant={register ? "default" : "ghost"}
          onClick={() => changeMode(true)}
          disabled={busy}
        >
          注册
        </Button>
      </div>
      <h1>{register ? "创建账户" : "登录，继续练习"}</h1>
      <p className="muted auth-intro">
        {register
          ? "创建学习账户后会自动登录，并继续打开当前页面。"
          : "使用你的课程账户继续做题、查看提交和保存草稿。"}
      </p>
      <form
        noValidate
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy || retrySeconds > 0) return;
          setBusy(true);
          setError("");
          setErrorId("");
          const validation: Record<string, string> = {};
          const usernameLength = [...username].length;
          const passwordLength = [...password].length;
          if (usernameLength < 3) validation.username = "用户名至少需要 3 个字符。";
          else if (usernameLength > 40) validation.username = "用户名不能超过 40 个字符。";
          else if ([...username].some((character) => /\s/.test(character) || character.charCodeAt(0) <= 31 || character.charCodeAt(0) === 127)) validation.username = "用户名不能包含空格或控制字符。";
          if (passwordLength < 6) validation.password = "密码至少需要 6 个字符。";
          else if (passwordLength > 200) validation.password = "密码不能超过 200 个字符。";
          if (register && password !== confirmation) validation.password_confirmation = "两次输入的密码不一致。";
          if (Object.keys(validation).length) {
            setFieldErrors(validation);
            setBusy(false);
            (validation.username ? usernameInput.current : passwordInput.current)?.focus();
            return;
          }
          const body = { username, password };
          try {
            if (register) await api("/users/", json("POST", body));
            await api("/auth/login", json("POST", body));
            queryClient.removeQueries({
              predicate: (q) => q.queryKey[0] !== "me",
            });
            await queryClient.invalidateQueries({ queryKey: ["me"] });
          } catch (e) {
            const apiError = e instanceof ApiError ? e : null;
            const id = apiError?.details?.id || "";
            const serverFields = Object.fromEntries(
              (apiError?.details?.fields || [])
                .filter((item) => ["username", "password", "password_confirmation"].includes(item.field))
                .map((item) => [item.field, item.message]),
            );
            if (id === "user_not_found") serverFields.username = "没有找到这个用户，请检查拼写。";
            if (id === "incorrect_password") serverFields.password = "密码不正确，请重新输入。";
            setFieldErrors(serverFields);
            setError(Object.keys(serverFields).length ? "" : errorText(e));
            setErrorId(id);
            if (id === "login_rate_limited") setRetrySeconds(apiError?.retryAfter || 300);
            if (!register) {
              setPassword("");
            }
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          用户名
          <input
            ref={usernameInput}
            name="username"
            aria-label="用户名"
            aria-invalid={!!fieldErrors.username || undefined}
            aria-describedby={fieldErrors.username ? "username-error" : undefined}
            autoComplete="username"
            minLength={3}
            required
            disabled={busy}
            value={username}
            onChange={(event) => {
              setUsername(event.target.value);
              clearField("username");
            }}
          />
          {fieldErrors.username && <small id="username-error" className="field-error" role="alert">{fieldErrors.username}</small>}
        </label>
        <label>
          密码
          <span className="password-field">
            <input
              ref={passwordInput}
              aria-label="密码"
              aria-invalid={!!fieldErrors.password || undefined}
              aria-describedby={fieldErrors.password ? "password-error" : undefined}
              type={showPassword ? "text" : "password"}
              name="password"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                clearField("password");
                if (register) clearField("password_confirmation");
              }}
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={6}
              disabled={busy}
            />
            <button
              className="password-toggle"
              type="button"
              aria-label={showPassword ? "隐藏密码" : "显示密码"}
              aria-pressed={showPassword}
              onClick={() => setShowPassword((visible) => !visible)}
              disabled={busy}
            >
              <Icon name={showPassword ? "eyeOff" : "eye"} />
            </button>
          </span>
          {fieldErrors.password && <small id="password-error" className="field-error" role="alert">{fieldErrors.password}</small>}
        </label>
        {register && (
          <label>
            确认密码
            <span className="password-field">
              <input
                aria-label="确认密码"
                aria-invalid={!!fieldErrors.password_confirmation || undefined}
                aria-describedby={fieldErrors.password_confirmation ? "confirmation-error" : undefined}
                type={showConfirmation ? "text" : "password"}
                name="password_confirmation"
                value={confirmation}
                onChange={(event) => {
                  setConfirmation(event.target.value);
                  clearField("password_confirmation");
                }}
                autoComplete="new-password"
                required
                minLength={6}
                disabled={busy}
              />
              <button
                className="password-toggle"
                type="button"
                aria-label={showConfirmation ? "隐藏确认密码" : "显示确认密码"}
                aria-pressed={showConfirmation}
                onClick={() => setShowConfirmation((visible) => !visible)}
                disabled={busy}
              >
                <Icon name={showConfirmation ? "eyeOff" : "eye"} />
              </button>
            </span>
            {fieldErrors.password_confirmation && <small id="confirmation-error" className="field-error" role="alert">{fieldErrors.password_confirmation}</small>}
            <small className="muted">用户名至少 3 个字符，密码至少 6 个字符。</small>
          </label>
        )}
        {error && <p className="auth-error" role="alert">{error}</p>}
        <Button variant="default" disabled={busy || retrySeconds > 0}>
          {busy ? "请稍候…" : retrySeconds > 0 ? `${retrySeconds} 秒后重试` : register ? "注册并登录" : "登录"}
        </Button>
      </form>
    </main>
  );
}
export default function App() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
  });
  const location = useLocation();
  useNavigationBoundary(me.data ? String(me.data.user_id) : undefined);
  useEffect(() => {
    const expired = () => {
      setApiUser();
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      queryClient.setQueryData(["me"], null);
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    document.title =
      "Atelier OJ · " +
      (location.pathname.startsWith("/problems/") ? "做题" : "编程练习");
  }, [location]);
  if (me.isPending) return <div className="skeleton">正在加载…</div>;
  if (!me.data) return <Login />;
  const user = me.data;
  setApiUser(String(user.user_id));
  return (
    <ActivityProvider userId={String(user.user_id)}>
      <header className="topbar">
        <div className="topbar-inner">
          <Link className="brand" to="/problems">
            <span className="brand-mark">
              <Icon name="code" />
            </span>
            <span className="brand-wordmark">
              Atelier <b>OJ</b>
              <small>编程练习空间</small>
            </span>
          </Link>
          <nav aria-label="主导航">
            <NavLink to="/problems">
              <Icon name="book" />
              题库
            </NavLink>
            <NavLink to="/submissions">
              <Icon name="chart" />
              我的提交
            </NavLink>
            <NavLink to="/authoring">
              <Icon name="spark" />
              命题中心
            </NavLink>
            {user.role !== "admin" && (
              <NavLink to="/resources">
                <Icon name="code" />
                资源
              </NavLink>
            )}
            {user.role === "admin" && (
              <NavLink to="/admin">
                <Icon name="shield" />
                管理
              </NavLink>
            )}
          </nav>
          <NavLink
            className="account-link"
            to="/account"
            aria-label={`${user.username}的账户`}
          >
            <span className="avatar" aria-hidden="true">
              {user.username.slice(0, 1).toUpperCase()}
            </span>
            <span className="account-name">
              {user.username}
              <small>{user.role === "admin" ? "管理员" : "学习者"}</small>
            </span>
          </NavLink>
        </div>
      </header>
      <ActivityBar />
      <main>
        <Suspense fallback={<div className="skeleton">正在打开页面…</div>}>
          <Routes>
            <Route path="/problems" element={<Library />} />
            <Route path="/problems/:id" element={<Workspace user={user} />} />
            <Route path="/submissions" element={<Records user={user} />} />
            <Route
              path="/submissions/:id"
              element={<SubmissionPage user={user} />}
            />
            <Route path="/account" element={<Account user={user} />} />
            <Route path="/resources" element={<Resources />} />
            <Route path="/logs/submissions/:id" element={<PublicLog user={user} />} />
            <Route
              path="/admin"
              element={
                user.role === "admin" ? (
                  <Admin user={user} />
                ) : (
                  <Navigate to="/problems" replace />
                )
              }
            />
            <Route path="/authoring" element={<Authoring />} />
            <Route
              path="/authoring/drafts/:id"
              element={<DraftPage user={user} />}
            />
            <Route path="/authoring/tasks/:id" element={<AuthoringTask />} />
            <Route path="*" element={<Navigate to="/problems" replace />} />
          </Routes>
        </Suspense>
      </main>
    </ActivityProvider>
  );
}

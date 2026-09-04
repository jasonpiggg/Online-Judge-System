import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { api, json, errorText, queryClient, setApiUser } from "./api";
import type { User } from "./types";
import { Library } from "./pages/Library";
import { Button } from "./components/ui/button";
import { Records, SubmissionPage } from "./pages/Records";
import { Account } from "./pages/Account";
import { Admin } from "./pages/Admin";
import { Authoring, DraftPage, AuthoringTask } from "./pages/Authoring";
import "./style.css";
const Workspace = lazy(() =>
  import("./pages/Workspace").then((m) => ({ default: m.Workspace })),
);
function Login() {
  const [register, setRegister] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <Link className="brand" to="/">
        Atelier <span>OJ</span>
      </Link>
      <h1>{register ? "创建账户" : "登录，继续练习"}</h1>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          const data = new FormData(e.currentTarget);
          const body = {
            username: data.get("username"),
            password: data.get("password"),
          };
          try {
            if (register) await api("/users/", json("POST", body));
            await api("/auth/login", json("POST", body));
            queryClient.removeQueries({
              predicate: (q) => q.queryKey[0] !== "me",
            });
            await queryClient.invalidateQueries({ queryKey: ["me"] });
          } catch (e) {
            setError(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          用户名
          <input name="username" autoComplete="username" required />
        </label>
        <label>
          密码
          <input
            type="password"
            name="password"
            autoComplete={register ? "new-password" : "current-password"}
            required
            minLength={6}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <Button variant="default" disabled={busy}>
          {busy ? "请稍候…" : register ? "注册并登录" : "登录"}
        </Button>
      </form>
      <Button variant="ghost" onClick={() => setRegister(!register)}>
        {register ? "已有账户？登录" : "没有账户？注册"}
      </Button>
    </main>
  );
}
export default function App() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
  });
  const location = useLocation();
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
    <>
      <header className="topbar">
        <Link className="brand" to="/problems">
          Atelier <span>OJ</span>
        </Link>
        <nav aria-label="主导航">
          <NavLink to="/problems">题库</NavLink>
          <NavLink to="/submissions">我的提交</NavLink>
          <NavLink to="/authoring">命题中心</NavLink>
          {user.role === "admin" && <NavLink to="/admin">管理</NavLink>}
        </nav>
        <Link className="account-link" to="/account">
          {user.username}
        </Link>
      </header>
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
            <Route
              path="/admin"
              element={
                user.role === "admin" ? (
                  <Admin />
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
    </>
  );
}

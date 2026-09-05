import { Icon } from "../components/Icon";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, json, errorText, queryClient } from "../api";
import type { User } from "../types";
import { Button } from "../components/ui/button";
import { LanguageSettings } from "../components/LanguageSettings";
export function ModelSettings() {
  const { data: c } = useQuery({
    queryKey: ["model-config"],
    queryFn: () => api<Record<string, any>>("/ai/model-config"),
  });
  const [error, setError] = useState(""),
    [saved, setSaved] = useState(false),
    [busy, setBusy] = useState(false);
  return (
    <section>
      <h2>AI 模型</h2>
      <p>
        {c?.source === "system"
          ? "正在使用系统模型"
          : c?.source === "personal"
            ? "正在使用个人模型"
            : "尚未配置模型"}
      </p>
      <details className="disclosure-card">
        <summary>个人模型配置</summary>
        <form
          className="form-grid"
          key={c?.source}
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setSaved(false);
            setError("");
            const f = new FormData(e.currentTarget);
            const body = {
              provider_url: f.get("provider_url"),
              model: f.get("model"),
              api_key: f.get("api_key") || null,
              currency: f.get("currency"),
              input_price: Number(f.get("input_price")),
              output_price: Number(f.get("output_price")),
              price_unit: 1000000,
            };
            try {
              await api("/ai/model-config", json("PUT", body));
              setSaved(true);
              await queryClient.invalidateQueries({
                queryKey: ["model-config"],
              });
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            兼容 API 地址
            <input
              name="provider_url"
              type="url"
              required
              defaultValue={c?.provider_url || ""}
              placeholder="https://example.com/v1"
            />
          </label>
          <label>
            模型名称
            <input name="model" required defaultValue={c?.model || ""} />
          </label>
          <label>
            API key
            <input
              name="api_key"
              type="password"
              autoComplete="off"
              required={!c?.personal_configured}
              placeholder={c?.personal_configured ? "留空保留现有密钥" : ""}
            />
          </label>
          <div className="filters">
            <label>
              输入单价 / 百万 Token
              <input
                type="number"
                name="input_price"
                step="any"
                min="0"
                defaultValue={c?.input_price || 0}
              />
            </label>
            <label>
              输出单价 / 百万 Token
              <input
                type="number"
                name="output_price"
                step="any"
                min="0"
                defaultValue={c?.output_price || 0}
              />
            </label>
            <label>
              币种
              <select name="currency" defaultValue={c?.currency || "CNY"}>
                <option>CNY</option>
                <option>USD</option>
              </select>
            </label>
          </div>
          <Button variant="default" disabled={busy}>
            保存配置
          </Button>
        </form>
        {c?.personal_configured && (
          <Button
            onClick={async () => {
              try {
                await api("/ai/model-config", { method: "DELETE" });
                await queryClient.invalidateQueries({
                  queryKey: ["model-config"],
                });
              } catch (e) {
                setError(errorText(e));
              }
            }}
          >
            移除个人配置，恢复系统模型
          </Button>
        )}
      </details>
      {saved && <p role="status">配置已保存。</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
export function Account({ user }: { user: User }) {
  return (
    <div className="page narrow">
      <h1>
        <Icon name="chart" />
        {user.username}
      </h1>
      <p className="muted">
        加入于 {user.join_time} · {user.role === "admin" ? "管理员" : "学习者"}
      </p>
      <div className="stats">
        <div>
          <strong>{user.resolve_count}</strong>
          <span>已通过题目</span>
        </div>
        <div>
          <strong>{user.submit_count}</strong>
          <span>提交次数</span>
        </div>
      </div>
      <ModelSettings />
      <details className="account-language-settings disclosure-card">
        <summary>评测语言配置</summary>
        <LanguageSettings heading={false} />
      </details>
      <Button
        onClick={async () => {
          await api("/auth/logout", json("POST"));
          for (const storage of [localStorage, sessionStorage]) {
            for (const key of Object.keys(storage)) {
              if (
                key.startsWith(`oj-draft-${user.user_id}-`) ||
                key.startsWith(`oj-author-${user.user_id}-`)
              )
                storage.removeItem(key);
            }
          }
          queryClient.clear();
          window.location.assign("/problems");
        }}
      >
        退出登录
      </Button>
    </div>
  );
}

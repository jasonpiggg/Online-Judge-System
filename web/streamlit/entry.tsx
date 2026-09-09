import { createRoot, type Root } from "react-dom/client";
import { useEffect, useRef, useState } from "react";
import { CodeEditor } from "../src/components/Editor";
import { RichText } from "../src/components/Markdown";
import { DiffView } from "../src/components/DiffView";
import "./style.css";
import { equivalentDraft } from "./draft-state";

type Data = { mode: string; text?: string; code?: string; language?: string; size?: number; owner?: string; storageKey?: string; revision?: number; epoch?: number; before?: Record<string, unknown>; after?: Record<string, unknown>; api?: string; action?: string; username?: string; password?: string; nonce?: string; url?: string; dirty?: boolean; payload?: unknown; saved?: unknown; resolveBackup?: number };
type Bridge = { data: Data; parentElement: HTMLElement | ShadowRoot; setStateValue: (key: string, value: unknown) => void; setTriggerValue: (key: string, value: unknown) => void };
const authPaths: Record<string,string> = { login: "/api/auth/login", register: "/api/users/", logout: "/api/auth/logout", me: "/api/auth/me" };
let tabId = crypto.randomUUID();
try { tabId = sessionStorage.getItem('oj-streamlit-tab') as typeof tabId || tabId; sessionStorage.setItem('oj-streamlit-tab', tabId); } catch { /* Storage is optional. */ }
function browserApi(api: string | undefined) {
  const target = new URL(api || location.origin);
  if (['localhost', '127.0.0.1'].includes(target.hostname) && ['localhost', '127.0.0.1'].includes(location.hostname)) target.hostname = location.hostname;
  return target.origin;
}
const sameCode = (a: unknown, b: unknown) => typeof a === 'string' && typeof b === 'string' && a.replace(/\r\n/g,'\n') === b.replace(/\r\n/g,'\n');
const dirtyControls = new Map<string, boolean>();
let pendingFormInput = false;
const isDirty = () => pendingFormInput || [...dirtyControls.values()].some(Boolean);
const scrollSurface = () => document.querySelector<HTMLElement>('[data-testid="stMain"]') || document.scrollingElement as HTMLElement;
function Component({ bridge }: { bridge: Bridge }) {
  const d = bridge.data;
  const storageKey = d.storageKey ? `${d.storageKey}:${tabId}` : undefined;
  const callbacks = useRef(bridge); callbacks.current = bridge;
  const [code, setCode] = useState(d.code || "");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastEpoch = useRef(d.epoch);
  const seen = useRef("");
  const backupPending = useRef(false);
  const resolution = useRef(d.resolveBackup);
  useEffect(() => {
    if (d.epoch !== lastEpoch.current) { setCode(d.code || ""); lastEpoch.current = d.epoch; }
  }, [d.code, d.epoch]);
  useEffect(() => {
    if (!['editor', 'backup'].includes(d.mode) || !storageKey) return;
    try {
      const raw = sessionStorage.getItem(storageKey) || localStorage.getItem(storageKey);
      if (raw) {
        const value = JSON.parse(raw);
        if ((d.mode === 'editor' && typeof value.code === "string" && !sameCode(value.code, d.code)) || (d.mode === 'backup' && value.payload && typeof value.payload === 'object' && !equivalentDraft(value.payload, d.payload))) {
          backupPending.current = true;
          callbacks.current.setTriggerValue("backup", value);
        }
      }
    } catch { /* A malformed local backup cannot replace server data. */ }
  }, [storageKey, d.mode]);
  useEffect(() => {
    if (!storageKey) return;
    if (d.mode === 'editor') dirtyControls.set(storageKey, !sameCode(code, d.saved));
    if (d.mode === 'backup') { dirtyControls.set(storageKey, !equivalentDraft(d.payload, d.saved)); pendingFormInput = false; }
    try {
      if (resolution.current !== d.resolveBackup) {
        resolution.current = d.resolveBackup; backupPending.current = false;
        sessionStorage.removeItem(storageKey); localStorage.removeItem(storageKey);
      }
      if (backupPending.current) return;
      if (d.mode === 'editor') {
        const raw = sessionStorage.getItem(storageKey) || localStorage.getItem(storageKey);
        if (raw && sameCode(JSON.parse(raw).code, d.saved)) { sessionStorage.removeItem(storageKey); localStorage.removeItem(storageKey); }
      } else if (d.mode === 'backup') {
        if (equivalentDraft(d.payload, d.saved)) { sessionStorage.removeItem(storageKey); localStorage.removeItem(storageKey); }
        else { const raw = JSON.stringify({payload:d.payload,revision:d.revision}); sessionStorage.setItem(storageKey,raw); localStorage.setItem(storageKey,raw); }
      }
    } catch { /* Never discard server data because storage is unavailable. */ }
  }, [d.saved, d.payload, d.mode, d.revision, d.resolveBackup, storageKey, code]);
  useEffect(() => () => { if (storageKey) dirtyControls.delete(storageKey); }, [storageKey]);
  useEffect(() => {
    if (d.mode !== "auth" || !d.nonce || seen.current === d.nonce) return;
    seen.current = d.nonce;
    void (async () => {
      try {
        const path = authPaths[d.action || ""];
        if (!path || !d.api) throw Error("无效认证请求");
        const body = JSON.stringify({ username: d.username, password: d.password });
        const options = { method: "POST", credentials: "include" as const, headers: { "Content-Type": "application/json" }, body: d.action === "logout" ? undefined : body };
        let res = await fetch(browserApi(d.api) + path, options);
        let payload = await res.json();
        if (res.ok && d.action === "register") { res = await fetch(browserApi(d.api) + authPaths.login, options); payload = await res.json(); }
        if (res.ok) { window.location.reload(); return; }
        callbacks.current.setTriggerValue("result", { status: res.status, payload, retryAfter: res.headers.get("Retry-After") });
      } catch { callbacks.current.setTriggerValue("result", { status: 503, payload: { msg: "认证服务无法连接，请检查服务状态。" } }); }
    })();
  }, [d.nonce, d.mode]);
  useEffect(() => {
    if (d.mode !== "state") return;
    const storage = `oj-streamlit-ui:${d.owner}:${tabId}`;
    const scrollKey = `oj-streamlit-scroll:${d.owner}:${location.pathname}${location.search}`;
    if (!seen.current) {
      seen.current = storage;
      let restored: unknown = [];
      try { const raw = localStorage.getItem(storage); if (raw) restored = JSON.parse(raw); } catch { /* Ignore malformed state. */ }
      callbacks.current.setStateValue('restored', Array.isArray(restored) ? restored : []);
    }
    const surface = scrollSurface();
    const updateSection = () => {
      const sectionLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('.st-key-section-nav a'));
      let current = sectionLinks[0];
      for (const link of sectionLinks) {
        const section = document.getElementById(decodeURIComponent(link.hash.slice(1)));
        if (section && section.getBoundingClientRect().top <= 180) current = link;
      }
      for (const link of sectionLinks) {
        if (link === current) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      }
    };
    surface.addEventListener('scroll', updateSection, { passive: true });
    updateSection();
    let restoreTimer: ReturnType<typeof setInterval> | undefined;
    try {
      const y = Number(sessionStorage.getItem(scrollKey) || 0);
      let attempts = 0;
      if (y > 0) restoreTimer = setInterval(() => {
        // The native page arrives after the browser-state handshake.
        if (surface.scrollHeight - surface.clientHeight >= y || ++attempts >= 30) {
          surface.scrollTo({top:y}); clearInterval(restoreTimer);
        }
      }, 100);
    } catch { /* Optional restoration. */ }
    if (d.payload) { try { localStorage.setItem(storage, JSON.stringify(d.payload)); } catch { /* Storage can be disabled. */ } }
    const save = () => { try { sessionStorage.setItem(scrollKey, String(surface.scrollTop)); } catch { /* Optional. */ } };
    const guard = (event: BeforeUnloadEvent) => { save(); if (isDirty()) { event.preventDefault(); event.returnValue = ""; } };
    const input = (event: Event) => {
      if (location.pathname === '/draft' && event.target instanceof HTMLElement && event.target.closest('[data-testid="stMain"]')) pendingFormInput = true;
    };
    const navigate = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest('a,button') : null;
      if (!target) return;
      if (target.closest(".st-key-close-current-task, .st-key-clear-task-tabs")) return;
      const href = target.getAttribute('href');
      const changesPage = href && !href.startsWith('#') && !target.hasAttribute('download') || target.closest('.st-key-task-bar') || /^(返回来源|上一题|下一题|退出登录)$/.test(target.textContent?.trim() || '');
      if (changesPage && isDirty() && !window.confirm('存在尚未保存的修改。确认离开？源码和已同步到页面的草稿会保留本地备份。')) { event.preventDefault(); event.stopImmediatePropagation(); }
    };
    surface.addEventListener("scroll", save, { passive: true });
    document.addEventListener('input', input, true);
    document.addEventListener('click', navigate, true);
    window.addEventListener("beforeunload", guard);
    const check = async () => {
      try {
        const r = await fetch(browserApi(d.api) + authPaths.me, { credentials: "include", cache: "no-store" });
        const p = await r.json();
        if (!r.ok || String(p.data?.user_id) !== String(d.owner)) window.location.reload();
      } catch { /* Backend requests also enforce identity before every operation. */ }
    };
    const interval = setInterval(() => void check(), 4000);
    const focus = () => void check(); window.addEventListener("focus", focus);
    return () => { clearInterval(interval); clearInterval(restoreTimer); window.removeEventListener("focus", focus); surface.removeEventListener("scroll", save); surface.removeEventListener("scroll", updateSection); document.removeEventListener('input', input, true); document.removeEventListener('click', navigate, true); window.removeEventListener("beforeunload", guard); };
  }, [d.mode, d.owner, d.payload, d.url]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  if (d.mode === "markdown") return <RichText text={d.text} />;
  if (d.mode === "diff") return <DiffView before={d.before || {}} after={d.after || {}} />;
  if (d.mode === "editor") return <CodeEditor value={code} language={d.language} size={d.size} onChange={(value) => {
    setCode(value);
    if (storageKey) dirtyControls.set(storageKey, !sameCode(value,d.saved));
    if (storageKey) { try { const raw = JSON.stringify({code:value,revision:d.revision}); sessionStorage.setItem(storageKey,raw); localStorage.setItem(storageKey,raw); } catch { /* Python receives edits even without browser storage. */ } }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => callbacks.current.setStateValue("edit", { code:value,revision:d.revision,epoch:d.epoch }), 400);
  }} onSubmit={() => { if (timer.current) clearTimeout(timer.current); callbacks.current.setTriggerValue("submit", {code,revision:d.revision}); }} />;
  if (d.mode === "auth") return <p role="status">正在验证账户……</p>;
  return null;
}
type MountedParent = (HTMLElement | ShadowRoot) & { _ojRoot?: Root };
const mounted = new Set<MountedParent>();
// Streamlit updates data without unmounting controls. Dispose only disconnected roots.
const observer = new MutationObserver(() => {
  for (const parent of mounted) {
    if (!(parent instanceof ShadowRoot ? parent.host : parent).isConnected) {
      parent._ojRoot?.unmount(); delete parent._ojRoot; mounted.delete(parent);
    }
  }
});
observer.observe(document.body, {childList:true,subtree:true});
export default function render(bridge: Bridge) {
  const parent = bridge.parentElement as (HTMLElement | ShadowRoot) & { _ojRoot?: Root };
  if (!parent._ojRoot) { const node = document.createElement("div"); node.className = "oj-component"; parent.appendChild(node); parent._ojRoot = createRoot(node); mounted.add(parent); }
  parent._ojRoot.render(<Component bridge={bridge} />);
}

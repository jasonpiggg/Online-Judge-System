import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "./Icon";

export type ActivityKind = "problem" | "draft" | "ai" | "submission";
export type ActivityEntry = {
  id: string;
  kind: ActivityKind;
  title: string;
  path: string;
  status?: string;
  unsafeToClose?: boolean;
  closeMessage?: string;
  touchedAt: number;
};

type ActivityContextValue = {
  entries: ActivityEntry[];
  upsert: (entry: Omit<ActivityEntry, "touchedAt"> & { touchedAt?: number }) => void;
  remove: (id: string) => void;
};

const ActivityContext = createContext<ActivityContextValue | null>(null);
const iconFor = (kind: ActivityKind) =>
  ({ problem: "code", draft: "file", ai: "bot", submission: "play" })[kind];

export function routeIdentity(path: string) {
  const pathname = path.split(/[?#]/, 1)[0].replace(/\/+$/, "");
  return pathname || "/";
}

export function upsertActivity(
  current: ActivityEntry[],
  entry: Omit<ActivityEntry, "touchedAt"> & { touchedAt?: number },
  currentPath = "",
) {
  const index = current.findIndex((item) => item.id === entry.id);
  const next = { ...entry, touchedAt: entry.touchedAt || Date.now() };
  if (index < 0) {
    const updated = [next, ...current];
    if (updated.length <= 20) return updated;
    const active = routeIdentity(currentPath);
    while (updated.length > 20) {
      let removable = -1;
      for (let index = updated.length - 1; index >= 0; index -= 1) {
        const item = updated[index];
        if (!item.unsafeToClose && routeIdentity(item.path) !== active) {
          removable = index;
          break;
        }
      }
      if (removable < 0) break;
      updated.splice(removable, 1);
    }
    return updated;
  }
  const updated = current.slice();
  // Status/title refreshes must not reorder browser-like tabs under the pointer.
  updated[index] = next;
  return updated;
}

export function ActivityProvider({ userId, children }: { userId: string; children: ReactNode }) {
  const storageKey = `oj-activities-${userId}`;
  const location = useLocation();
  const [entries, setEntries] = useState<ActivityEntry[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
      return Array.isArray(saved) ? saved : [];
    }
    catch { return []; }
  });
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(entries)); }
    catch { /* Individual editors report storage failures with actionable guidance. */ }
  }, [entries, storageKey]);
  const upsert = useCallback((entry: Omit<ActivityEntry, "touchedAt"> & { touchedAt?: number }) => {
    setEntries((current) => upsertActivity(current, entry, location.pathname + location.search));
  }, [location.pathname, location.search]);
  const remove = useCallback((id: string) => setEntries((items) => items.filter((e) => e.id !== id)), []);
  const value = useMemo(() => ({ entries, upsert, remove }), [entries, upsert, remove]);
  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useActivity() {
  const value = useContext(ActivityContext);
  if (!value) throw new Error("ActivityProvider is missing");
  return value;
}

export function useRegisterActivity(entry: Omit<ActivityEntry, "touchedAt"> | null) {
  const { upsert } = useActivity();
  const signature = entry ? JSON.stringify(entry) : "";
  useEffect(() => {
    if (entry) upsert(entry);
    // Stable serialized content prevents status renders from creating an update loop.
  }, [signature, upsert]);
}

export function ActivityBar() {
  const { entries, remove } = useActivity();
  const location = useLocation();
  const navigate = useNavigate();
  if (!entries.length) return null;
  const currentPath = location.pathname + location.search;
  const activeIndex = entries.findIndex(
    (entry) => routeIdentity(entry.path) === routeIdentity(currentPath),
  );
  const visible = activeIndex >= 6
    ? [entries[activeIndex], ...entries.slice(0, 5)]
    : entries.slice(0, 6);
  const visibleIds = new Set(visible.map((entry) => entry.id));
  const overflow = entries.filter((entry) => !visibleIds.has(entry.id));
  const close = (entry: ActivityEntry) => {
    if (entry.unsafeToClose && !window.confirm(entry.closeMessage || "仍有内容未安全保存，确认关闭此任务入口？")) return;
    remove(entry.id);
    if (routeIdentity(currentPath) === routeIdentity(entry.path)) {
      const target = entries.find((item) => item.id !== entry.id);
      navigate(target?.path || (entry.kind === "draft" || entry.kind === "ai" ? "/authoring" : "/problems"));
    }
  };
  return (
    <div className="activity-strip" aria-label="进行中的任务">
      <div className="activity-strip-inner">
        <span className="activity-label">进行中</span>
        <div className="activity-tabs">
          {visible.map((entry) => (
            <div className={`activity-tab ${routeIdentity(currentPath) === routeIdentity(entry.path) ? "active" : ""}`} key={entry.id}>
              <Link to={entry.path} title={`${entry.title}${entry.status ? ` · ${entry.status}` : ""}`}>
                <Icon name={iconFor(entry.kind)} />
                <span>{entry.title}</span>
                {entry.status && <i aria-label={entry.status} />}
              </Link>
              <button type="button" aria-label={`关闭 ${entry.title}`} onClick={() => close(entry)}><Icon name="close" /></button>
            </div>
          ))}
          {overflow.length > 0 && (
            <details className="activity-more">
              <summary><Icon name="more" /> 更多 {overflow.length}</summary>
              <div>{overflow.map((entry) => <div className={`activity-overflow-row ${routeIdentity(currentPath) === routeIdentity(entry.path) ? "active" : ""}`} key={entry.id}><Link to={entry.path}>{entry.title}<small>{entry.status}</small></Link><button type="button" aria-label={`关闭 ${entry.title}`} onClick={() => close(entry)}><Icon name="close" /></button></div>)}</div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

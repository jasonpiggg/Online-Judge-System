import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Link,
  useLocation,
  useNavigate,
  type LinkProps,
} from "react-router-dom";
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
};
export type TaskSlot = {
  id: string;
  current: ActivityEntry;
  backStack: ActivityEntry[];
  touchedAt: number;
};

type NavigationAction = "activate" | "back" | "new" | "push" | "replace";
type TaskLocationState = Record<string, unknown> & {
  taskSlotId?: string;
  taskAction?: NavigationAction;
};
type StoredActivities = { version: 2; slots: TaskSlot[] };

type ActivityContextValue = {
  slots: TaskSlot[];
  activeSlot?: TaskSlot;
  register: (entry: ActivityEntry) => void;
  remove: (id: string) => void;
  activate: (slot: TaskSlot) => void;
  navigateInSlot: (to: string, options?: { replace?: boolean; state?: object }) => void;
  openRoot: (to: string, state?: object) => void;
  openInNewSlot: (to: string, state?: object) => void;
  replaceCurrent: (to: string, state?: object) => void;
  back: () => void;
  confirmLeave: () => boolean;
};

const ActivityContext = createContext<ActivityContextValue | null>(null);
const STORAGE_VERSION = 2;
const SLOT_LIMIT = 20;
const STACK_LIMIT = 20;
const iconFor = (kind: ActivityKind) =>
  ({ problem: "code", draft: "file", ai: "bot", submission: "play" })[kind];

export function routeIdentity(path: string) {
  const url = new URL(path, "http://oj.local");
  return url.pathname.replace(/\/+$/, "") || "/";
}

function validEntry(value: unknown): value is ActivityEntry {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ActivityEntry>;
  return !!item.id && !!item.title && !!item.path &&
    ["problem", "draft", "ai", "submission"].includes(item.kind || "");
}

function capSlots(slots: TaskSlot[], activeId?: string) {
  const next = slots.slice();
  while (next.length > SLOT_LIMIT) {
    let removable = -1;
    let oldest = Number.POSITIVE_INFINITY;
    next.forEach((slot, index) => {
      const protectedSlot = slot.id === activeId || slot.current.unsafeToClose ||
        slot.backStack.some((entry) => entry.unsafeToClose);
      if (!protectedSlot && slot.touchedAt < oldest) {
        removable = index;
        oldest = slot.touchedAt;
      }
    });
    if (removable < 0) break;
    next.splice(removable, 1);
  }
  return next;
}

export function updateSlot(
  slots: TaskSlot[],
  slotId: string,
  entry: ActivityEntry,
  action: Exclude<NavigationAction, "new">,
  touchedAt = Date.now(),
) {
  return slots.map((slot) => {
    if (slot.id !== slotId) return slot;
    const differentPage = routeIdentity(slot.current.path) !== routeIdentity(entry.path);
    const backStack = action === "push" && differentPage
      ? [...slot.backStack, slot.current].slice(-STACK_LIMIT)
      : slot.backStack;
    return { ...slot, current: entry, backStack, touchedAt };
  });
}

function readStored(storageKey: string): TaskSlot[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey) || "[]");
    if (Array.isArray(parsed)) {
      return parsed.filter(validEntry).map((entry, index) => ({
        id: `migrated-${entry.id}-${index}`,
        current: entry,
        backStack: [],
        touchedAt: Number((entry as ActivityEntry & { touchedAt?: number }).touchedAt) || Date.now(),
      }));
    }
    const stored = parsed as Partial<StoredActivities>;
    if (stored.version !== STORAGE_VERSION || !Array.isArray(stored.slots)) return [];
    return stored.slots.filter((slot): slot is TaskSlot =>
      !!slot && typeof slot.id === "string" && validEntry(slot.current) &&
      Array.isArray(slot.backStack),
    ).map((slot) => ({
      ...slot,
      backStack: slot.backStack.filter(validEntry).slice(-STACK_LIMIT),
    }));
  } catch {
    return [];
  }
}

function mergeState(state: unknown, task: TaskLocationState): TaskLocationState {
  return { ...(state && typeof state === "object" ? state : {}), ...task };
}

function safeHub(entry?: ActivityEntry) {
  if (entry) {
    const from = new URL(entry.path, "http://oj.local").searchParams.get("from");
    if (from?.startsWith("/") && !from.startsWith("//")) return from;
  }
  return entry?.kind === "draft" || entry?.kind === "ai" ? "/authoring" : "/problems";
}

export function ActivityProvider({ userId, children }: { userId: string; children: ReactNode }) {
  const storageKey = `oj-activities-${userId}`;
  const tombstoneKey = `oj-closed-task-slots-${userId}`;
  const location = useLocation();
  const navigate = useNavigate();
  const [slots, setSlots] = useState<TaskSlot[]>(() => readStored(storageKey));
  const slotsRef = useRef(slots);
  slotsRef.current = slots;
  const [activeSlotId, setActiveSlotId] = useState<string>();
  const processedKeys = useRef(new Set<string>());
  const locationState = (location.state || {}) as TaskLocationState;

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ version: STORAGE_VERSION, slots }));
    } catch {
      // Editors surface actionable backup failures; activity persistence is best-effort.
    }
  }, [slots, storageKey]);

  const closedIds = useCallback(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(tombstoneKey) || "[]");
      return new Set<string>(Array.isArray(value) ? value : []);
    } catch {
      return new Set<string>();
    }
  }, [tombstoneKey]);

  const register = useCallback((entry: ActivityEntry) => {
    const requestedId = locationState.taskSlotId;
    if (requestedId && !slotsRef.current.some((slot) => slot.id === requestedId) && closedIds().has(requestedId)) {
      navigate(safeHub(entry), { replace: true, state: {} });
      return;
    }
    const existing = requestedId && slotsRef.current.some((slot) => slot.id === requestedId)
      ? requestedId
      : undefined;
    const isNew = locationState.taskAction === "new" || !existing;
    if (isNew) {
      if (processedKeys.current.has(location.key)) return;
      processedKeys.current.add(location.key);
      const id = crypto.randomUUID();
      const slot: TaskSlot = { id, current: entry, backStack: [], touchedAt: Date.now() };
      setSlots((current) => capSlots([slot, ...current], id));
      setActiveSlotId(id);
      navigate(entry.path, {
        replace: true,
        state: mergeState(location.state, { taskSlotId: id, taskAction: "activate" }),
      });
      return;
    }
    const action = locationState.taskAction || "activate";
    const firstVisit = !processedKeys.current.has(location.key);
    processedKeys.current.add(location.key);
    setActiveSlotId(existing);
    setSlots((current) => updateSlot(
      current,
      existing,
      entry,
      firstVisit && action === "push" ? "push" : action === "replace" ? "replace" : "activate",
    ));
  }, [closedIds, location.key, location.state, locationState.taskAction, locationState.taskSlotId, navigate]);

  const activeSlot = slots.find((slot) => slot.id === activeSlotId);
  const taskState = useCallback((action: NavigationAction, state?: object) =>
    mergeState(state, {
      taskSlotId: action === "new" ? undefined : activeSlot?.id,
      taskAction: activeSlot || action === "new" ? action : "new",
    }), [activeSlot]);

  const confirmLeave = useCallback(() => locationState.taskSlotId !== activeSlot?.id ||
    !activeSlot?.current.unsafeToClose ||
    window.confirm(activeSlot.current.closeMessage || "仍有内容未安全保存，确认离开当前页面？"),
  [activeSlot, locationState.taskSlotId]);

  const navigateInSlot = useCallback((to: string, options?: { replace?: boolean; state?: object }) => {
    if (!confirmLeave()) return;
    const action = options?.replace ? "replace" : "push";
    // A task slot owns its own back stack. Replacing the browser entry prevents
    // closed or renamed task pages from leaking back into global browser history.
    navigate(to, { replace: true, state: taskState(action, options?.state) });
  }, [confirmLeave, navigate, taskState]);
  const openRoot = useCallback((to: string, state?: object) => {
    if (!confirmLeave()) return;
    navigate(to, { state: taskState("new", state) });
  }, [confirmLeave, navigate, taskState]);
  const openInNewSlot = useCallback((to: string, state?: object) => {
    // The current task remains open, so an unsafe draft is not being abandoned.
    navigate(to, { state: taskState("new", state) });
  }, [navigate, taskState]);
  const replaceCurrent = useCallback((to: string, state?: object) => {
    navigate(to, { replace: true, state: taskState("replace", state || location.state) });
  }, [location.state, navigate, taskState]);

  const activate = useCallback((slot: TaskSlot) => {
    if (slot.id !== activeSlot?.id && !confirmLeave()) return;
    setActiveSlotId(slot.id);
    navigate(slot.current.path, {
      replace: true,
      state: mergeState({}, { taskSlotId: slot.id, taskAction: "activate" }),
    });
  }, [activeSlot?.id, confirmLeave, navigate]);

  const remove = useCallback((id: string) => {
    const removed = slots.filter((slot) => slot.id === id || slot.current.id === id);
    if (!removed.length) return;
    if (removed.some((slot) => slot.current.unsafeToClose || slot.backStack.some((entry) => entry.unsafeToClose)) &&
      !window.confirm(removed[0].current.closeMessage || "仍有内容未安全保存，确认关闭此任务标签？")) return;
    const ids = new Set(removed.map((slot) => slot.id));
    const next = slots.filter((slot) => !ids.has(slot.id));
    setSlots(next);
    try {
      sessionStorage.setItem(tombstoneKey, JSON.stringify([...closedIds(), ...ids].slice(-50)));
    } catch { /* Best-effort protection against stale browser history. */ }
    if (activeSlotId && ids.has(activeSlotId)) {
      const target = next[0];
      setActiveSlotId(target?.id);
      if (target) navigate(target.current.path, {
        replace: true,
        state: mergeState({}, { taskSlotId: target.id, taskAction: "activate" }),
      });
      else navigate(safeHub(removed[0].current), { replace: true, state: {} });
    }
  }, [activeSlotId, closedIds, navigate, slots, tombstoneKey]);

  const back = useCallback(() => {
    if (!activeSlot || !activeSlot.backStack.length) return;
    if (activeSlot.current.unsafeToClose &&
      !window.confirm(activeSlot.current.closeMessage || "仍有内容未安全保存，确认返回？")) return;
    const previous = activeSlot.backStack.at(-1)!;
    setSlots((current) => current.map((slot) => slot.id === activeSlot.id ? {
      ...slot,
      current: previous,
      backStack: slot.backStack.slice(0, -1),
      touchedAt: Date.now(),
    } : slot));
    navigate(previous.path, {
      replace: true,
      state: mergeState({}, { taskSlotId: activeSlot.id, taskAction: "back" }),
    });
  }, [activeSlot, navigate]);

  const value = useMemo(() => ({
    slots, activeSlot, register, remove, activate, navigateInSlot,
    openRoot, openInNewSlot, replaceCurrent, back, confirmLeave,
  }), [slots, activeSlot, register, remove, activate, navigateInSlot, openRoot, openInNewSlot, replaceCurrent, back, confirmLeave]);
  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useActivity() {
  const value = useContext(ActivityContext);
  if (!value) throw new Error("ActivityProvider is missing");
  return value;
}

export function useRegisterActivity(entry: ActivityEntry | null) {
  const { register } = useActivity();
  const signature = entry ? JSON.stringify(entry) : "";
  useEffect(() => {
    if (entry) register(entry);
  }, [signature, register]);
}

export function useRecoverUnavailableTask(error: unknown) {
  const { activeSlot, back, remove } = useActivity();
  const location = useLocation();
  const handled = useRef("");
  const state = (location.state || {}) as TaskLocationState;
  const status = error && typeof error === "object" && "status" in error
    ? Number((error as { status?: unknown }).status)
    : 0;
  useEffect(() => {
    if (state.taskAction !== "back" || ![403, 404].includes(status) || !activeSlot) return;
    const key = `${activeSlot.id}:${location.key}`;
    if (handled.current === key) return;
    handled.current = key;
    if (activeSlot.backStack.length) back();
    else remove(activeSlot.id);
  }, [activeSlot, back, location.key, remove, state.taskAction, status]);
}

export function TaskLink({ newSlot = false, state, onClick, ...props }: LinkProps & { newSlot?: boolean }) {
  const { activeSlot, confirmLeave } = useActivity();
  const location = useLocation();
  const currentState = (location.state || {}) as TaskLocationState;
  const insideActiveSlot = !!activeSlot && currentState.taskSlotId === activeSlot.id;
  const action: NavigationAction = newSlot || !insideActiveSlot ? "new" : "push";
  return <Link
    {...props}
    replace={action === "push"}
    state={mergeState(state, {
      taskSlotId: action === "new" ? undefined : activeSlot?.id,
      taskAction: action,
    })}
    onClick={(event) => {
      onClick?.(event);
      if (event.defaultPrevented || action === "new" || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (!confirmLeave()) event.preventDefault();
    }}
  />;
}

export function NewTaskButton({ to, label = "在新任务标签打开" }: { to: string; label?: string }) {
  const { openInNewSlot } = useActivity();
  return (
    <button className="new-task-button" type="button" title={label} aria-label={label} onClick={() => openInNewSlot(to)}>
      <Icon name="newTab" />
    </button>
  );
}

export function ActivityBar() {
  const { slots, activeSlot, remove, activate } = useActivity();
  if (!slots.length) return null;
  const activeIndex = slots.findIndex((slot) => slot.id === activeSlot?.id);
  const visible = activeIndex >= 6
    ? [slots[activeIndex], ...slots.slice(0, 5)]
    : slots.slice(0, 6);
  const visibleIds = new Set(visible.map((slot) => slot.id));
  const overflow = slots.filter((slot) => !visibleIds.has(slot.id));
  const tab = (slot: TaskSlot, overflowRow = false) => (
    <div className={`${overflowRow ? "activity-overflow-row" : "activity-tab"}${slot.id === activeSlot?.id ? " active" : ""}`} key={slot.id}>
      <button type="button" className="activity-tab-target" onClick={() => activate(slot)} title={`${slot.current.title}${slot.current.status ? ` · ${slot.current.status}` : ""}`}>
        <Icon name={iconFor(slot.current.kind)} />
        <span>{slot.current.title}</span>
        {slot.current.status && (overflowRow ? <small>{slot.current.status}</small> : <i aria-label={slot.current.status} />)}
      </button>
      <button type="button" aria-label={`关闭 ${slot.current.title}`} onClick={() => remove(slot.id)}><Icon name="close" /></button>
    </div>
  );
  return (
    <div className="activity-strip" aria-label="进行中的任务">
      <div className="activity-strip-inner">
        <span className="activity-label">进行中</span>
        <div className="activity-tabs">
          {visible.map((slot) => tab(slot))}
          {overflow.length > 0 && (
            <details className="activity-more">
              <summary><Icon name="more" /> 更多 {overflow.length}</summary>
              <div>{overflow.map((slot) => tab(slot, true))}</div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}

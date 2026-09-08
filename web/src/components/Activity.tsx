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
import { api, queryClient } from "../api";

export type ActivityKind = "problem" | "draft" | "ai" | "submission";
export type ActivityEntry = {
  id: string;
  kind: ActivityKind;
  title: string;
  path: string;
  status?: string;
  unsafeToClose?: boolean;
  closeMessage?: string;
  baseProblemId?: string | null;
  navigationState?: Record<string, unknown>;
  scrollY?: number;
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
type ActivityContextValue = {
  slots: TaskSlot[];
  activeSlot?: TaskSlot;
  register: (entry: ActivityEntry) => void;
  remove: (id: string) => void;
  activate: (slot: TaskSlot) => void;
  navigateInSlot: (
    to: string,
    options?: { replace?: boolean; state?: object },
  ) => void;
  openRoot: (to: string, state?: object) => void;
  replaceCurrent: (to: string, state?: object) => void;
  back: () => void;
  confirmLeave: () => boolean;
  findEditingDraft: (problemId: string) => ActivityEntry | undefined;
};
const ActivityContext = createContext<ActivityContextValue | null>(null);
const STORAGE_VERSION = 3;
const SLOT_LIMIT = 20;
const STACK_LIMIT = 20;
const iconFor = (kind: ActivityKind) =>
  ({ problem: "code", draft: "file", ai: "bot", submission: "play" })[kind];

export function routeIdentity(path: string) {
  return new URL(path, "http://oj.local").pathname.replace(/\/+$/, "") || "/";
}
function isTaskPath(path: string) {
  return /^\/(?:problems|submissions|authoring\/(?:drafts|tasks)|logs\/submissions)\/[^/?#]+\/?$/.test(
    routeIdentity(path),
  );
}
function validEntry(value: unknown): value is ActivityEntry {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ActivityEntry>;
  return (
    typeof item.id === "string" &&
    typeof item.title === "string" &&
    typeof item.path === "string" &&
    item.path.startsWith("/") &&
    !item.path.startsWith("//") &&
    !item.path.includes("\\") &&
    isTaskPath(item.path) &&
    ["problem", "draft", "ai", "submission"].includes(item.kind || "")
  );
}
function trimStack(stack: ActivityEntry[]) {
  // Never evict an entry whose only safe copy may still need attention.
  return stack.filter(
    (entry, index) =>
      entry.unsafeToClose || index >= stack.length - STACK_LIMIT,
  );
}
function capSlots(slots: TaskSlot[], activeId?: string) {
  const next = slots.slice();
  while (next.length > SLOT_LIMIT) {
    const removable = next
      .filter(
        (slot) =>
          slot.id !== activeId &&
          ![slot.current, ...slot.backStack].some(
            (entry) => entry.unsafeToClose,
          ),
      )
      .sort((a, b) => a.touchedAt - b.touchedAt)[0];
    if (!removable) break;
    next.splice(next.indexOf(removable), 1);
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
  return slots.map((slot) =>
    slot.id !== slotId
      ? slot
      : {
          ...slot,
          current: entry,
          touchedAt,
          backStack:
            action === "push" &&
            routeIdentity(slot.current.path) !== routeIdentity(entry.path)
              ? trimStack([...slot.backStack, slot.current])
              : slot.backStack,
        },
  );
}
// Page identity belongs to the visible tab; history entries only support Back.
export function findTask(slots: TaskSlot[], path: string) {
  const identity = routeIdentity(path);
  const current = slots.slice().sort((a, b) => b.touchedAt - a.touchedAt).find(
    (slot) => routeIdentity(slot.current.path) === identity,
  );
  if (current) return { slot: current, index: -1, entry: current.current };
}
function readStored(storageKey: string): TaskSlot[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]");
    const raw = Array.isArray(parsed)
      ? parsed.filter(validEntry).map((entry, index) => ({
          id: `migrated-${entry.id}-${index}`,
          current: entry,
          backStack: [],
          touchedAt: Date.now(),
        }))
      : [2, 3].includes(parsed?.version) && Array.isArray(parsed.slots)
        ? parsed.slots
        : [];
    const valid: TaskSlot[] = raw
      .filter(
        (slot: TaskSlot) =>
          slot &&
          typeof slot.id === "string" &&
          validEntry(slot.current) &&
          Array.isArray(slot.backStack),
      )
      .map((slot: TaskSlot) => ({
        ...slot,
        backStack: trimStack(slot.backStack.filter(validEntry)),
        touchedAt: Number(slot.touchedAt) || 0,
      }));
    const seen = new Set<string>();
    return capSlots(
      valid
        .sort((a, b) => b.touchedAt - a.touchedAt)
        .filter((slot) => {
          const key = routeIdentity(slot.current.path);
          const duplicate = seen.has(key);
          seen.add(key);
          return (
            !duplicate ||
            [slot.current, ...slot.backStack].some(
              (entry) => entry.unsafeToClose,
            )
          );
        }),
    );
  } catch {
    return [];
  }
}
function cleanState(state: unknown): Record<string, unknown> {
  if (!state || typeof state !== "object") return {};
  const copy = { ...state } as TaskLocationState;
  delete copy.taskSlotId;
  delete copy.taskAction;
  return copy;
}
function safeHub(entry?: ActivityEntry) {
  return entry?.kind === "draft" || entry?.kind === "ai"
    ? "/authoring"
    : "/problems";
}
export function ActivityProvider({
  userId,
  children,
}: {
  userId: string;
  children: ReactNode;
}) {
  const storageKey = `oj-activities-${userId}`;
  const tombstoneKey = `oj-closed-task-slots-${userId}`;
  const location = useLocation();
  const navigate = useNavigate();
  const [slots, setSlots] = useState<TaskSlot[]>(() => readStored(storageKey));
  const slotsRef = useRef(slots);
  const locationRef = useRef(location);
  locationRef.current = location;
  const processedKeys = useRef(new Set<string>());
  const state = (location.state || {}) as TaskLocationState;
  const activeSlot = isTaskPath(location.pathname)
    ? slots.find(
        (slot) =>
          slot.id === state.taskSlotId &&
          routeIdentity(slot.current.path) === routeIdentity(location.pathname),
      )
    : undefined;
  const commit = useCallback((next: TaskSlot[]) => {
    slotsRef.current = next;
    setSlots(next);
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ version: STORAGE_VERSION, slots: slotsRef.current }),
      );
    } catch {
      /* Editors report backup failures separately. */
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
  const capture = useCallback(() => {
    const loc = locationRef.current;
    const id = (loc.state as TaskLocationState | null)?.taskSlotId;
    if (!isTaskPath(loc.pathname)) return;
    slotsRef.current = slotsRef.current.map((slot) =>
      slot.id === id
        ? {
            ...slot,
            current: {
              ...slot.current,
              scrollY: window.scrollY,
              navigationState: cleanState(loc.state),
            },
          }
        : slot,
    );
  }, []);
  useEffect(() => {
    const save = () => {
      capture();
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({ version: STORAGE_VERSION, slots: slotsRef.current }),
        );
      } catch {
        /* Best effort. */
      }
    };
    window.addEventListener("scroll", capture, { passive: true });
    window.addEventListener("pagehide", save);
    return () => {
      window.removeEventListener("scroll", capture);
      window.removeEventListener("pagehide", save);
    };
  }, [capture, storageKey]);
  const confirmLeave = useCallback(
    () =>
      !activeSlot?.current.unsafeToClose ||
      window.confirm(
        activeSlot.current.closeMessage ||
          "仍有内容未安全保存，确认离开当前页面？",
      ),
    [activeSlot],
  );
  useEffect(() => {
    const guardHub = (event: MouseEvent) => {
      if (
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor = (event.target as HTMLElement).closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        !anchor ||
        anchor.origin !== window.location.origin ||
        isTaskPath(anchor.pathname)
      )
        return;
      if (!confirmLeave()) {
        event.preventDefault();
        event.stopPropagation();
      } else capture();
    };
    const unload = (event: BeforeUnloadEvent) => {
      if (!activeSlot?.current.unsafeToClose) return;
      event.preventDefault();
      event.returnValue = "";
    };
    document.addEventListener("click", guardHub, true);
    window.addEventListener("beforeunload", unload);
    return () => {
      document.removeEventListener("click", guardHub, true);
      window.removeEventListener("beforeunload", unload);
    };
  }, [activeSlot, capture, confirmLeave]);
  const visit = useCallback(
    (slot: TaskSlot, path = slot.current.path, extra?: object) => {
      navigate(path, {
        replace: true,
        state: {
          ...slot.current.navigationState,
          ...extra,
          taskSlotId: slot.id,
          taskAction: "activate",
        },
      });
    },
    [navigate],
  );
  const restore = useCallback(
    (
      found: NonNullable<ReturnType<typeof findTask>>,
      to: string,
      extra?: object,
    ) => {
      if (
        found.index >= 0 &&
        [
          found.slot.current,
          ...found.slot.backStack.slice(found.index + 1),
        ].some((entry) => entry.unsafeToClose) &&
        !window.confirm("返回此页面前，仍有内容未安全保存，确认返回？")
      )
        return;
      const current = {
        ...found.entry,
        scrollY: to === found.entry.path ? found.entry.scrollY : undefined,
        path: to,
        navigationState: { ...found.entry.navigationState, ...extra },
      };
      const restored = {
        ...found.slot,
        current,
        touchedAt: Date.now(),
        backStack:
          found.index < 0
            ? found.slot.backStack
            : found.slot.backStack.slice(0, found.index),
      };
      commit(
        slotsRef.current.map((slot) =>
          slot.id === restored.id ? restored : slot,
        ),
      );
      visit(restored);
    },
    [commit, visit],
  );
  const register = useCallback(
    (entry: ActivityEntry) => {
      const loc = locationRef.current;
      const routeState = (loc.state || {}) as TaskLocationState;
      if (routeIdentity(entry.path) !== routeIdentity(loc.pathname)) return;
      const requestedId = routeState.taskSlotId;
      const existing = slotsRef.current.find((slot) => slot.id === requestedId);
      if (requestedId && !existing && closedIds().has(requestedId)) {
        navigate(safeHub(entry), { replace: true, state: {} });
        return;
      }
      const firstVisit = !processedKeys.current.has(loc.key);
      processedKeys.current.add(loc.key);
      if (processedKeys.current.size > 200)
        processedKeys.current.delete(
          processedKeys.current.values().next().value!,
        );
      if (!existing || routeState.taskAction === "new") {
        const found = findTask(slotsRef.current, entry.path);
        if (found) {
          restore(found, entry.path, cleanState(loc.state));
          return;
        }
        if (!firstVisit) return;
        const slot: TaskSlot = {
          id: crypto.randomUUID(),
          current: { ...entry, navigationState: cleanState(loc.state) },
          backStack: [],
          touchedAt: Date.now(),
        };
        commit(capSlots([slot, ...slotsRef.current], slot.id));
        visit(slot);
        return;
      }
      const same =
        routeIdentity(existing.current.path) === routeIdentity(entry.path);
      if (!same) {
        const found = findTask(slotsRef.current, entry.path);
        if (found) {
          restore(found, entry.path, cleanState(loc.state));
          return;
        }
      }
      const nextEntry = {
        ...(same ? existing.current : {}),
        ...entry,
        navigationState: cleanState(loc.state),
      };
      if (JSON.stringify(nextEntry) !== JSON.stringify(existing.current)) {
        commit(
          updateSlot(
            slotsRef.current,
            existing.id,
            nextEntry,
            firstVisit && routeState.taskAction === "push"
              ? "push"
              : "activate",
          ),
        );
      }
      if (
        firstVisit &&
        entry.kind !== "problem" &&
        ["activate", "back"].includes(routeState.taskAction || "")
      ) {
        const saved = nextEntry.scrollY;
        requestAnimationFrame(() => {
          if (
            locationRef.current.key === loc.key &&
            typeof saved === "number" &&
            Number.isFinite(saved)
          )
            window.scrollTo({ top: saved, behavior: "instant" });
        });
      }
    },
    [closedIds, commit, location.key, navigate, restore, visit],
  );
  const open = useCallback(
    (to: string, extra?: object) => {
      if (!confirmLeave()) return;
      capture();
      const found = findTask(slotsRef.current, to);
      if (found) {
        // A plain resource link restores the existing section; explicit query targets win.
        restore(found, to.includes("?") ? to : found.entry.path, extra);
        return;
      }
      navigate(to, {
        replace: !!activeSlot,
        state: {
          ...extra,
          taskSlotId: activeSlot?.id,
          taskAction: !activeSlot ? "new" : "push",
        },
      });
    },
    [activeSlot, capture, confirmLeave, navigate, restore],
  );
  const replaceCurrent = useCallback(
    (to: string, extra?: object) => {
      navigate(to, {
        replace: true,
        state: {
          ...cleanState(extra || locationRef.current.state),
          taskSlotId: (locationRef.current.state as TaskLocationState | null)
            ?.taskSlotId,
          taskAction: "replace",
        },
      });
    },
    [navigate],
  );
  const navigateInSlot = useCallback(
    (to: string, options?: { replace?: boolean; state?: object }) => {
      if (options?.replace) {
        if (confirmLeave()) replaceCurrent(to, options.state);
      } else open(to, options?.state);
    },
    [confirmLeave, open, replaceCurrent],
  );
  const openRoot = useCallback(
    (to: string, extra?: object) => open(to, extra),
    [open],
  );
  const activate = useCallback(
    (slot: TaskSlot) => {
      if (!confirmLeave()) return;
      capture();
      const latest = slotsRef.current.find((item) => item.id === slot.id);
      if (latest) {
        const touched = { ...latest, touchedAt: Date.now() };
        commit(
          slotsRef.current.map((item) =>
            item.id === latest.id ? touched : item,
          ),
        );
        visit(touched);
      }
    },
    [capture, commit, confirmLeave, visit],
  );
  const remove = useCallback(
    (id: string) => {
      const removed = slotsRef.current.filter(
        (slot) => slot.id === id || slot.current.id === id,
      );
      const historyEntries = slotsRef.current
        .flatMap((slot) => slot.backStack)
        .filter((entry) => entry.id === id);
      if (!removed.length && !historyEntries.length) return;
      if (
        (historyEntries.some((entry) => entry.unsafeToClose) ||
          removed.some((slot) =>
            [slot.current, ...slot.backStack].some(
              (entry) => entry.unsafeToClose,
            ),
          )) &&
        !window.confirm("仍有内容未安全保存，确认关闭此标签页？")
      )
        return;
      const ids = new Set(removed.map((slot) => slot.id));
      const next = slotsRef.current
        .filter((slot) => !ids.has(slot.id))
        .map((slot) => ({
          ...slot,
          backStack: slot.backStack.filter((entry) => entry.id !== id),
        }));
      commit(next);
      try {
        sessionStorage.setItem(
          tombstoneKey,
          JSON.stringify([...closedIds(), ...ids].slice(-200)),
        );
      } catch {
        /* Best effort. */
      }
      if (activeSlot && ids.has(activeSlot.id)) {
        const target = next
          .slice()
          .sort((a, b) => b.touchedAt - a.touchedAt)[0];
        if (target) visit(target);
        else
          navigate(safeHub(removed[0].current), { replace: true, state: {} });
      }
    },
    [activeSlot, closedIds, commit, navigate, tombstoneKey, visit],
  );
  const back = useCallback(() => {
    if (!activeSlot?.backStack.length || !confirmLeave()) return;
    const index = activeSlot.backStack.length - 1;
    const entry = activeSlot.backStack[index];
    // History is for Back only; never overwrite another open page to restore it.
    const found = findTask(slotsRef.current, entry.path);
    if (found) {
      capture();
      restore(found, found.entry.path);
      return;
    }
    const restored = {
      ...activeSlot,
      current: entry,
      backStack: activeSlot.backStack.slice(0, index),
      touchedAt: Date.now(),
    };
    commit(
      slotsRef.current.map((slot) =>
        slot.id === restored.id ? restored : slot,
      ),
    );
    navigate(entry.path, {
      replace: true,
      state: {
        ...entry.navigationState,
        taskSlotId: restored.id,
        taskAction: "back",
      },
    });
  }, [activeSlot, capture, commit, confirmLeave, navigate, restore]);
  const findEditingDraft = useCallback((id: string) => {
    const ordered = slotsRef.current
      .slice()
      .sort((a, b) => b.touchedAt - a.touchedAt);
    return ordered
      .map((slot) => slot.current)
      .find((entry) => entry.kind === "draft" && entry.baseProblemId === id);
  }, []);
  useEffect(() => {
    const sync = () => {
      let changed = false;
      const refresh = (entry: ActivityEntry): ActivityEntry => {
        const id = routeIdentity(entry.path).split("/").pop()!;
        const key =
          entry.kind === "ai"
            ? "task"
            : entry.kind === "draft"
              ? "draft"
              : entry.kind === "problem"
                ? "problem"
                : "submission";
        const data = queryClient.getQueryData<Record<string, any>>([key, id]);
        if (!data) return entry;
        let title = entry.title,
          status = entry.status;
        if (entry.kind === "problem" && data.title)
          title = `${id} · ${data.title}`;
        if (
          entry.kind === "draft" &&
          data.problem?.title &&
          entry.status !== "已在本机备份"
        )
          title = data.problem.title;
        if (entry.kind === "ai") status = data.progress || data.status;
        if (entry.kind === "submission" && !entry.id.startsWith("log:"))
          status = data.status === "pending" ? "评测中" : "已完成";
        if (title === entry.title && status === entry.status) return entry;
        changed = true;
        return { ...entry, title, status };
      };
      const next = slotsRef.current.map((slot) => ({
        ...slot,
        current: refresh(slot.current),
        backStack: slot.backStack.map(refresh),
      }));
      if (changed) commit(next);
    };
    let queued = false,
      disposed = false;
    const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" || event.action.type !== "success" || queued)
        return;
      queued = true;
      queueMicrotask(() => {
        queued = false;
        if (!disposed) sync();
      });
    });
    // Inactive running tasks share the exact page query keys. Active observers own their polling.
    const poll = async () => {
      if (document.visibilityState === "hidden") return;
      const entries = new Map(
        slotsRef.current
          .flatMap((slot) => [slot.current, ...slot.backStack])
          .filter(
            (entry) =>
              entry.kind === "ai" ||
              (entry.kind === "submission" && !entry.id.startsWith("log:")),
          )
          .map((entry) => [entry.path.split("?")[0], entry]),
      );
      for (const entry of [...entries.values()].slice(0, SLOT_LIMIT)) {
        if (disposed) return;
        const id = routeIdentity(entry.path).split("/").pop()!;
        const key = [entry.kind === "ai" ? "task" : "submission", id];
        const query = queryClient
          .getQueryCache()
          .find({ queryKey: key, exact: true });
        const data = query?.state.data as { status?: string } | undefined;
        if (
          query?.getObserversCount() ||
          query?.state.fetchStatus === "fetching" ||
          query?.state.status === "error"
        )
          continue;
        if (
          data?.status &&
          (entry.kind === "ai"
            ? ["completed", "failed", "cancelled"].includes(data.status)
            : data.status !== "pending")
        )
          continue;
        await queryClient
          .fetchQuery({
            queryKey: key,
            staleTime: 5000,
            queryFn: () =>
              api(
                entry.kind === "ai"
                  ? `/ai/problem-tasks/${id}`
                  : `/submissions/${id}?include_metadata=true`,
              ),
          })
          .catch(() => undefined);
      }
    };
    let polling = false;
    const tick = () => {
      if (!polling) {
        polling = true;
        void poll().finally(() => {
          polling = false;
        });
      }
    };
    const timer = window.setInterval(tick, 5000);
    return () => {
      disposed = true;
      unsubscribe();
      window.clearInterval(timer);
    };
  }, [commit]);
  const value = useMemo(
    () => ({
      slots,
      activeSlot,
      register,
      remove,
      activate,
      navigateInSlot,
      openRoot,
      replaceCurrent,
      back,
      confirmLeave,
      findEditingDraft,
    }),
    [
      slots,
      activeSlot,
      register,
      remove,
      activate,
      navigateInSlot,
      openRoot,
      replaceCurrent,
      back,
      confirmLeave,
      findEditingDraft,
    ],
  );
  return (
    <ActivityContext.Provider value={value}>
      {children}
    </ActivityContext.Provider>
  );
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
  const status =
    error && typeof error === "object" && "status" in error
      ? Number(error.status)
      : 0;
  useEffect(() => {
    if (
      ![403, 404].includes(status) ||
      !activeSlot ||
      handled.current === location.key
    )
      return;
    handled.current = location.key;
    if (activeSlot.backStack.length) back();
    else remove(activeSlot.id);
  }, [activeSlot, back, location.key, remove, status]);
}
export function TaskLink({ state, onClick, ...props }: LinkProps) {
  const { navigateInSlot } = useActivity();
  return (
    <Link
      {...props}
      state={state}
      onClick={(event) => {
        onClick?.(event);
        if (
          event.defaultPrevented ||
          props.target === "_blank" ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        )
          return;
        event.preventDefault();
        const to =
          typeof props.to === "string"
            ? props.to
            : `${props.to.pathname || ""}${props.to.search || ""}${props.to.hash || ""}`;
        navigateInSlot(to, { state });
      }}
    />
  );
}
export function TaskAction({
  label,
  to,
  resolve,
  state,
  onError,
  disabled = false,
}: {
  label: string;
  to?: string;
  resolve?: () => Promise<string>;
  state?: object;
  onError?: (error: unknown) => void;
  disabled?: boolean;
}) {
  const { navigateInSlot, confirmLeave } = useActivity();
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const run = async () => {
    if (pending.current || !confirmLeave()) return;
    pending.current = true;
    setBusy(true);
    try {
      const path = resolve ? await resolve() : to!;
      if (mounted.current) navigateInSlot(path, { state });
    } catch (error) {
      onError?.(error);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  return (
    <button
      className="button outline"
      type="button"
      disabled={disabled || busy}
      onClick={() => void run()}
    >
      {label}
    </button>
  );
}
export function ActivityBar() {
  const { slots, activeSlot, remove, activate } = useActivity();
  if (!slots.length) return null;
  const activeIndex = slots.findIndex((slot) => slot.id === activeSlot?.id);
  const visible =
    activeIndex >= 6
      ? [slots[activeIndex], ...slots.slice(0, 5)]
      : slots.slice(0, 6);
  const visibleIds = new Set(visible.map((slot) => slot.id));
  const overflow = slots.filter((slot) => !visibleIds.has(slot.id));
  const duplicate = slots.some((slot, index) =>
    slots
      .slice(0, index)
      .some(
        (other) =>
          routeIdentity(other.current.path) ===
          routeIdentity(slot.current.path),
      ),
  );
  const tab = (slot: TaskSlot, overflowRow = false) => (
    <div
      className={`${overflowRow ? "activity-overflow-row" : "activity-tab"}${slot.id === activeSlot?.id ? " active" : ""}`}
      key={slot.id}
    >
      <button
        type="button"
        className="activity-tab-target"
        aria-current={slot.id === activeSlot?.id ? "page" : undefined}
        onClick={() => activate(slot)}
        title={`${slot.current.title}${slot.current.status ? ` · ${slot.current.status}` : ""}`}
      >
        <Icon name={iconFor(slot.current.kind)} />
        <span>{slot.current.title}</span>
        {slot.current.status &&
          (overflowRow ? (
            <small>{slot.current.status}</small>
          ) : (
            <i aria-label={slot.current.status} />
          ))}
      </button>
      <button
        type="button"
        aria-label={`关闭 ${slot.current.title}`}
        onClick={() => remove(slot.id)}
      >
        <Icon name="close" />
      </button>
    </div>
  );
  return (
    <div className="activity-strip" aria-label="已打开的任务">
      <div className="activity-strip-inner">
        <span className="activity-label">已打开</span>
        <div className="activity-tabs">
          {visible.map((slot) => tab(slot))}
          {overflow.length > 0 && (
            <details className="activity-more">
              <summary>
                <Icon name="more" /> 更多 {overflow.length}
              </summary>
              <div>{overflow.map((slot) => tab(slot, true))}</div>
            </details>
          )}
        </div>
        {duplicate && (
          <small role="status">
            重复标签含未安全保存的内容，请检查后关闭。
          </small>
        )}
      </div>
    </div>
  );
}

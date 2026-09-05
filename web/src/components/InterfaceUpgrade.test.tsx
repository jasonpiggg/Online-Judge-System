import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ActivityBar, ActivityProvider, routeIdentity, updateSlot, useRegisterActivity, type TaskSlot } from "./Activity";
import { BackLink } from "./BackLink";
import { DiffView } from "./DiffView";
import { ErrorNotice } from "./ErrorNotice";
import { extractCodeSuggestion, extractCodeSuggestions } from "./AI";
import { useActionReveal } from "./useActionReveal";
import { DEFAULT_EDITOR_FONT_SIZE } from "../pages/Workspace";
import { authoringTaskOrigin, normalizeManagedPage } from "../pages/Authoring";
import { DisclosureCard } from "./DisclosureCard";
import { Button } from "./ui/button";

afterEach(cleanup);
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

function RegisteredTask({ unsafe = false }: { unsafe?: boolean }) {
  useRegisterActivity({
    id: "problem:p1",
    kind: "problem",
    title: "P1 · 测试题",
    path: "/problems/p1",
    status: "已保存",
    unsafeToClose: unsafe,
  });
  return <><BackLink /><ActivityBar /></>;
}

function RegisteredOverflowTask() {
  useRegisterActivity({
    id: "problem:7",
    kind: "problem",
    title: "P7",
    path: "/problems/7?tab=代码",
  });
  return <ActivityBar />;
}

describe("activity task tabs", () => {
  it("updates a slot in place and only pushes a different page", () => {
    const slots: TaskSlot[] = [{
      id: "slot-1",
      current: { id: "problem:p1", kind: "problem", title: "P1", path: "/problems/p1?tab=题目", status: "编辑中" },
      backStack: [],
      touchedAt: 1,
    }];
    const samePage = updateSlot(slots, "slot-1", { ...slots[0].current, path: "/problems/p1?tab=代码", status: "已保存" }, "replace", 2);
    expect(samePage[0].backStack).toHaveLength(0);
    expect(samePage[0].current.status).toBe("已保存");
    const nextPage = updateSlot(samePage, "slot-1", { id: "draft:1", kind: "draft", title: "草稿一", path: "/authoring/drafts/1" }, "push", 3);
    expect(nextPage[0].backStack).toHaveLength(1);
    expect(nextPage[0].current.title).toBe("草稿一");
  });

  it("adds and closes a safe task without deleting content", async () => {
    render(<MemoryRouter initialEntries={["/problems/p1"]}><ActivityProvider userId="7"><Routes><Route path="/problems/p1" element={<RegisteredTask />} /><Route path="/problems" element={<p>题库</p>} /></Routes></ActivityProvider></MemoryRouter>);
    expect(await screen.findByText("P1 · 测试题")).toBeInTheDocument();
    expect(document.querySelector(".back-link")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "关闭 P1 · 测试题" }));
    expect(screen.queryByText("P1 · 测试题")).not.toBeInTheDocument();
  });

  it("requires confirmation only when backup is unsafe", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<MemoryRouter><ActivityProvider userId="7"><RegisteredTask unsafe /></ActivityProvider></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "关闭 P1 · 测试题" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(screen.getByText("P1 · 测试题")).toBeInTheDocument();
    confirm.mockRestore();
  });

  it("ignores malformed local activity data", () => {
    localStorage.setItem("oj-activities-7", JSON.stringify({ unexpected: true }));
    render(<MemoryRouter><ActivityProvider userId="7"><ActivityBar /></ActivityProvider></MemoryRouter>);
    expect(screen.queryByLabelText("进行中的任务")).not.toBeInTheDocument();
  });

  it("normalizes transient query parameters", () => {
    expect(routeIdentity("/problems/p1?from=%2Fsubmissions&tab=代码")).toBe("/problems/p1");
  });

  it("promotes the current overflow task into the visible active tabs", () => {
    const slots = Array.from({ length: 8 }, (_, index) => ({
      id: `slot-${index}`,
      current: { id: `problem:${index}`, kind: "problem", title: `P${index}`, path: `/problems/${index}?tab=代码` },
      backStack: [],
      touchedAt: index,
    }));
    localStorage.setItem("oj-activities-7", JSON.stringify({ version: 2, slots }));
    const { container } = render(
      <MemoryRouter initialEntries={[{ pathname: "/problems/7", search: "?tab=代码", state: { taskSlotId: "slot-7", taskAction: "activate" } }]}>
        <ActivityProvider userId="7"><RegisteredOverflowTask /></ActivityProvider>
      </MemoryRouter>,
    );
    expect(container.querySelector(".activity-tab.active")?.textContent).toContain("P7");
  });
});

it("renders field differences in split and unified layouts", () => {
  render(<DiffView before={{ description: "求 a+b", testcases: [{ input: "1 2", output: "3" }] }} after={{ description: "求两个整数 a+b", testcases: [{ input: "2 3", output: "5" }] }} />);
  expect(screen.getByText("题目描述")).toBeInTheDocument();
  expect(document.querySelectorAll(".diff-add").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "单列" }));
  expect(document.querySelector(".diff-unified")).not.toBeNull();
});

it("keeps actionable errors", () => {
  render(<MemoryRouter><ErrorNotice message="permission denied" /></MemoryRouter>);
  expect(screen.getByText(/联系管理员/)).toBeInTheDocument();
});

function CurrentPath() {
  return <output aria-label="current-path">{useLocation().pathname}</output>;
}

function RegisteredBackTask() {
  useRegisterActivity({ id: "draft:1", kind: "draft", title: "草稿", path: "/authoring/drafts/1" });
  return <><BackLink /><CurrentPath /></>;
}

it("returns within the active task slot instead of browser history", async () => {
  localStorage.setItem("oj-activities-7", JSON.stringify({ version: 2, slots: [{
    id: "slot-1",
    current: { id: "draft:1", kind: "draft", title: "草稿", path: "/authoring/drafts/1" },
    backStack: [{ id: "problem:p1", kind: "problem", title: "P1 · 原题", path: "/problems/p1" }],
    touchedAt: 1,
  }] }));
  render(
    <MemoryRouter initialEntries={[{ pathname: "/authoring/drafts/1", state: { taskSlotId: "slot-1", taskAction: "activate" } }]}>
      <ActivityProvider userId="7"><RegisteredBackTask /></ActivityProvider>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "返回 P1 · 原题" }));
  expect(screen.getByLabelText("current-path")).toHaveTextContent("/problems/p1");
});

it("wraps disclosure content and keeps link and native buttons on shared sizes", () => {
  const { container } = render(
    <MemoryRouter>
      <DisclosureCard summary="高级设置" open><p>第一行内容</p></DisclosureCard>
      <div className="action-group">
        <Button asChild><a href="/target">链接操作</a></Button>
        <Button>原生操作</Button>
      </div>
    </MemoryRouter>,
  );
  expect(container.querySelector(".disclosure-content")?.textContent).toContain("第一行内容");
  expect(screen.getByRole("link", { name: "链接操作" })).toHaveClass("button");
  expect(screen.getByRole("button", { name: "原生操作" })).toHaveClass("button");
});

it("keeps unchanged lines between separate diff changes unhighlighted", () => {
  const { container } = render(<DiffView before={{ code: "old\nkeep this line\nold end\n" }} after={{ code: "new\nkeep this line\nnew end\n" }} />);
  expect(Array.from(container.querySelectorAll(".diff-remove,.diff-add")).map(node => node.textContent).join("")).not.toContain("keep this line");
});

it("does not mark every Windows line as changed against model LF output", () => {
  const { container } = render(<DiffView before={{ code: "import sys\r\nprint(1)" }} after={{ code: "import sys\nprint(2)" }} />);
  expect(Array.from(container.querySelectorAll(".diff-remove,.diff-add")).map(node => node.textContent).join("")).not.toContain("import sys");
});

describe("AI code review safeguards", () => {
  const current = "import sys\nvalue = int(sys.stdin.readline())\nprint(value)";

  it("offers an isolated snippet for review with a warning", () => {
    const suggestion = extractCodeSuggestion(
      "可以这样判断：\n```python\nprint(value)\n```",
      current,
      "python",
    );
    expect(suggestion?.code).toBe("print(value)");
    expect(suggestion?.canApply).toBe(true);
    expect(suggestion?.warnings).toContain("代码较短，可能只是讲解片段。覆盖前请确认它包含完整解法。");
    expect(extractCodeSuggestion("运行输出：\n```text\nAC\n```", current, "python")).toBeNull();
  });

  it("allows an explicitly requested complete executable replacement", () => {
    const suggestion = extractCodeSuggestion(
      "完整替换代码：\n```python\nimport sys\nvalue = int(sys.stdin.readline())\nprint(value + 1)\n```",
      current,
      "python",
    );
    expect(suggestion?.canApply).toBe(true);
  });

  it("returns every language-labelled candidate but ignores logs", () => {
    const candidates = extractCodeSuggestions(
      "```python\nprint(1)\n```\n```text\nAC\n```\n```cpp\nint main() { return 0; }\n```",
      "print(0)",
      "python",
    );
    expect(candidates.map((item) => item.language)).toEqual(["python", "cpp"]);
    expect(candidates[1].warnings.join(" ")).toMatch(/当前编辑器语言/);
  });
});

function RevealFixture() {
  const target = useActionReveal<HTMLElement>();
  return <><button onClick={target.reveal}>显示</button><section ref={target.ref}>详情</section></>;
}

describe("action reveal", () => {
  it("uses the 14px editor default and scrolls only on a user action", () => {
    expect(DEFAULT_EDITOR_FONT_SIZE).toBe(14);
    const scroll = vi.fn();
    HTMLElement.prototype.scrollIntoView = scroll;
    Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: false }) });
    render(<RevealFixture />);
    expect(scroll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "显示" }));
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(scroll).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });
  it("disables smooth motion when the operating system requests it", () => {
    const scroll = vi.fn();
    HTMLElement.prototype.scrollIntoView = scroll;
    Object.defineProperty(window, "matchMedia", { configurable: true, value: () => ({ matches: true }) });
    render(<RevealFixture />);
    fireEvent.click(screen.getByRole("button", { name: "显示" }));
    expect(scroll).toHaveBeenCalledWith({ behavior: "auto", block: "start" });
  });
});

describe("authoring list compatibility", () => {
  it("normalizes a legacy array without crashing the authoring page", () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({ id: index }));
    expect(normalizeManagedPage(rows, 2)).toEqual({
      items: [{ id: 10 }, { id: 11 }],
      total: 12,
      page: 2,
      pageSize: 10,
      legacy: true,
    });
  });

  it("normalizes the current metadata response", () => {
    expect(normalizeManagedPage({ drafts: [{ id: 1 }], total: 21, page: 3, page_size: 10 }, 3)).toEqual({
      items: [{ id: 1 }],
      total: 21,
      page: 3,
      pageSize: 10,
      legacy: false,
    });
  });
});

describe("AI authoring task origin", () => {
  it("prefers the immutable source draft and uses the review step when needed", () => {
    expect(authoringTaskOrigin({ source_draft_id: "draft-1", problem_id: "p1", action: "review" })).toEqual({
      path: "/authoring/drafts/draft-1?step=检查与发布",
      source: "draft",
      draftId: "draft-1",
    });
    expect(authoringTaskOrigin({ source_draft_id: "draft-1", problem_id: "p1", action: "generate" }).path).toBe("/authoring/drafts/draft-1");
  });

  it("falls back to the problem and then the authoring center", () => {
    expect(authoringTaskOrigin({ source_draft_id: null, problem_id: "p1", action: "generate" }).path).toBe("/problems/p1");
    expect(authoringTaskOrigin({ source_draft_id: null, action: "generate" })).toEqual({
      path: "/authoring",
      source: "authoring",
      draftId: undefined,
    });
  });
});

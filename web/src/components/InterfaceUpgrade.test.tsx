import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ActivityBar, ActivityProvider, upsertActivity, useRegisterActivity } from "./Activity";
import { BackLink } from "./BackLink";
import { DiffView } from "./DiffView";
import { ErrorNotice } from "./ErrorNotice";
import { extractCodeSuggestion } from "./AI";

afterEach(cleanup);
beforeEach(() => localStorage.clear());

function RegisteredTask({ unsafe = false }: { unsafe?: boolean }) {
  useRegisterActivity({
    id: "problem:p1",
    kind: "problem",
    title: "P1 · 测试题",
    path: "/problems/p1",
    status: "已保存",
    unsafeToClose: unsafe,
  });
  return <ActivityBar />;
}

describe("activity task tabs", () => {
  it("updates a task in place instead of moving the active tab to the left", () => {
    const entries = [
      { id: "draft:1", kind: "draft" as const, title: "草稿一", path: "/authoring/drafts/1", touchedAt: 1 },
      { id: "problem:p1", kind: "problem" as const, title: "P1", path: "/problems/p1", status: "编辑中", touchedAt: 2 },
    ];
    const updated = upsertActivity(entries, { ...entries[1], status: "已保存" });
    expect(updated.map((item) => item.id)).toEqual(["draft:1", "problem:p1"]);
    expect(updated[1].status).toBe("已保存");
  });

  it("adds and closes a safe task without deleting content", async () => {
    render(<MemoryRouter initialEntries={["/problems"]}><ActivityProvider userId="7"><RegisteredTask /></ActivityProvider></MemoryRouter>);
    expect(await screen.findByText("P1 · 测试题")).toBeInTheDocument();
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
});

it("renders field differences in split and unified layouts", () => {
  render(<DiffView before={{ description: "求 a+b", testcases: [{ input: "1 2", output: "3" }] }} after={{ description: "求两个整数 a+b", testcases: [{ input: "2 3", output: "5" }] }} />);
  expect(screen.getByText("题目描述")).toBeInTheDocument();
  expect(document.querySelectorAll(".diff-add").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "单列" }));
  expect(document.querySelector(".diff-unified")).not.toBeNull();
});

it("uses polished back navigation and actionable errors", () => {
  render(<MemoryRouter><BackLink to="/problems">返回题库</BackLink><ErrorNotice message="permission denied" /></MemoryRouter>);
  expect(screen.getByRole("link", { name: "返回题库" })).toHaveClass("back-link");
  expect(screen.getByText(/联系管理员/)).toBeInTheDocument();
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

  it("shows an isolated snippet without allowing it to replace the editor", () => {
    const suggestion = extractCodeSuggestion(
      "可以这样判断：\n```python\nprint(value)\n```",
      current,
      "分析本次评测",
    );
    expect(suggestion?.code).toBe("print(value)");
    expect(suggestion?.canApply).toBe(false);
    expect(suggestion?.reason).toMatch(/不会覆盖|禁止一键覆盖/);
    expect(extractCodeSuggestion("运行输出：\n```text\nAC\n```", current, "分析评测")).toBeNull();
  });

  it("allows an explicitly requested complete executable replacement", () => {
    const suggestion = extractCodeSuggestion(
      "完整替换代码：\n```python\nimport sys\nvalue = int(sys.stdin.readline())\nprint(value + 1)\n```",
      current,
      "请修复并给我完整代码",
    );
    expect(suggestion?.canApply).toBe(true);
  });
});

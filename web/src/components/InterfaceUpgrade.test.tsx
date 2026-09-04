import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ActivityBar, ActivityProvider, useRegisterActivity } from "./Activity";
import { BackLink } from "./BackLink";
import { DiffView } from "./DiffView";
import { ErrorNotice } from "./ErrorNotice";

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

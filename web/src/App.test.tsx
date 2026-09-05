import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { Login } from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function failedLogin(id: string, title: string, suggestion: string, status = 401) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    code: status,
    msg: id.replaceAll("_", " "),
    error: { id, title, suggestion },
  }), {
    status,
    headers: { "Content-Type": "application/json", ...(status === 429 ? { "Retry-After": "120" } : {}) },
  })));
}

it("shows a username-level error and moves focus for an unknown user", async () => {
  failedLogin("user_not_found", "用户不存在", "检查用户名是否正确，或先创建账户。");
  render(<MemoryRouter><Login /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "missing" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret1" } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByText("没有找到这个用户，请检查拼写。")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("用户名")).toHaveFocus());
  expect(screen.getByLabelText("密码")).toHaveValue("");
});

it("keeps rate-limit guidance visible without allowing duplicate submits", async () => {
  failedLogin("login_rate_limited", "登录尝试过于频繁", "请等待 120 秒后再试。", 429);
  render(<MemoryRouter><Login /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "wrongpw" } });
  fireEvent.submit(screen.getByRole("button", { name: "登录" }).closest("form")!);
  expect(await screen.findByRole("alert")).toHaveTextContent("请等待 120 秒后再试");
  expect(screen.getByRole("button", { name: "登录" })).not.toBeDisabled();
});

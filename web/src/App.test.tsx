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
  const retry = screen.getByRole("button", { name: "120 秒后重试" });
  expect(retry).toBeDisabled();
  fireEvent.submit(retry.closest("form")!);
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("validates login fields before requesting the server and uses one reveal control", () => {
  const request = vi.fn();
  vi.stubGlobal("fetch", request);
  render(<MemoryRouter><Login /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "a b" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "123" } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(screen.getByText("用户名不能包含空格或控制字符。")).toBeInTheDocument();
  expect(screen.getByText("密码至少需要 6 个字符。")).toBeInTheDocument();
  expect(request).not.toHaveBeenCalled();
  expect(screen.getAllByRole("button", { name: "显示密码" })).toHaveLength(1);
  expect(screen.queryByText("检查标红字段")).not.toBeInTheDocument();
});

it("maps server validation fields to their inputs", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    code: 400,
    msg: "invalid request parameters",
    error: {
      id: "validation_error",
      fields: [
        { field: "username", message: "用户名格式不正确。" },
        { field: "password", message: "密码格式不正确。" },
      ],
    },
  }), { status: 400, headers: { "Content-Type": "application/json" } })));
  render(<MemoryRouter><Login /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret1" } });
  fireEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByText("用户名格式不正确。")).toBeInTheDocument();
  expect(screen.getByText("密码格式不正确。")).toBeInTheDocument();
  expect(screen.getByLabelText("用户名")).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByLabelText("密码")).toHaveAttribute("aria-invalid", "true");
});

it("keeps registration reveal controls independent and clears related errors", () => {
  vi.stubGlobal("fetch", vi.fn());
  render(<MemoryRouter><Login /></MemoryRouter>);
  fireEvent.click(screen.getByRole("tab", { name: "注册" }));
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
  fireEvent.change(screen.getByLabelText("密码", { exact: true }), { target: { value: "secret1" } });
  fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "secret2" } });
  fireEvent.click(screen.getByRole("button", { name: "注册并登录" }));
  expect(screen.getByText("两次输入的密码不一致。")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
  expect(screen.getByLabelText("密码", { exact: true })).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("确认密码")).toHaveAttribute("type", "password");
  fireEvent.change(screen.getByLabelText("密码", { exact: true }), { target: { value: "secret2" } });
  expect(screen.queryByText("两次输入的密码不一致。")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "登录" }));
  expect(screen.getByLabelText("密码", { exact: true })).toHaveValue("");
  expect(screen.getByLabelText("密码", { exact: true })).toHaveAttribute("type", "password");
});

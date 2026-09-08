import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/problems");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admintestpassword");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "题库", exact: true })).toBeVisible();
});

test("unavailable public logs remain actionable and closing restores the resource hub", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ json: { ...body, data: { ...body.data, role: "user" } } });
  });
  for (const status of [403, 404, 422]) {
    await page.route("**/api/submissions/999999/log", (route) => route.fulfill({
      status, json: { msg: "日志不可查看" },
    }));
    await page.goto("/resources?tab=公开日志");
    await page.getByLabel("提交编号", { exact: true }).fill("999999");
    await page.getByRole("button", { name: "查看日志", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page).toHaveURL(/logs\/submissions\/999999/);
    await page.reload();
    await expect(page.getByRole("alert")).toBeVisible();
    await page.getByRole("button", { name: "关闭 日志 #999999" }).click();
    await expect(page).toHaveURL(/resources\?tab=/);
    await expect(page.getByRole("heading", { name: "查看公开评测日志" })).toBeVisible();
  }
});

test("audit controls align and language forms fill their disclosure on desktop and mobile", async ({ page }, info) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/admin?tab=访问审计");
    const input = page.getByLabel("审计题号");
    const button = page.getByRole("button", { name: "查询审计" });
    await expect(input).toBeVisible();
    if (width === 1440) {
      const a = (await input.boundingBox())!;
      const b = (await button.boundingBox())!;
      expect(Math.abs(a.y + a.height - b.y - b.height)).toBeLessThan(2);
    }
    await page.screenshot({ path: info.outputPath(`audit-${width}.png`) });
    await page.goto("/admin?tab=语言");
    await page.getByText("注册语言 / 更新配置", { exact: true }).click();
    const form = page.locator("form").filter({ has: page.getByRole("button", { name: "保存语言" }) });
    const field = form.getByLabel("运行命令", { exact: true });
    await expect(field).toBeVisible();
    expect(Math.abs((await form.boundingBox())!.width - (await field.boundingBox())!.width)).toBeLessThan(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`language-${width}.png`), fullPage: true });
  }
});

test("zero-score details align with code and closing restores filtered submissions after reload", async ({ page }, info) => {
  const submission = {
    submission_id: "42", user_id: 1, username: "admin", problem_id: "sum_2", language: "python", code: "print(0)",
    status: "success", score: 0, counts: 50, created_at: "2026-09-08T09:00:00Z",
    evaluation: { status: "success", verdict: "private", score: 0, max_score: 50,
      executed_cases: null, passed_cases: null, total_cases: null, all_passed: false, result_counts: {} },
  };
  await page.route("**/api/submissions/?*", (route) => route.fulfill({ json: { data: { total: 1, submissions: [submission] } } }));
  await page.route("**/api/submissions/42?*", (route) => route.fulfill({ json: { data: submission } }));
  await page.route("**/api/submissions/42/log", (route) => route.fulfill({ json: { data: { score: 0, counts: 50 } } }));
  await page.goto("/submissions?problem_id=sum_2");
  await page.getByRole("link", { name: "#42", exact: true }).click();
  await page.reload();
  const summary = page.locator(".evaluation-summary");
  await expect(summary).toBeVisible();
  await expect(summary.locator(".badge path")).toHaveAttribute("d", "m6 6 12 12M18 6 6 18");
  const code = page.locator(".page > .disclosure-card").filter({ hasText: "提交代码" });
  const a = (await summary.boundingBox())!;
  const b = (await code.boundingBox())!;
  expect(Math.abs(a.x - b.x)).toBeLessThan(2);
  expect(Math.abs(a.width - b.width)).toBeLessThan(2);
  await page.screenshot({ path: info.outputPath("submission.png"), fullPage: true });
  await page.getByRole("button", { name: "关闭 提交 #42" }).click();
  await expect(page).toHaveURL(/submissions\?problem_id=sum_2$/);
});


test("inline code remains legible in prose without changing fenced code backgrounds", async ({ page }, info) => {
  await page.route("**/api/problems/sum_2", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.data.description = "运算符 `+` 与 `-`，表达式 `expr → term (+|- term)*`。\n\n```python\nprint(1 + 2)\n```";
    await route.fulfill({ json: body });
  });
  await page.goto("/problems/sum_2");
  const code = page.locator(".markdown code").filter({ hasText: "expr → term" });
  await expect(code).toBeVisible();
  await expect(code).toHaveCSS("background-color", "rgb(227, 237, 255)");
  await expect(code).toHaveCSS("color", "rgb(23, 63, 122)");
  await expect(page.locator(".markdown pre code").first()).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await page.screenshot({ path: info.outputPath("inline-code.png") });
});

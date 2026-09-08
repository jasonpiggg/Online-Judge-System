import { test, expect, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/problems");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admintestpassword");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.locator(".problem-row").first()).toBeVisible();
}

for (const width of [1440, 1024, 390, 320]) {
  test(`polished navigation and record actions at ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 960 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await login(page);
    if (width <= 760) {
      const title = await page.locator(".problem-title").first().boundingBox();
      expect(title!.width).toBeGreaterThan(width - 100);
    }
    await page.getByLabel("搜索题目").fill("sum_2");
    await page.locator(".problem-row").filter({ hasText: "sum_2" }).click();
    await expect(page.locator(".statement-pane")).toBeVisible();
    if (width > 760) {
      const top = await page
        .locator(".statement-pane")
        .evaluate((el) => el.getBoundingClientRect().top + scrollY);
      expect(top).toBeLessThanOrEqual(300);
    }
    const summary = page.locator(".problem-actions-menu > summary");
    await summary.focus();
    await summary.press("Enter");
    await expect(
      page.getByRole("button", { name: "编辑题目", exact: true }),
    ).toBeVisible();
    const menu = await page.locator(".problem-actions").boundingBox();
    expect(menu!.x).toBeGreaterThanOrEqual(0);
    expect(menu!.x + menu!.width).toBeLessThanOrEqual(width);
    await summary.press("Escape");
    await expect(summary).toBeFocused();
    await expect(page.locator(".problem-actions-menu")).not.toHaveAttribute(
      "open",
    );
    if (width <= 760) {
      const sizes = await page.locator(".activity-tab").evaluateAll((tabs) =>
        tabs.map((tab) => ({
          outer: tab.getBoundingClientRect().height,
          controls: [...tab.querySelectorAll("button")].map(
            (button) => button.getBoundingClientRect().height,
          ),
        })),
      );
      for (const size of sizes)
        for (const control of size.controls) {
          expect(control).toBeGreaterThanOrEqual(44);
          expect(size.outer).toBeGreaterThanOrEqual(control);
        }
    }
    await expect(page.locator(".monaco-editor")).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`workspace-${width}.png`),
      fullPage: true,
    });
    // A separate owner avoids consuming the admin's per-problem submission quota.
    await page.request.post("/api/users/", {
      data: { username: `polish_${width}`, password: "polish-test-password" },
    });
    const owner = await page.context().request.post("/api/auth/login", {
      data: { username: `polish_${width}`, password: "polish-test-password" },
    });
    expect(owner.ok()).toBeTruthy();
    const response = await page.request.post("/api/submissions/", {
      data: {
        problem_id: "sum_2",
        language: "python",
        code: "a,b=map(int,input().split());print(a+b)",
      },
    });
    expect(response.ok()).toBeTruthy();
    const sid = (await response.json()).data.submission_id;
    await page.goto("/submissions");
    const record = page
      .locator("tbody tr")
      .filter({ has: page.getByText(`#${sid}`, { exact: true }) });
    await expect(record).toBeVisible();
    await expect(record.locator(".record-time")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBeTruthy();
    if (width <= 760) {
      for (const name of ["查看详情", "查看日志"]) {
        const link = record.getByRole("link", { name, exact: true });
        const box = await link.boundingBox();
        expect(box!.x).toBeGreaterThanOrEqual(0);
        expect(box!.x + box!.width).toBeLessThanOrEqual(width);
        expect(box!.height).toBeGreaterThanOrEqual(44);
      }
      await record.getByRole("link", { name: "查看详情", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/submissions/${sid}\\?`));
      await page.goto("/submissions");
    }
    await expect(record).toBeVisible();
    await page.screenshot({
      path: info.outputPath(`records-${width}.png`),
      fullPage: true,
    });
    await record.getByRole("link", { name: "查看日志", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/logs/submissions/${sid}\\?`));
    await expect(page.locator(".evaluation-summary")).toBeVisible();
    await page.request.post("/api/auth/login", {
      data: { username: "admin", password: "admintestpassword" },
    });
    await page.goto("/admin");
    if (width <= 760) {
      await page.getByLabel("管理类别").selectOption("语言");
      await expect(page).toHaveURL(/tab=/);
      await expect(
        page.getByText("注册语言 / 更新配置", { exact: true }),
      ).toBeVisible();
    }
  });
}

test("record states, empty results and errors stay readable at 320px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 960 });
  await login(page);
  let mode = "states";
  await page.route("**/api/submissions/?*", async (route) => {
    if (mode === "error")
      return route.fulfill({ status: 503, json: { detail: "记录暂时不可用" } });
    const submissions =
      mode === "empty"
        ? []
        : ["AC", "WA", "CE", "pending"].map((verdict, index) => ({
            submission_id: String(90001 + index),
            problem_id: "long_problem_identifier_".repeat(4),
            language: "python",
            status: verdict === "pending" ? "pending" : "success",
            score: 0,
            counts: 0,
            created_at: "2026-09-08T10:20:30Z",
            evaluation: { verdict },
          }));
    await route.fulfill({
      json: { data: { total: submissions.length, submissions } },
    });
  });
  await page.goto("/submissions");
  for (const text of ["全部通过", "答案错误", "编译失败", "正在评测"]) {
    await expect(page.getByText(text, { exact: true })).toBeVisible();
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await expect(
    page.getByRole("navigation", { name: "提交记录分页" }),
  ).toHaveCount(0);
  mode = "empty";
  await page.reload();
  await expect(
    page.getByText("没有匹配的提交记录。", { exact: false }),
  ).toBeVisible();
  mode = "error";
  await page.reload();
  await expect(page.getByRole("alert")).toBeVisible();
});

test("draft AI shortcut preserves unsaved metadata without starting a model task", async ({
  page,
}) => {
  await login(page);
  await page.goto("/problems/sum_2");
  await page.locator(".problem-actions-menu > summary").click();
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  await expect(page).toHaveURL(/authoring\/drafts/);
  const title = page.getByLabel("标题", { exact: true });
  await title.fill("未保存的标题 — 跳转验收");
  let calls = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/ai/"))
      calls++;
  });
  await page.getByText("AI 辅助当前草稿", { exact: true }).click();
  await expect(page.getByLabel("AI 修改要求")).toBeHidden();
  await page.getByRole("button", { name: "AI 辅助", exact: true }).click();
  await expect(page.getByLabel("AI 修改要求")).toBeInViewport();
  await expect(title).toHaveValue("未保存的标题 — 跳转验收");
  expect(calls).toBe(0);
});

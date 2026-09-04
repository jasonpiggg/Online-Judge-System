import { test, expect, type Page } from "@playwright/test";
async function login(page: Page) {
  await page.goto("/problems");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admintestpassword");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "题库", exact: true }),
  ).toBeVisible();
}
test("filter, navigate, edit, refresh, submit and inspect result", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("搜索题目").fill("sum_2");
  await page.locator(".problem-row").filter({ hasText: "sum_2" }).click();
  await expect(page.getByRole("heading", { name: "两数之和" })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("搜索题目")).toHaveValue("sum_2");
  await page.goForward();
  await expect(page.getByRole("heading", { name: "两数之和" })).toBeVisible();
  await page.locator(".monaco-editor").click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText("a,b=map(int,input().split());print(a+b)");
  await expect(page.locator(".view-lines")).toContainText("print");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator(".view-lines")).toContainText("print");
  await page.getByRole("button", { name: "提交评测", exact: true }).click();
  await expect(page.getByText("全部通过", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "查看提交详情 →" }).click();
  await expect(page.getByRole("heading", { name: /提交 #/ })).toBeVisible();
  await page.getByRole("link", { name: "返回题目继续修改" }).click();
  await expect(page.locator(".view-lines")).toContainText("print");
});
test("AI streams, restores after refresh and cancels without resubmission", async ({
  page,
}) => {
  await login(page);
  await page.goto("/problems/sum_2?tab=AI");
  await page.getByLabel("你的问题").fill("给我提示");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText("回答已完成", { exact: true })).toBeVisible();
  await expect(page.getByText("先检查输入：两个整数需要相加。")).toBeVisible();
  await page.reload();
  await expect(page.getByText("先检查输入：两个整数需要相加。")).toBeVisible();
  await page.getByLabel("你的问题").fill("模拟慢速回答");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "停止", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "停止", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "停止", exact: true }),
  ).toHaveCount(0);
});
test("author, verify, publish and open problem", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "命题中心", exact: true }).click();
  await page
    .getByLabel("命题需求")
    .fill("创建一道简单的整数求和题目，覆盖正负数和边界");
  await page.getByRole("button", { name: "开始生成", exact: true }).click();
  await expect(page.getByRole("link", { name: "打开已验证草稿" })).toBeVisible({
    timeout: 45000,
  });
  await page.getByRole("link", { name: "打开已验证草稿" }).click();
  await page.getByRole("button", { name: "检查与发布", exact: true }).click();
  await page.getByRole("button", { name: "发布题目", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "浏览器验收求和题", exact: true }),
  ).toBeVisible();
});
test("two tabs preserve both conflicting drafts and language switching", async ({
  page,
  context,
}) => {
  await login(page);
  await page.goto("/problems/sum_2");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  const other = await context.newPage();
  await other.goto("/problems/sum_2");
  await expect(other.getByText("已保存", { exact: true })).toBeVisible();
  async function edit(target: Page, code: string) {
    await target.locator(".monaco-editor").click();
    await target.keyboard.press("ControlOrMeta+A");
    await target.keyboard.insertText(code);
    await expect(target.locator(".view-lines")).toContainText(code);
  }
  await edit(page, "print('first tab')");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await edit(other, "print('second tab')");
  await expect(
    other.getByRole("heading", { name: "草稿在其他页面已更新" }),
  ).toBeVisible();
  await expect(other.locator(".notice")).toContainText("first tab");
  await expect(other.locator(".notice")).toContainText("second tab");
  await other.getByRole("button", { name: "使用云端版本" }).click();
  await expect(other.locator(".view-lines")).toContainText("first tab");
  const options = await other
    .getByLabel("编程语言")
    .locator("option")
    .evaluateAll((nodes) => nodes.map((n) => (n as HTMLOptionElement).value));
  await other
    .getByLabel("编程语言")
    .selectOption(options.find((v) => v !== "python")!);
  await expect(other.getByText("已保存", { exact: true })).toBeVisible();
  await other.getByLabel("编程语言").selectOption("python");
  await expect(other.locator(".view-lines")).toContainText("first tab");
  await other.close();
});
test("account switching never saves the previous user's code", async ({
  page,
  context,
}) => {
  await login(page);
  await page.goto("/problems/sum_2");
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await context.request.post("/api/users/", {
    data: { username: "browser_second", password: "browserpassword" },
  });
  await context.request.post("/api/auth/login", {
    data: { username: "browser_second", password: "browserpassword" },
  });
  await page.locator(".monaco-editor").click();
  await page.keyboard.insertText("old account secret");
  await expect(
    page.getByRole("heading", { name: "登录，继续练习" }),
  ).toBeVisible();
  const response = await context.request.get(
    "/api/workspace-drafts/sum_2/python",
  );
  expect((await response.json()).data).toBeNull();
});
test("edit existing problem and accept a scoped AI suggestion", async ({
  page,
}) => {
  await login(page);
  await page.goto("/problems/sum_2");
  await page.getByText("题目操作", { exact: true }).click();
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "两数之和",
  );
  await page.getByLabel("标题", { exact: true }).fill("草稿中的两数之和");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.locator(".sticky-actions")).toContainText("已同步");
  await page.getByLabel("AI 修改范围").selectOption("samples");
  await page
    .getByLabel("AI 修改要求")
    .fill("提供一个简单准确的新样例，保留其他内容。");
  await page.getByRole("button", { name: "开始", exact: true }).click();
  await expect(page.getByRole("button", { name: "采纳到草稿" })).toBeEnabled({
    timeout: 15000,
  });
  await page.getByRole("button", { name: "采纳到草稿" }).click();
  await page.getByRole("button", { name: "预览题面", exact: true }).click();
  await expect(page.locator(".statement")).toContainText("3 4");
});
for (const width of [1440, 1024, 390])
  test(`responsive layout ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await login(page);
    const problem = (
      await (await page.request.get("/api/problems/sum_2")).json()
    ).data;
    delete problem.limit_inheritance;
    const created = await page.request.post("/api/problems/", {
      data: {
        ...problem,
        id: `render_${width}`,
        description:
          problem.description +
          "\n\n$$a+b=c$$\n\n| 输入 | 含义 |\n|---|---|\n| a | 整数 |\n\n" +
          "长题面内容，保持可读。".repeat(50) +
          "\n\n```text\n" +
          "long_code_".repeat(100) +
          "\n```",
      },
    });
    expect(created.status()).toBe(200);
    await page.goto(`/problems/render_${width}`);
    await expect(page.getByRole("heading", { name: "两数之和" })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBeTruthy();
    await expect(page.locator(".katex")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`workspace-${width}.png`),
    });
    if (width === 390) {
      await page.getByRole("button", { name: "代码", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "提交评测" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "AI", exact: true }).click();
      await expect(page.getByLabel("你的问题")).toBeVisible();
    }
  });

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

test("login and registration preserve a protected deep link", async ({ page }, testInfo) => {
  await page.goto("/problems/sum_2");
  await expect(page.getByRole("tab", { name: "登录", exact: true })).toHaveAttribute("aria-selected", "true");
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`login-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("tab", { name: "登录", exact: true }).focus();
  await page.getByRole("tab", { name: "登录", exact: true }).press("ArrowRight");
  await expect(page.getByRole("tab", { name: "注册", exact: true })).toBeFocused();
  await expect(page.getByRole("heading", { name: "创建账户" })).toBeVisible();
  await page.getByLabel("用户名", { exact: true }).fill("login_ux_student");
  await page.getByLabel("密码", { exact: true }).fill("login-password");
  await page.getByLabel("确认密码", { exact: true }).fill("different-password");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page.getByRole("alert")).toContainText("密码不一致");
  await page.getByLabel("确认密码", { exact: true }).fill("login-password");
  await page.getByRole("button", { name: "显示密码" }).click();
  await expect(page.getByLabel("密码", { exact: true })).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "注册并登录" }).click();
  await expect(page).toHaveURL(/\/problems\/sum_2$/);
  await expect(page.getByRole("heading", { name: "两数之和" })).toBeVisible();

  await page.request.post("/api/auth/logout");
  await page.reload();
  await expect(page.getByRole("heading", { name: "登录，继续练习" })).toBeVisible();
  await page.getByLabel("用户名", { exact: true }).fill("login_ux_student");
  await page.getByLabel("密码", { exact: true }).fill("login-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/problems\/sum_2$/);
});

test("standard difficulty aliases, filtering, guide and draft persistence", async ({
  page,
}, testInfo) => {
  await login(page);
  expect(
    await page
      .locator("body")
      .evaluate((node) => getComputedStyle(node).fontSize),
  ).toBe("16px");
  const expected = [
    "全部难度",
    "入门",
    "简单",
    "中等",
    "困难",
    "挑战",
    "未分级",
  ];
  await expect(
    page.getByLabel("难度", { exact: true }).locator("option"),
  ).toHaveText(expected);
  await page.goto("/problems?difficulty=easy");
  await expect(page.getByLabel("难度", { exact: true })).toHaveValue("简单");
  await expect(page.locator(".problem-row")).toHaveCount(1);
  await expect(page.locator(".problem-row .difficulty")).toHaveText("简单");
  await page.getByLabel("难度", { exact: true }).selectOption("中等");
  await expect(page.locator(".problem-row .difficulty")).toHaveText("中等");
  await page.goBack();
  await expect(page.getByLabel("难度", { exact: true })).toHaveValue("简单");
  await page.locator(".difficulty-guide summary").click();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: testInfo.outputPath(`difficulty-${width}.png`),
    });
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.locator(".problem-row").click();
  await expect(page.locator(".work-heading .difficulty")).toHaveText("简单");
  await expect(page.getByText("题目操作", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "编辑题目", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "删除题目", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  const difficulty = page.getByLabel("难度", { exact: true });
  await expect(difficulty).toHaveValue("简单");
  await difficulty.selectOption("困难");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.locator(".sticky-actions")).toContainText("已同步");
  await page.reload();
  await expect(difficulty).toHaveValue("困难");
});

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
  await expect(page.getByRole("heading", { name: "本题提交记录" })).toBeVisible();
  await expect(page.locator(".submission-history-row.selected")).toContainText("全部通过");
  await page.getByRole("link", { name: "查看提交详情", exact: true }).click();
  await expect(page.getByRole("heading", { name: /提交 #/ })).toBeVisible();
  await page.getByRole("link", { name: "返回原题", exact: true }).click();
  await expect(page).toHaveURL(/\/problems\/sum_2\?submission=\d+&tab=%E7%BB%93%E6%9E%9C/);
  await expect(page.locator(".view-lines")).toContainText("print");
  await expect(page.locator(".submission-history-row.selected")).toBeVisible();
});

test("Chinese composition, URL restoration and vertical result controls", async ({
  page,
}) => {
  await login(page);
  const input = page.getByLabel("搜索题目");
  await input.dispatchEvent("compositionstart");
  await input.fill("kuohao");
  await page.waitForTimeout(350);
  expect(new URL(page.url()).searchParams.get("q")).toBeNull();
  await input.fill("括号");
  await input.dispatchEvent("compositionend", { data: "括号" });
  await expect(page).toHaveURL(/q=/);
  await expect(page.locator(".problem-row")).toHaveCount(1);
  await page.getByLabel("清空搜索").click();
  await expect(input).toHaveValue("");
  await page.goto("/problems/sum_2");
  const statement = await page.locator(".statement-pane").boundingBox();
  const editor = await page.locator(".code-area").boundingBox();
  expect(editor!.y).toBeGreaterThan(statement!.y + statement!.height);
  await page.locator(".monaco-editor").click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText("a,b=map(int,input().split());print(a-b)");
  await page.getByRole("button", { name: "提交评测", exact: true }).click();
  await expect(page.locator(".case-tile").first()).toBeVisible();
  await page.locator(".case-tile").first().click();
  await expect(page.locator(".case-detail")).toContainText("耗时");
  await expect(page.locator(".evaluation-numbers")).toContainText("得分");
});
test("AI streams, restores after refresh and cancels without resubmission", async ({
  page,
}, testInfo) => {
  await login(page);
  await page.goto("/problems/sum_2?tab=AI");
  await page.getByLabel("你的问题").fill("给我提示");
  await page.getByLabel("你的问题").press("Enter");
  await expect(page.getByText("回答已完成", { exact: true })).toBeVisible();
  await expect(page.getByText("先检查输入：两个整数需要相加。")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "输入提示", level: 3 }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText("先检查输入：两个整数需要相加。")).toBeVisible();
  await page.getByLabel("你的问题").fill("再给一步提示");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page.getByText("历史对话（1 轮）", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("给我提示", { exact: true })).not.toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("assistant-collapsed-history.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(
    page.getByText("已开始新对话，后续回答不会携带此前对话内容。"),
  ).toBeVisible();
  await expect(page.getByText("历史对话（1 轮）", { exact: true })).toHaveCount(
    0,
  );
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

test("authoring navigation tolerates a legacy list response", async ({ page }) => {
  await login(page);
  for (const pattern of ["**/api/problem-drafts/?**", "**/api/ai/problem-tasks/?**"]) {
    await page.route(pattern, async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      const data = body.data?.drafts ?? body.data?.tasks ?? body.data ?? [];
      await route.fulfill({ response, json: { ...body, data } });
    });
  }
  await page.getByRole("link", { name: "命题中心", exact: true }).click();
  await expect(page.getByRole("heading", { name: "命题中心", exact: true })).toBeVisible();
  await expect(page.getByText("命题中心已使用兼容模式打开")).toBeVisible();
});
test("incomplete draft saves and AI completes it", async ({ page }) => {
  await login(page);
  await page.goto("/authoring");
  await page.getByRole("button", { name: "手动创建题目" }).click();
  await page.getByLabel("题号", { exact: true }).fill("partial_browser");
  await page.getByLabel("标题", { exact: true }).fill("未完成的浏览器草稿");
  await page.getByLabel("来源", { exact: true }).fill("浏览器验收");
  await page.getByLabel("作者", { exact: true }).fill("课程用户");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.locator(".sticky-actions")).toContainText("已同步");
  await page.reload();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "未完成的浏览器草稿",
  );
  await expect(page.getByLabel("来源", { exact: true })).toHaveValue(
    "浏览器验收",
  );
  await expect(page.getByRole("button", { name: "生成局部修改" })).toBeDisabled();
  await expect(page.getByText(/此模式不会自动切换/)).toBeVisible();
  await page.getByRole("radio", { name: /补全整题并验证/ }).click();
  await page.getByRole("button", { name: "补全并验证整题", exact: true }).click();
  await expect(page.getByRole("link", { name: "打开已验证草稿" })).toBeVisible({
    timeout: 45000,
  });
});
test("manual draft uses repair links and basic verification without a reference", async ({
  page,
}) => {
  await login(page);
  const problem = (await (await page.request.get("/api/problems/sum_2")).json()).data;
  delete problem.limit_inheritance;
  const created = await page.request.post("/api/problem-drafts/", {
    data: {
      requirement: "手工题基础检查",
      problem: { ...problem, id: "basic_browser", title: "基础检查浏览器题" },
    },
  });
  expect(created.status()).toBe(200);
  const draftId = (await created.json()).data.id;
  await page.goto(`/authoring/drafts/${draftId}?step=${encodeURIComponent("检查与发布")}`);
  await expect(page.getByText(/还缺少：/)).toContainText("参考解");
  await page.getByRole("button", { name: "前往补充验证资产" }).click();
  await expect(page.getByRole("button", { name: "测试与解法", exact: true })).toHaveAttribute("aria-current", "step");
  await page.getByRole("button", { name: "检查与发布", exact: true }).click();
  await page.getByRole("button", { name: "运行基础检查", exact: true }).click();
  await expect(page.getByRole("link", { name: "打开已验证草稿" })).toBeVisible({ timeout: 45000 });
  await page.getByRole("link", { name: "打开已验证草稿" }).click();
  await expect(page.getByRole("heading", { name: "基础检查报告" })).toBeVisible();
  await expect(page.locator(".notice-inline").filter({ hasText: "未提供参考解" })).toBeVisible();
});
test("regular user manages experiment resources from the main navigation", async ({
  page,
}) => {
  await login(page);
  await page.request.post("/api/users/", {
    data: { username: "language_student", password: "language-password" },
  });
  await page.request.post("/api/auth/login", {
    data: { username: "language_student", password: "language-password" },
  });
  await page.goto("/resources");
  await expect(
    page.getByRole("heading", { name: "资源管理", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "主导航" })
      .getByRole("link", { name: "资源", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "主导航" })
      .getByRole("link", { name: "管理", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("管理题目搜索").fill("sum_2");
  await page
    .getByRole("row", { name: /sum_2/ })
    .getByRole("button", { name: "查看详情", exact: true })
    .click();
  const problemDetails = page.getByRole("region", { name: "题目详细信息" });
  await expect(problemDetails).toContainText("sum_2");
  await expect(problemDetails).toBeFocused();
  await expect(
    page.getByRole("button", { name: "编辑题目", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "删除题目", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "语言", exact: true }).click();
  await page.getByText("注册语言 / 更新配置", { exact: true }).click();
  await page.getByLabel("语言名称").fill("browserlang");
  await page.getByLabel("文件扩展名").fill(".txt");
  await page.getByLabel("运行命令").fill("python {src}");
  await page.getByRole("button", { name: "保存语言", exact: true }).click();
  await expect(page.getByText("语言配置已保存", { exact: true })).toBeVisible();
  await expect(page.locator("tbody")).toContainText("browserlang");
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
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "两数之和",
  );
  await page.getByLabel("标题", { exact: true }).fill("草稿中的两数之和");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.locator(".sticky-actions")).toContainText("已同步");
  await page.getByLabel("AI 局部修改范围").selectOption("samples");
  await page
    .getByLabel("AI 修改要求")
    .fill("提供一个简单准确的新样例，保留其他内容。");
  await page.getByRole("button", { name: "生成局部修改", exact: true }).click();
  await expect(page.getByRole("button", { name: "采纳到草稿" })).toBeEnabled({
    timeout: 15000,
  });
  await expect(page.locator(".diff-view")).toBeVisible();
  await page.getByRole("button", { name: "单列", exact: true }).click();
  await expect(page.locator(".diff-unified")).toBeVisible();
  await page.getByRole("button", { name: "采纳到草稿" }).click();
  await page.getByRole("button", { name: "预览题面", exact: true }).click();
  await expect(page.locator(".statement")).toContainText("3 4");
});

test("review mode produces an applicable patch and returns to its source draft", async ({
  page,
}) => {
  await login(page);
  await page.goto("/problems/sum_2");
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  await page.getByRole("radio", { name: /全面审查并修正/ }).click();
  await expect(page.getByRole("button", { name: "开始全面审查" })).toBeEnabled();
  const requirement = page.getByLabel("AI 修改要求");
  await requirement.fill("重点检查约束表达和已有测试资产");
  await requirement.press("Enter");
  await expect(page).toHaveURL(/\/authoring\/drafts\//);
  await requirement.press("ControlOrMeta+Enter");
  await expect(page.getByText("AI 全面审查", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByRole("link", { name: "返回原草稿" })).toHaveAttribute(
    "href",
    /\/authoring\/drafts\//,
  );
  await expect(page.locator(".diff-view")).toBeVisible();
  await page.getByRole("button", { name: "应用修改到草稿" }).click();
  await expect(page).toHaveURL(/\/authoring\/drafts\/.*step=/);
  const draftId = page.url().match(/\/authoring\/drafts\/([^?]+)/)?.[1];
  expect(draftId).toBeTruthy();
  const stored = await page.request.get(`/api/problem-drafts/${draftId}`);
  expect((await stored.json()).data.problem.constraints).toBe("|a|, |b| <= 10^9");
});

test("problem submission history paginates ten rows at a time", async ({ page }) => {
  await login(page);
  await page.route("**/api/submissions/?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("problem_id") !== "sum_2") {
      await route.continue();
      return;
    }
    const requestedPage = Number(url.searchParams.get("page") || "1");
    const all = Array.from({ length: 11 }, (_, index) => ({
      submission_id: String(9100 + index),
      problem_id: "sum_2",
      language: "python",
      status: "finished",
      score: 2,
      counts: 2,
      created_at: new Date(2026, 8, 5, 10, index).toISOString(),
      evaluation: {
        status: "finished",
        verdict: "AC",
        score: 2,
        max_score: 2,
        executed_cases: 2,
        passed_cases: 2,
        total_cases: 2,
        all_passed: true,
        result_counts: { AC: 2 },
      },
    }));
    const start = (requestedPage - 1) * 10;
    await route.fulfill({
      json: {
        status_code: 200,
        message: "success",
        data: {
          submissions: all.slice(start, start + 10),
          total: all.length,
          page: requestedPage,
          page_size: 10,
        },
      },
    });
  });
  await page.goto("/problems/sum_2?tab=%E7%BB%93%E6%9E%9C");
  await expect(page.locator(".submission-history-row")).toHaveCount(10);
  await page
    .getByRole("navigation", { name: "本题提交记录分页" })
    .getByRole("button", { name: "第 2 页" })
    .click();
  await expect(page.locator(".submission-history-row")).toHaveCount(1);
  await expect(page.locator(".submission-history-row")).toContainText("#9110");
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
    const statementBox = await page.locator(".statement-pane").boundingBox();
    const codeBox = await page.locator(".code-area").boundingBox();
    expect(codeBox!.y).toBeGreaterThan(statementBox!.y + statementBox!.height);
    if (width === 390) {
      await page.getByRole("button", { name: "代码", exact: true }).click();
      await expect(
        page.getByRole("button", { name: "提交评测" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "AI", exact: true }).click();
      await expect(page.getByLabel("你的问题")).toBeVisible();
    }
  });

test("visual acceptance across pages and result panels", async ({
  page,
}, testInfo) => {
  await login(page);
  const submitted = await page.request.post("/api/submissions/", {
    data: {
      problem_id: "sum_2",
      language: "python",
      code: "a,b=map(int,input().split());print(a+b)",
    },
  });
  expect(submitted.status()).toBe(200);
  const sid = (await submitted.json()).data.submission_id;
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 960 });
    for (const [label, route] of [
      ["library", "/problems"],
      ["workspace", "/problems/sum_2"],
      ["records", "/submissions"],
      ["authoring", "/authoring"],
      ["resources", "/resources"],
      ["account", "/account"],
      ["admin", "/admin"],
      ["result", `/submissions/${sid}`],
    ]) {
      await page.goto(route);
      await expect(page.locator("h1")).toBeVisible();
      if (label === "result")
        await expect(page.locator(".case-tile").first()).toBeVisible();
      if (label === "workspace")
        await expect(page.locator(".monaco-editor")).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBeTruthy();
      await page.screenshot({
        path: testInfo.outputPath(`${label}-${width}.png`),
        fullPage: true,
      });
    }
  }
});
test("library columns stay aligned with long identifiers and mobile navigation", async ({
  page,
}, testInfo) => {
  await login(page);
  const source = (await (await page.request.get("/api/problems/sum_2")).json())
    .data;
  delete source.limit_inheritance;
  const id = "long_identifier_".repeat(4);
  expect(
    (
      await page.request.post("/api/problems/", {
        data: { ...source, id, title: "较长题目标题与边界情况".repeat(5) },
      })
    ).status(),
  ).toBe(200);
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 960 });
    await page.goto("/problems");
    await expect(
      page.locator(".problem-row").filter({ hasText: id }),
    ).toBeVisible();
    const header = await page.locator(".list-head").evaluate((e) =>
      Array.from(e.children).map((c) => ({
        x: c.getBoundingClientRect().x,
        width: c.getBoundingClientRect().width,
      })),
    );
    const row = await page
      .locator(".problem-row")
      .filter({ hasText: id })
      .evaluate((e) =>
        Array.from(e.children).map((c) => ({
          x: c.getBoundingClientRect().x,
          width: c.getBoundingClientRect().width,
        })),
      );
    if (width > 760)
      for (const i of [0, 1])
        expect(Math.abs(header[i].x - row[i].x)).toBeLessThan(1);
    for (const i of [2, 3])
      expect(
        Math.abs(
          header[i].x + header[i].width / 2 - row[i].x - row[i].width / 2,
        ),
      ).toBeLessThan(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBeTruthy();
    for (const item of await page
      .getByRole("navigation", { name: "主导航" })
      .getByRole("link")
      .all())
      expect((await item.boundingBox())!.height).toBeGreaterThanOrEqual(36);
    await page.screenshot({
      path: testInfo.outputPath(`alignment-${width}.png`),
      fullPage: true,
    });
  }
});

test("administrator manages problems, users, submissions and audit through the UI", async ({
  page,
  playwright,
}, testInfo) => {
  await login(page);
  await expect(
    page
      .getByRole("navigation", { name: "主导航" })
      .getByRole("link", { name: "资源", exact: true }),
  ).toHaveCount(0);
  await page.goto("/resources");
  await expect(page.getByRole("heading", { name: "资源管理", exact: true })).toBeVisible();
  const username = "managed_student";
  const created = await page.request.post("/api/users/", {
    data: { username, password: "test-student-password" },
  });
  expect(created.status()).toBe(200);
  const uid = (await created.json()).data.user_id;
  const student = await playwright.request.newContext({
    baseURL: "http://127.0.0.1:8765",
  });
  await student.post("/api/auth/login", {
    data: { username, password: "test-student-password" },
  });
  const submission = await student.post("/api/submissions/", {
    data: {
      problem_id: "sum_2",
      language: "python",
      code: "a,b=map(int,input().split());print(a+b)",
    },
  });
  expect(submission.status()).toBe(200);
  const sid = (await submission.json()).data.submission_id;
  expect(
    (
      await student.get(
        "/api/submissions/?all_users=true&include_metadata=true",
      )
    ).status(),
  ).toBe(403);
  expect((await student.get("/api/logs/roles/")).status()).toBe(403);
  await page.goto("/admin");
  await page.getByLabel("搜索用户").fill(username);
  const row = page.locator("tbody tr").filter({ hasText: username });
  await row.getByRole("link", { name: "资料", exact: true }).click();
  const userProfile = page.getByRole("region", { name: "用户资料" });
  await expect(userProfile).toContainText(uid);
  await expect(userProfile).toBeFocused();
  await page.getByRole("link", { name: "查看此用户提交" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody")).toContainText(username);
  await page.getByRole("link", { name: `#${sid}`, exact: true }).click();
  await expect(
    page.locator(".code-block").filter({ hasText: "print(a+b)" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "重新评测", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "重新评测", exact: true }).click();
  await expect(page.locator(".case-tile").first()).toBeVisible();
  await page.getByRole("link", { name: "返回管理提交", exact: true }).click();
  await expect(page.getByLabel("提交用户 ID")).toHaveValue(uid);
  await page.reload();
  await expect(page.locator("tbody")).toContainText(username);
  const source = (await (await page.request.get("/api/problems/sum_2")).json())
    .data;
  delete source.limit_inheritance;
  expect(
    (
      await page.request.post("/api/problems/", {
        data: {
          ...source,
          id: "admin_details_case",
          time_limit: null,
          memory_limit: null,
        },
      })
    ).status(),
  ).toBe(200);
  await page.goto("/admin?tab=题目&problem_id=admin_details_case");
  const info = page.getByRole("region", { name: "题目详细信息" });
  await expect(info).toContainText("admin_details_case");
  await info.getByLabel("公开日志", { exact: true }).check();
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get("/api/problems/admin_details_case")
          ).json()
        ).data.public_cases,
    )
    .toBe(true);
  await info.getByText("完整题面与样例", { exact: true }).click();
  await expect(info.locator(".statement")).toContainText("输入格式");
  await info.getByRole("button", { name: "编辑题目", exact: true }).click();
  await expect(page.getByLabel("题号", { exact: true })).toHaveValue(
    "admin_details_case",
  );
  await page.goto(`/admin?tab=用户&user_id=${uid}`);
  const target = page.locator("tbody tr").filter({ hasText: username });
  await target.getByLabel(`${username}的角色`).selectOption("banned");
  await target.getByRole("button", { name: "保存", exact: true }).click();
  await expect(target.locator(".role-banned")).toHaveText("已禁用");
  await page.getByRole("button", { name: "角色审计", exact: true }).click();
  await expect(
    page.locator("tbody tr").filter({ hasText: username }),
  ).toContainText("已禁用");
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 960 });
    for (const [name, url] of [
      ["users", `/admin?tab=用户&user_id=${uid}`],
      ["submissions", `/admin?tab=提交&user_id=${uid}`],
      ["problems", "/admin?tab=题目&problem_id=admin_details_case"],
      ["roles", "/admin?tab=角色审计"],
    ]) {
      await page.goto(url);
      await expect(
        page.getByRole("heading", { name: "管理中心", exact: true }),
      ).toBeVisible();
      await expect(page.locator("tbody tr").first()).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
      ).toBeTruthy();
      await page.screenshot({
        path: testInfo.outputPath(`${name}-${width}.png`),
        fullPage: true,
      });
    }
  }
  await student.dispose();
});

test("browser-like activity tabs close safely and reopen on navigation", async ({ page }) => {
  await login(page);
  await page.goto("/problems/sum_2");
  await expect(page.getByLabel("进行中的任务")).toContainText("sum_2");
  await page.getByRole("button", { name: /关闭 sum_2/ }).click();
  await expect(page).toHaveURL(/\/problems$/);
  await expect(page.getByLabel("进行中的任务")).toHaveCount(0);
  await page.goto("/problems/sum_2");
  await expect(page.getByLabel("进行中的任务")).toContainText("sum_2");
  await page.goto("/problems/brackets");
  await expect(page.locator(".activity-tab > a span")).toHaveCount(2);
  await expect(page.getByLabel("进行中的任务")).toContainText("brackets");
  const before = await page.locator(".activity-tab > a span").allTextContents();
  await page.getByRole("link", { name: /sum_2 ·/ }).click();
  await expect(page).toHaveURL(/\/problems\/sum_2/);
  await expect.poll(() => page.locator(".activity-tab > a span").allTextContents()).toEqual(before);
});

test("AI code review warns on snippets, blocks stale edits, and supports undo", async ({ page }, testInfo) => {
  await login(page);
  await page.goto("/problems/sum_2?tab=代码");
  const original = "import sys\na, b = map(int, sys.stdin.readline().split())\nprint(a - b)";
  await page.locator(".monaco-editor").click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText(original);
  await page.getByRole("button", { name: "AI", exact: true }).click();
  await page.getByLabel("你的问题").fill("分析本次评测的单行建议");
  await page.getByLabel("你的问题").press("Enter");
  await expect(page.getByText("回答已完成", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /查看代码候选 1 差异/ }).click();
  await expect(page.locator(".diff-remove").first()).toBeVisible();
  await expect(page.getByText(/代码较短，可能只是讲解片段/)).toBeVisible();
  await expect(page.getByRole("button", { name: "确认覆盖编辑器" })).toBeEnabled();
  await expect(page.locator(".view-lines")).toContainText("a - b");
  await page.getByRole("button", { name: "关闭审查" }).click();
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByText("已开始新对话，后续回答不会携带此前对话内容。")).toBeVisible();
  await page.getByLabel("你的问题").fill("请给我完整代码用于代码审查验收");
  await page.getByLabel("你的问题").press("Enter");
  await expect(page.getByText("回答已完成", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /查看代码候选 1 差异/ }).click();
  await expect(page.getByRole("button", { name: "确认覆盖编辑器" })).toBeEnabled();
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 950 });
    await page.locator(".code-review-card").scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`code-review-${width}.png`) });
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.getByLabel("编程语言").selectOption("cpp");
  await expect(page.getByRole("button", { name: "确认覆盖编辑器" })).toBeDisabled();
  await page.getByLabel("编程语言").selectOption("python");
  await expect(page.getByRole("button", { name: "确认覆盖编辑器" })).toBeEnabled();
  await page.getByRole("button", { name: "确认覆盖编辑器" }).click();
  await expect(page.locator(".view-lines")).toContainText("a + b");
  await page.getByRole("button", { name: "撤销 AI 替换" }).click();
  await expect(page.locator(".view-lines")).toContainText("a - b");
  await page.getByRole("button", { name: /查看代码候选 1 差异/ }).click();
  await page.locator(".monaco-editor").click();
  await page.keyboard.press("ControlOrMeta+End");
  await page.keyboard.insertText("\n# keep my new edit");
  await expect(page.getByRole("button", { name: "确认覆盖编辑器" })).toBeDisabled();
});

test("content font and inset spacing remain readable across viewports", async ({ page }) => {
  await login(page);
  await page.goto("/problems/brackets?tab=代码");
  await expect(page.getByLabel("代码字号")).toHaveValue("14");
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.locator(".statement .markdown p").first().evaluate(node => getComputedStyle(node).fontSize)).toBe("16px");
    expect(await page.getByRole("button", { name: "提交评测", exact: true }).evaluate(node => getComputedStyle(node).fontSize)).toBe("14px");
    for (const selector of [".editor-toolbar", ".editor-footer"]) {
      const spacing = await page.locator(selector).evaluate(node => ({ padding: parseFloat(getComputedStyle(node).paddingLeft), gap: parseFloat(getComputedStyle(node).gap) }));
      expect(spacing.padding).toBeGreaterThanOrEqual(15);
      expect(spacing.gap).toBeGreaterThanOrEqual(12);
    }
  }
});

test("shared disclosures, action buttons and AI requirements keep consistent spacing", async ({ page }, testInfo) => {
  await login(page);
  await page.goto("/admin?tab=语言");
  await page.getByText("注册语言 / 更新配置", { exact: true }).click();
  const languageCard = page.locator(".disclosure-card").filter({ hasText: "注册语言 / 更新配置" });
  const summaryBox = (await languageCard.locator(":scope > summary").boundingBox())!;
  const firstFieldBox = (await languageCard.getByLabel("语言名称").boundingBox())!;
  const cardBox = (await languageCard.boundingBox())!;
  const saveBox = (await languageCard.getByRole("button", { name: "保存语言" }).boundingBox())!;
  expect(firstFieldBox.y - (summaryBox.y + summaryBox.height)).toBeGreaterThanOrEqual(14);
  expect(cardBox.y + cardBox.height - (saveBox.y + saveBox.height)).toBeGreaterThanOrEqual(14);

  await page.goto("/admin?tab=题目&problem_id=sum_2");
  const problemDetail = page.getByRole("region", { name: "题目详细信息" });
  await expect(problemDetail).toBeVisible();
  const heights = await problemDetail.locator(".action-group .button").evaluateAll((nodes) =>
    nodes.map((node) => Math.round(node.getBoundingClientRect().height)),
  );
  expect(heights.length).toBeGreaterThan(2);
  expect(new Set(heights).size).toBe(1);

  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  const requirement = page.getByLabel("AI 修改要求");
  await expect(requirement).toHaveJSProperty("tagName", "TEXTAREA");
  await expect(requirement).toHaveAttribute("rows", "4");
  const requirementBox = (await requirement.boundingBox())!;
  const actionBox = (await page.getByRole("button", { name: "生成局部修改" }).boundingBox())!;
  expect(actionBox.width).toBeLessThan(requirementBox.width);
  expect(actionBox.y).toBeGreaterThan(requirementBox.y + requirementBox.height);

  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`shared-spacing-${width}.png`), fullPage: true });
  }
});

test("failed local verification returns to the draft without paid regeneration", async ({ page }) => {
  await login(page);
  const problem = (await (await page.request.get("/api/problems/sum_2")).json()).data;
  delete problem.limit_inheritance;
  const created = await page.request.post("/api/problem-drafts/", { data: { problem } });
  const draftId = (await created.json()).data.id;
  const started = await page.request.post(`/api/problem-drafts/${draftId}/verify`);
  const taskId = (await started.json()).data.task_id;
  await page.goto(`/authoring/tasks/${taskId}`);
  await expect(page.getByText("本地验证未通过", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新生成", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "返回草稿修正并检查" }).click();
  await expect(page).toHaveURL(new RegExp(`/authoring/drafts/${draftId}`));
  await expect(page.getByRole("button", { name: "运行基础检查", exact: true })).toBeEnabled();
});

test("authoring lists paginate independently, archive, and recover a failed candidate", async ({ page }) => {
  await login(page);
  for (let index = 0; index < 11; index += 1) {
    const created = await page.request.post("/api/problem-drafts/", {
      data: { problem: { id: `page_${index}`, title: `分页草稿 ${index}` } },
    });
    expect(created.status()).toBe(200);
  }
  await page.goto("/authoring");
  await expect(page.getByRole("navigation", { name: "草稿分页" })).toBeVisible();
  await page.getByRole("navigation", { name: "草稿分页" }).getByRole("button", { name: "第 2 页" }).click();
  await expect(page).toHaveURL(/draft_page=2/);
  page.once("dialog", (dialog) => dialog.accept());
  await page.locator(".managed-row").filter({ has: page.getByText(/分页草稿/) }).first().getByRole("button", { name: "归档" }).click();

  await page.getByLabel("命题需求").fill("创建一道验收失败恢复的简易计算器题目");
  await page.getByRole("button", { name: "开始生成" }).click();
  await expect(page.getByText("可恢复的命题成果")).toBeVisible({ timeout: 45000 });
  await page.getByRole("button", { name: "将当前成果另存为草稿" }).click();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("浏览器验收求和题");
  await expect(page.getByText(/发布前仍须重新通过/)).toHaveCount(0);
});

test("regular user can view public case logs without private submission data", async ({
  page,
  playwright,
}) => {
  await login(page);
  expect((await page.request.put("/api/problems/sum_2/log_visibility", { data: { public_cases: false } })).status()).toBe(200);
  const author = await playwright.request.newContext({ baseURL: "http://127.0.0.1:8765" });
  await author.post("/api/users/", { data: { username: "public_log_author", password: "public-log-password" } });
  await author.post("/api/auth/login", { data: { username: "public_log_author", password: "public-log-password" } });
  const submitted = await author.post("/api/submissions/", { data: { problem_id: "sum_2", language: "python", code: "a,b=map(int,input().split());print(a+b)" } });
  const sid = (await submitted.json()).data.submission_id;
  await expect.poll(async () => (await (await author.get(`/api/submissions/${sid}`)).json()).data.status).not.toBe("pending");
  const viewer = await page.request.post("/api/users/", { data: { username: "public_log_viewer", password: "public-log-password" } });
  const viewerId = (await viewer.json()).data.user_id;
  await page.request.post("/api/auth/login", { data: { username: "public_log_viewer", password: "public-log-password" } });
  expect((await page.request.get(`/api/submissions/${sid}/log`)).status()).toBe(403);

  await page.request.post("/api/auth/login", { data: { username: "public_log_author", password: "public-log-password" } });
  await page.goto("/resources?tab=公开日志");
  await page.getByLabel("提交编号").fill(String(sid));
  await page.getByRole("button", { name: "查看日志", exact: true }).click();
  await expect(page.getByText("原始运行日志", { exact: true })).toBeVisible();

  await page.request.post("/api/auth/login", { data: { username: "admin", password: "admintestpassword" } });
  expect((await page.request.put("/api/problems/sum_2/log_visibility", { data: { public_cases: true } })).status()).toBe(200);
  await page.request.post("/api/auth/login", { data: { username: "public_log_viewer", password: "public-log-password" } });
  await page.goto("/resources?tab=公开日志");
  await page.getByLabel("提交编号").fill(String(sid));
  await page.getByRole("button", { name: "查看日志", exact: true }).click();
  await expect(page.locator(".case-tile").first()).toBeVisible();
  await expect(page.getByText(/不包含源码、隐藏输入/)).toBeVisible();
  await expect(page.getByText("原始运行日志", { exact: true })).toHaveCount(0);
  await expect(page.getByText("提交代码", { exact: true })).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("print(a+b)");
  await page.request.post("/api/auth/login", {
    data: { username: "admin", password: "admintestpassword" },
  });
  await page.goto("/resources?tab=公开日志");
  await page.getByLabel("提交编号").fill(String(sid));
  await page.getByRole("button", { name: "查看日志", exact: true }).click();
  await expect(page.getByText("原始运行日志", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /返回管理/ })).toHaveAttribute(
    "href",
    "/admin?tab=提交",
  );
  await page.goto("/admin?tab=访问审计");
  await page.getByLabel("审计用户 ID").fill(String(viewerId));
  await page.getByLabel("审计题号").fill("sum_2");
  await page.getByRole("button", { name: "查询审计", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`user_id=${viewerId}`));
  await expect(page.locator("tbody")).toContainText("拒绝访问 · 403");
  await expect(page.locator("tbody")).toContainText("允许访问 · 200");
  await author.dispose();
});

test("administrator pagination preserves a deep-linked page while data loads", async ({
  page,
}) => {
  await login(page);
  const prefix = `page_${Date.now()}`;
  for (let index = 0; index < 21; index += 1) {
    const response = await page.request.post("/api/users/", {
      data: {
        username: `${prefix}_${String(index).padStart(2, "0")}`,
        password: "test-pagination-password",
      },
    });
    expect(response.status()).toBe(200);
  }

  await page.goto("/admin?tab=用户&page=2");
  await expect(page.getByRole("button", { name: "第 2 页" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page).toHaveURL(/(?:\?|&)page=2(?:&|$)/);
});

test("administrator create-user and reset controls validate before mutation", async ({ page }) => {
  await login(page);
  await page.goto("/admin?tab=用户");
  const createCard = page.locator(".disclosure-card").filter({ hasText: "创建用户" });
  await createCard.getByText("创建用户", { exact: true }).click();
  await createCard.getByLabel("用户名", { exact: true }).fill("ui_created_student");
  await createCard.getByLabel("初始密码").fill("ui-created-password");
  await createCard.getByRole("combobox", { name: "角色" }).selectOption("user");
  await createCard.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("已保存");
  await page.getByLabel("搜索用户").fill("ui_created_student");
  await expect(page.locator("tbody")).toContainText("ui_created_student");

  await page.getByRole("button", { name: "系统设置", exact: true }).click();
  await page.getByText("恢复初始实验数据", { exact: true }).click();
  const reset = page.getByRole("button", { name: "重置数据", exact: true });
  await expect(reset).toBeDisabled();
  await page.getByLabel("重置确认").fill("WRONG");
  await expect(reset).toBeDisabled();
  await page.getByLabel("重置确认").fill("RESET");
  await expect(reset).toBeEnabled();
});

import { test, expect, type Page } from "@playwright/test";
async function showProblemActions(page: Page) {
  const menu = page.locator(".problem-actions-menu");
  await menu.waitFor({ state: "attached" });
  if (await menu.getAttribute("open") === null)
    await menu.locator("summary").first().click();
}
async function login(page: Page) {
  await page.goto("/problems");
  await page.getByLabel("用户名", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admintestpassword");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "题库", exact: true }),
  ).toBeVisible();
}
async function openProblem(page: Page) {
  await page.getByLabel("搜索题目").fill("sum_2");
  await page.locator(".problem-row").filter({ hasText: "sum_2" }).click();
  await expect(
    page.getByRole("heading", { name: "两数之和", exact: true }),
  ).toBeVisible();
}
test("reopening edit reuses its draft and tabs restore list context", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("搜索题目").fill("sum");
  await page.locator(".problem-row").filter({ hasText: "sum_2" }).click();
  const original = await page.evaluate(
    () => window.history.state.usr.ids.length as number,
  );
  await showProblemActions(page);
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  await expect(page).toHaveURL(/authoring\/drafts/);
  const draftUrl = new URL(page.url()).pathname;
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("link", { name: "题库", exact: true })
    .click();
  await expect(page.locator(".activity-tab.active")).toHaveCount(0);
  await openProblem(page);
  await showProblemActions(page);
  await page.getByRole("button", { name: "编辑题目", exact: true }).click();
  await expect.poll(() => new URL(page.url()).pathname).toBe(draftUrl);
  await expect(page.locator(".activity-tab")).toHaveCount(2);
  await page.getByRole("button", { name: /返回 sum_2/ }).click();
  // This reopening came from the filtered list, so the preserved context has one item.
  await expect(
    page.getByRole("button", { name: "下一题", exact: true }),
  ).toBeDisabled();
  expect(original).toBeGreaterThan(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "下一题", exact: true }),
  ).toBeDisabled();
});
test("search spacing, fixed navigation, fonts and upward scroll continuity", async ({
  page,
}, info) => {
  await login(page);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    const spacing = await page.locator(".search-field").evaluate((node) => {
      const input = node.querySelector("input")!;
      const icon = node.querySelector(".icon")!;
      return (
        input.getBoundingClientRect().left +
        parseFloat(getComputedStyle(input).paddingLeft) -
        icon.getBoundingClientRect().right
      );
    });
    expect(spacing).toBeGreaterThanOrEqual(6);
    await page.screenshot({
      path: info.outputPath(`search-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.getByLabel("搜索题目").fill("sum");
  await page.locator(".problem-row").filter({ hasText: "sum_2" }).click();
  const switcher = await page.locator(".problem-switcher").boundingBox();
  const nav = await page.locator(".work-nav").boundingBox();
  expect(switcher!.x + switcher!.width).toBeCloseTo(nav!.x + nav!.width, 0);
  await page.getByRole("button", { name: "代码", exact: true }).click();
  await expect
    .poll(() => new URL(page.url()).searchParams.get("tab"))
    .toBe("代码");
  await page.waitForTimeout(500);
  // Instrument all programmatic repositioning after the explicit jump has finished.
  await page.evaluate(() => {
    const state = window as unknown as { jumps: number };
    state.jumps = 0;
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (options) {
      state.jumps++;
      original.call(this, options);
    };
  });
  await page.mouse.move(80, 750);
  for (let i = 0; i < 12; i++) {
    await page.mouse.wheel(0, -90);
    await page.waitForTimeout(60);
  }
  expect(
    await page.evaluate(() => (window as unknown as { jumps: number }).jumps),
  ).toBe(0);
  await expect
    .poll(() => new URL(page.url()).searchParams.get("tab"))
    .toBe("题目");
  expect(
    await page.evaluate(async () => {
      await document.fonts.load('14px "JetBrains Mono"');
      return document.fonts.check('14px "JetBrains Mono"');
    }),
  ).toBeTruthy();
  await page.screenshot({
    path: info.outputPath("workspace-refined.png"),
    fullPage: true,
  });
});
test("code import supports Python, C++ and newly registered languages without reload", async ({
  page,
}) => {
  await login(page);
  await openProblem(page);
  const input = page.getByLabel("选择代码文件");
  await expect(input).toHaveAttribute("accept", /\.cpp/);
  const py = "# 中文\r\na,b=map(int,input().split());print(a+b)\r\n";
  await input.setInputFiles({
    name: "answer.PY",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("\ufeff" + py),
  });
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "确认替换代码" }).click();
  await expect(page.locator(".monaco-editor .view-lines")).toContainText(
    "print(a+b)",
  );
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  const cpp =
    "#include <iostream>\nint main(){int a,b; std::cin>>a>>b; std::cout<<a+b;}";
  await input.setInputFiles({
    name: "answer.cpp",
    mimeType: "text/plain",
    buffer: Buffer.from(cpp),
  });
  await expect(page.getByLabel("导入目标语言")).toHaveValue("cpp");
  await page.getByRole("button", { name: "确认替换代码" }).click();
  await expect(page.getByLabel("编程语言", { exact: true })).toHaveValue("cpp");
  await expect(page.locator(".monaco-editor .view-lines")).toContainText(
    "std::cout",
  );
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await page.getByLabel("编程语言", { exact: true }).selectOption("python");
  await expect(page.locator(".monaco-editor .view-lines")).toContainText(
    "print(a+b)",
  );
  const registration = await page.request.post("/api/languages/", {
    data: {
      name: "c_import",
      file_ext: ".c",
      compile_cmd: "gcc {src} -o {exe}",
      run_cmd: "{exe}",
      time_limit: 3,
      memory_limit: 128,
    },
  });
  expect([200, 409]).toContain(registration.status());
  await page.evaluate(() =>
    window.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(input).toHaveAttribute("accept", /\.c,/);
  await input.setInputFiles({
    name: "answer.c",
    mimeType: "text/plain",
    buffer: Buffer.from("int main(void) {return 0;}"),
  });
  await page.getByRole("button", { name: "确认替换代码" }).click();
  await expect(page.getByLabel("编程语言", { exact: true })).toHaveValue(
    "c_import",
  );
  await expect(page.locator(".monaco-editor .view-lines")).toContainText(
    "int main",
  );
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await page.getByLabel("编程语言", { exact: true }).selectOption("python");
  await expect(page.locator(".monaco-editor .view-lines")).toContainText(
    "print(a+b)",
  );
  await page.getByRole("button", { name: "提交评测", exact: true }).click();
  await expect(
    page
      .locator(".result .evaluation-summary")
      .getByText("全部通过", { exact: true }),
  ).toBeVisible();
});
test("JSON import creates a draft, rejects invalid fields and refuses existing IDs", async ({
  page,
}) => {
  await login(page);
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("link", { name: "命题中心", exact: true })
    .click();
  const input = page.getByLabel("选择题目 JSON");
  await input.setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from("[{}]"),
  });
  await expect(page.getByRole("alert")).toContainText("单道题目");
  await input.setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"title":"Invalid","status":"ready"}'),
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await input.setInputFiles({
    name: "exists.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"id":"sum_2"}'),
  });
  await expect(page.getByRole("alert")).toContainText("题号已存在");
  await input.setInputFiles({
    name: "new.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        id: "import_fixture",
        title: "文件导入测试",
        description: "可以继续补全",
      }),
    ),
  });
  await expect(page).toHaveURL(/authoring\/drafts/);
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "文件导入测试",
  );
});


test("import cancellation, ambiguous extensions and changed configuration preserve code", async ({ page }) => {
  await login(page); await openProblem(page);
  const original = "print('original backup')";
  await page.locator(".monaco-editor").click();
  await page.keyboard.press("ControlOrMeta+A"); await page.keyboard.insertText(original);
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  const input = page.getByLabel("选择代码文件");
  await input.setInputFiles({ name: "cancel.py", mimeType: "text/plain", buffer: Buffer.from("print('replacement')") });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.locator(".view-lines")).toContainText("original backup");
  let available = true;
  await page.route("**/api/languages/?include_metadata=true", async route => {
    const response = await route.fetch(); const body = await response.json();
    const base = body.data.languages.find((item: { name: string }) => item.name === "python");
    body.data.languages = available ? [...body.data.languages, { ...base, name: "alternative_python" }] : body.data.languages.filter((item: { name: string }) => item.name !== "python");
    body.data.name = body.data.languages.map((item: { name: string }) => item.name);
    await route.fulfill({ response, json: body });
  });
  await page.getByLabel("编程语言", { exact: true }).selectOption("cpp");
  await expect(page.getByRole("button", { name: "导入代码文件" })).toBeEnabled();
  await input.setInputFiles({ name: "choose.py", mimeType: "text/plain", buffer: Buffer.from("print('choose language')") });
  await expect(page.getByLabel("导入目标语言")).toHaveValue("");
  await expect(page.getByRole("button", { name: "确认替换代码" })).toBeDisabled();
  await page.getByLabel("导入目标语言").selectOption("python");
  available = false;
  await page.getByRole("button", { name: "确认替换代码" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("语言配置已变化");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.unroute("**/api/languages/?include_metadata=true");
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByLabel("编程语言", { exact: true }).getByRole("option", { name: "python", exact: true })).toHaveCount(1);
  await page.getByLabel("编程语言", { exact: true }).selectOption("python");
  await expect(page.locator(".view-lines")).toContainText("original backup");
});

test("current-page navigation has no opening menus and survives zoom", async ({page}) => {
  await login(page); await openProblem(page);
  await showProblemActions(page);
  await expect(page.locator(".task-action-menu")).toHaveCount(0);
  await page.getByRole("button", {name: "编辑题目", exact: true}).click();
  await expect(page).toHaveURL(/authoring\/drafts/);
  await expect(page.locator(".activity-tab")).toHaveCount(1);
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
});

test("draft JSON downloads unsaved fields and loads local files without saving", async ({ page }) => {
  await login(page);
  await page.goto("/authoring");
  await page.getByRole("button", { name: "手动创建题目" }).click();
  await page.getByLabel("题号", { exact: true }).fill("json_roundtrip");
  await page.getByLabel("标题", { exact: true }).fill("未保存的导出标题");
  await page.getByRole("button", { name: "检查与发布", exact: true }).click();
  await page.getByText("高级：JSON 导入与导出", { exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 JSON", exact: true }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe("json_roundtrip.json");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  const data = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  expect(data.title).toBe("未保存的导出标题");
  const draftUrl = page.url();
  const input = page.getByLabel("导入当前草稿 JSON");
  await input.setInputFiles({name: "bad.json", mimeType: "application/json", buffer: Buffer.from("[]")});
  await expect(page.locator(".problem-json [role=alert]")).toContainText("单道题目");
  await input.setInputFiles({name: "roundtrip.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify({...data, title: "本地导入标题"}))});
  await expect(page.getByText("已载入，保存后生效", { exact: true })).toBeVisible();
  expect(page.url()).toBe(draftUrl);
  await page.getByRole("button", { name: "题面与样例", exact: true }).click();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("本地导入标题");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.locator(".sticky-actions")).toContainText("已同步");
});

test("statement uses available width and assistant groups answers at desktop and mobile sizes", async ({ page }, info) => {
  await login(page);
  await page.goto("/problems/sum_2?tab=AI");
  await page.getByLabel("你的问题").fill("布局验收：解释输入格式");
  await page.getByLabel("你的问题").press("Enter");
  await expect(page.getByText("回答已完成", { exact: true })).toBeVisible();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    const pane = await page.locator(".statement-pane").boundingBox();
    const statement = await page.locator(".statement-pane .statement").boundingBox();
    expect(statement!.width / pane!.width).toBeGreaterThan(0.8);
    const intro = await page.locator(".assistant-intro").boundingBox();
    const quick = await page.locator(".assistant .quick-actions").boundingBox();
    expect(quick!.y - intro!.y - intro!.height).toBeGreaterThanOrEqual(12);
    expect(await page.locator(".current-answer .ai-answer-card").evaluate(node => getComputedStyle(node).borderLeftWidth)).toBe("3px");
    const status = await page.locator(".assistant .task-status").boundingBox();
    expect(status!.height).toBeLessThan(130);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await page.locator(".assistant-intro").scrollIntoViewIfNeeded();
    await page.locator(".assistant").screenshot({path: info.outputPath(`assistant-${width}.png`)});
    await page.locator(".statement-pane").screenshot({path: info.outputPath(`statement-${width}.png`)});
  }
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByText("已开始新对话，后续回答不会携带此前对话内容。", { exact: true })).toBeVisible();
});

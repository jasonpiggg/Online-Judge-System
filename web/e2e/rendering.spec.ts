import {test, expect, type Page} from "@playwright/test";
async function login(page: Page) {
  await page.goto("/problems");
  await page.getByLabel("用户名", {exact: true}).fill("admin");
  await page.getByLabel("密码", {exact: true}).fill("admintestpassword");
  await page.getByRole("button", {name: "登录", exact: true}).click();
  await expect(page.locator(".problem-row").first()).toBeVisible();
}
test("adjacent buttons and long diff panes retain spacing and scrolling", async ({page}, info) => {
  await login(page);
  await page.locator(".problem-row").first().click();
  const previous = page.getByRole("button", {name: "上一题", exact: true});
  const next = page.getByRole("link", {name: "下一题", exact: true});
  await expect(previous).toBeDisabled();
  const a = await previous.boundingBox(), b = await next.boundingBox();
  expect(Math.abs(a!.height - b!.height)).toBeLessThan(1);
  expect(Math.abs(a!.width - b!.width)).toBeLessThan(1);
  await page.goto("/problems/sum_2?tab=代码");
  await page.locator(".monaco-editor").click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText("# " + "old_comment ".repeat(35) + "END\nprint(0)");
  await page.getByRole("button", {name: "AI", exact: true}).click();
  await page.getByLabel("你的问题").fill("长行差异验收");
  await page.getByLabel("你的问题").press("Enter");
  await expect(page.locator(".current-answer .user-message")).toHaveText("长行差异验收");
  await expect(page.getByText("回答已完成", {exact: true})).toBeVisible();
  await page.getByRole("button", {name: /查看代码候选 1 差异/}).click();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    const diff = page.locator(".code-review-card .diff-view");
    const actions = page.locator(".code-review-card .review-actions");
    const d = await diff.boundingBox(), c = await actions.boundingBox();
    expect(c!.y - d!.y - d!.height).toBeGreaterThanOrEqual(15);
    for (const pane of await diff.locator(".diff-text").all()) {
      expect(await pane.evaluate(node => {
        const style = getComputedStyle(node);
        node.scrollLeft = node.scrollWidth;
        const visible = parseFloat(style.marginLeft) >= 12 && style.overflowX === "auto" && node.scrollLeft > 0;
        node.scrollLeft = 0;
        return visible;
      })).toBeTruthy();
    }
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    await page.locator(".code-review-card").screenshot({path: info.outputPath(`diff-${width}.png`)});
  }
  await page.getByRole("button", {name: "关闭审查"}).click();
  await page.getByRole("button", {name: "新对话", exact: true}).click();
});
test("empty compile messages are omitted and copy controls stay inside logs", async ({page}, info) => {
  await login(page);
  await page.route("**/api/submissions/987654?include_metadata=true", route => route.fulfill({json: {data: {
    submission_id: "987654", problem_id: "sum_2", language: "cpp", status: "success", code: "int main() {}", created_at: "2026-09-08",
    compile_info: {result: "success", message: ""}, run_info: {message: "5 test cases finished"},
    evaluation: {verdict: "AC", score: 50, max_score: 50, passed_cases: 5, total_cases: 5, all_passed: true},
  }}}));
  await page.route("**/api/submissions/987654/log", route => route.fulfill({json: {data: {score: 50, counts: 50, details: []}}}));
  await page.goto("/submissions/987654");
  await page.getByText("原始运行日志", {exact: true}).click();
  await expect(page.locator(".raw-logs .code-block")).toHaveCount(1);
  await expect(page.locator(".raw-logs")).toContainText("运行日志");
  for (const width of [1440, 320]) {
    await page.setViewportSize({width, height: 1000});
    const box = await page.locator(".raw-logs .code-block").boundingBox();
    const copy = await page.locator(".raw-logs .copy").boundingBox();
    expect(copy!.y).toBeGreaterThan(box!.y);
    expect(copy!.y + copy!.height).toBeLessThan(box!.y + box!.height);
    expect(copy!.x + copy!.width).toBeLessThan(box!.x + box!.width);
    await page.locator(".raw-logs").screenshot({path: info.outputPath(`logs-${width}.png`)});
  }
});

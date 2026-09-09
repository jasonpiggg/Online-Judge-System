import { test, expect, type Page } from '@playwright/test';

const api = 'http://127.0.0.1:18765';
async function authenticate(page: Page) {
  const response = await page.request.post(api + '/api/auth/login', {data:{username:'admin', password:'admintestpassword'}});
  expect(response.ok()).toBe(true);
}

async function healthy(page: Page) {
  await expect(page.getByTestId('stException')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  // Check the actual content surface, not just the browser root.
  expect(await page.getByTestId('stMain').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
}

for (const width of [1440, 1024, 390, 320]) {
  test(`all final Streamlit surfaces at ${width}px`, async ({page}, info) => {
    test.setTimeout(120000);
    await page.setViewportSize({width,height:1000});
    await page.goto('/');
    await expect(page.getByRole('button',{name:'进入工作台',exact:true})).toBeVisible();
    await healthy(page);
    await page.screenshot({path:info.outputPath(`login-${width}.png`)});
    await authenticate(page);
    const problem = (await (await page.request.get(api+'/api/problems/sum_2')).json()).data;
    delete problem.limit_inheritance;
    const draft = (await (await page.request.post(api+'/api/problem-drafts/',{data:{problem}})).json()).data;
    // Different seeded problems keep fast CI runs below the real per-problem rate limit.
    const submissionProblem = ['sum_2','arithmetic_expression','brackets','coin_change'][[1440,1024,390,320].indexOf(width)];
    const submissionResponse = await page.request.post(api+'/api/submissions/',{data:{problem_id:submissionProblem,language:'python',code:'print(0)'}});
    expect(submissionResponse.ok()).toBe(true);
    const submission = (await submissionResponse.json()).data;
    const task = (await (await page.request.post(api+`/api/problem-drafts/${draft.id}/verify`,{data:{mode:'basic'},headers:{'Idempotency-Key':`design-${width}-${Date.now()}`}})).json()).data;
    const surfaces = [
      ['library','/','题库'], ['records','/records','提交记录'],
      ['authoring','/ai','命题中心'], ['resources','/resources','管理中心'],
      ['profile','/profile','个人账户'], ['admin','/admin','管理中心'],
      ['language','/resources?section='+encodeURIComponent('语言'),'管理中心'],
      ['workspace','/workspace?id=sum_2&language=python','两数之和'],
      ['draft',`/draft?id=${draft.id}`,'两数之和'],
      ['editor','/editor','新建题目'],
      ['submission',`/submission?id=${submission.submission_id}`,`提交 #${submission.submission_id}`],
      ['public-log',`/public_log?id=${submission.submission_id}`,'公开评测日志'],
      ['task',`/ai_task?id=${task.task_id}`,'AI 任务'],
    ];
    for (const [name,url,heading] of surfaces) {
      await page.goto(url);
      await expect(page.getByRole('heading',{name:heading,exact:true}).first()).toBeVisible();
      await healthy(page);
      if(name==='library') {
        const brand = await page.locator('.st-key-brand-bar').boundingBox();
        const header = await page.getByTestId('stHeader').boundingBox();
        expect(brand!.y).toBeGreaterThanOrEqual(header!.y+header!.height+12);
        if(width>760) {
          const nav = await page.getByTestId('stTopNavLink').first().boundingBox();
          expect(Math.abs(nav!.x-brand!.x)).toBeLessThanOrEqual(8);
        }
      }
      if(name==='library' && width<=760) await expect(page.getByText('筛选与题目管理',{exact:true})).toBeVisible();
      if(name==='admin' && width<=760) await expect(page.getByRole('combobox',{name:'管理模块',exact:true})).toBeVisible();
      if(name==='profile') await expect(page.getByRole('button',{name:'退出登录',exact:true})).toBeVisible();
      await page.screenshot({path:info.outputPath(`${name}-${width}.png`)});
      if(name==='workspace') {
        await expect(page.getByRole('textbox',{name:'向助手提问',exact:true})).toHaveCount(0);
        await page.locator('.st-key-section-nav').getByRole('link',{name:'代码',exact:true}).click();
        await expect.poll(async () => (await page.locator('.st-key-section-nav').boundingBox())!.y).toBeGreaterThanOrEqual(50);
        const nav = await page.locator('.st-key-section-nav').boundingBox();
        expect(nav!.y).toBeLessThan(100);
        const code = await page.getByRole('heading',{name:'代码',exact:true}).boundingBox();
        expect(code!.y).toBeGreaterThanOrEqual(nav!.y+nav!.height);
        await page.screenshot({path:info.outputPath(`editor-panel-${width}.png`)});
        await page.getByText('AI 做题助手',{exact:true}).click();
        await expect(page.getByRole('button',{name:'给我一个渐进提示',exact:true})).toBeVisible();
        await healthy(page);
        await page.screenshot({path:info.outputPath(`assistant-${width}.png`)});
      }
    }
  });
}

test('untouched draft leaves without a false dirty warning, literal edits remain protected', async ({page}) => {
  await authenticate(page);
  const draft = (await (await page.request.post(api+'/api/problem-drafts/',{data:{problem:{title:'Untouched draft'}}})).json()).data;
  await page.goto(`/draft?id=${draft.id}`);
  await expect(page.getByText('已保存',{exact:true})).toBeVisible();
  const dialogs: string[] = [];
  page.on('dialog', async dialog => {dialogs.push(dialog.message()); await dialog.dismiss();});
  await page.getByRole('button',{name:'返回来源',exact:true}).click();
  await expect(page.getByRole('heading',{name:'题库',exact:true})).toBeVisible();
  expect(dialogs).toEqual([]);
  await page.goto(`/draft?id=${draft.id}`);
  const title = page.getByRole('textbox',{name:'题目标题',exact:true});
  await title.fill('Actual edit'); await title.press('Tab');
  await expect(page.getByText('有未保存修改',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'返回来源',exact:true}).click();
  await expect(title).toHaveValue('Actual edit');
  expect(dialogs).toHaveLength(1);
});

test('returning home or to origin deselects tasks and reopening selects the saved detail',async({page})=>{
  await authenticate(page);
  await page.goto('/workspace?id=sum_2&language=python');
  const active = page.locator('.st-key-task-strip').getByRole('button',{name:'两数之和',exact:true}).and(page.locator('[kind="primary"]'));
  await expect(active).toHaveCount(1);
  await page.getByRole('button',{name:'返回来源',exact:true}).click();
  await expect(page.getByRole('heading',{name:'题库',exact:true})).toBeVisible();
  await expect(active).toHaveCount(0);
  await expect(page.getByRole('button',{name:'关闭当前任务',exact:true})).toBeDisabled();
  await page.locator('.st-key-task-strip').getByRole('button',{name:'两数之和',exact:true}).click();
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  await expect(active).toHaveCount(1);
  await page.getByTestId('stTopNavLink').filter({hasText:'题库'}).click();
  await expect(page.getByRole('heading',{name:'题库',exact:true})).toBeVisible();
  await expect(active).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('button',{name:'关闭当前任务',exact:true})).toBeDisabled();
  await page.setViewportSize({width:390,height:1000});
  await expect(page.getByRole('combobox',{name:'进行中的任务',exact:true})).toHaveValue('选择任务');
});

test('forty tasks remain bounded and inactive pages cannot close an unrelated task',async({page})=>{
  await authenticate(page);
  await page.addInitScript(() => {
    sessionStorage.setItem('oj-streamlit-tab','design-forty');
    localStorage.setItem('oj-streamlit-ui:1:design-forty', JSON.stringify(Array.from({length:40},(_,i)=>({key:`task-${i}`,title:`长标题任务 ${i} · 检查导航宽度与任务切换`, current:{page:'workspace',params:{id:`test-${i}`}},origin:{page:'library',params:{}},history:[]}))));
  });
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'题库',exact:true})).toBeVisible();
  await expect(page.locator('.st-key-task-strip').getByRole('button', {name:/长标题任务/})).toHaveCount(40);
  await expect(page.getByRole('button',{name:'关闭当前任务',exact:true})).toBeDisabled();
  await healthy(page);
  await page.setViewportSize({width:320,height:1000});
  await expect(page.getByRole('combobox',{name:'进行中的任务',exact:true})).toBeVisible();
  await healthy(page);
});

test('multiline sample edits enter the dirty payload and survive browser recovery',async({page})=>{
  await authenticate(page);
  const draft = (await (await page.request.post(api+'/api/problem-drafts/',{data:{problem:{title:'Multiline recovery',samples:[{input:'1 2',output:'3'}]}}})).json()).data;
  await page.goto(`/draft?id=${draft.id}`);
  await page.getByRole('tab',{name:'样例',exact:true}).click();
  await page.getByText('逐项编辑样例（支持多行）',{exact:true}).click();
  const input = page.getByRole('textbox',{name:'输入',exact:true});
  await input.fill('  1 2\n\n'); await input.press('Tab');
  await expect(page.getByText('有未保存修改',{exact:true})).toBeVisible();
  await expect.poll(() => page.evaluate(() => Object.entries(localStorage).some(([key,value])=>key.startsWith('oj-streamlit-draft:') && value.includes('  1 2\\n\\n')))).toBe(true);
  page.on('dialog',dialog=>dialog.accept());
  await page.reload();
  await page.getByRole('button',{name:'载入浏览器草稿',exact:true}).click();
  await expect(page.getByRole('button',{name:'载入浏览器草稿',exact:true})).toHaveCount(0);
  await expect(page.getByText('有未保存修改',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get(api+'/api/problem-drafts/'+draft.id)).json()).data.problem.samples[0].input).toBe('  1 2\n\n');
  await healthy(page);
});

test('account page logout has one active authentication bridge',async({page})=>{
  await authenticate(page);
  await page.goto('/profile');
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  await expect(page.getByRole('button',{name:'进入工作台',exact:true})).toBeVisible();
  await expect(page.getByTestId('stException')).toHaveCount(0);
  expect((await page.request.get(api+'/api/auth/me')).status()).toBe(401);
});

test('long library titles and tags wrap and empty search remains actionable',async({page})=>{
  await authenticate(page);
  const problem = (await (await page.request.get(api+'/api/problems/sum_2')).json()).data;
  delete problem.limit_inheritance;
  const id = 'design_long_'+Date.now();
  const title = '跨越多个边界条件的长题目名称与解法分析'.repeat(4);
  expect((await page.request.post(api+'/api/problems/',{data:{...problem,id,title,tags:['动态规划','边界条件','字符串','递归','图论','数论']}})).ok()).toBe(true);
  for(const width of [1440,320]) {
    await page.setViewportSize({width,height:1000});
    await page.goto('/?q='+id);
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await healthy(page);
  }
  await page.goto('/?q=does-not-exist-'+id);
  await expect(page.getByText('没有找到匹配的题目。试试其他关键词，或创建第一道题。',{exact:true})).toBeVisible();
  await healthy(page);
});


test('login chrome, bottom pager and clear-all task navigation', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('button',{name:'进入工作台',exact:true})).toBeVisible();
  await expect(page.getByTestId('stTopNavLink')).toHaveCount(0);
  await expect(page.getByRole('checkbox',{name:'显示密码',exact:true})).toHaveCount(0);
  await authenticate(page);
  await page.goto('/resources');
  const bottom = page.locator('.st-key-pagination-page-bottom');
  await expect(page.locator('.st-key-pagination-page-top')).toHaveCount(0);
  await expect(bottom).toBeAttached();
  await bottom.getByRole('spinbutton',{name:'跳转至',exact:true}).fill('2');
  await bottom.getByRole('button',{name:'跳转',exact:true}).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(bottom.getByText(/第 2 \/ /)).toBeVisible();
  await bottom.getByRole('button',{name:'首页',exact:true}).click();
  await expect(page).toHaveURL(/page=1/);
  await page.goto('/workspace?id=sum_2');
  await expect(page.getByRole('button',{name:'关闭当前任务',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'一键清空任务标签',exact:true}).click();
  await expect(page.getByRole('heading',{name:'题库',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.locator('.st-key-task-bar')).toHaveCount(0);
  await healthy(page);
});


test('empty histories have no pagers and password feedback is actionable', async ({page}) => {
  const username = `password_${Date.now()}`;
  expect((await page.request.post(api+'/api/users/',{data:{username,password:'original123'}})).ok()).toBe(true);
  expect((await page.request.post(api+'/api/auth/login',{data:{username,password:'original123'}})).ok()).toBe(true);
  await page.goto('/workspace?id=sum_2');
  await page.getByText('本题提交历史',{exact:true}).click();
  await expect(page.getByText('暂无本题提交记录，提交代码后可在这里查看。',{exact:true})).toBeVisible();
  await expect(page.locator('.st-key-pager-page-top')).toHaveCount(0);
  await expect(page.locator('.st-key-pagination-page-bottom')).toHaveCount(0);
  await page.goto('/profile');
  await page.getByText('修改密码',{exact:true}).click();
  const submit = page.getByRole('button',{name:'更新密码',exact:true});
  const current = page.getByRole('textbox',{name:'当前密码',exact:true});
  const password = page.getByRole('textbox',{name:'新密码',exact:true});
  const confirm = page.getByRole('textbox',{name:'确认新密码',exact:true});
  await submit.click();
  await expect(page.getByText('请输入当前密码。',{exact:true})).toBeVisible();
  await current.fill('original123'); await submit.click();
  await expect(page.getByText('请输入新密码。',{exact:true})).toBeVisible();
  for (const [old,next,confirmation,message] of [
    ['original123','replacement123','','请再次输入新密码以确认。'],
    ['original123','original123','original123','新密码不能与当前密码相同，请设置不同的新密码。'],
    ['wrong123','replacement123','replacement123','当前密码不正确'],
    ['original123','replacement123','replacement123','密码已更新，其他设备已退出登录。'],
  ]) {
    await current.fill(old); await password.fill(next); await confirm.fill(confirmation);
    await submit.click();
    await expect(page.getByText(message,{exact:true})).toBeVisible();
  }
  expect((await page.request.get(api+'/api/auth/me')).ok()).toBe(true);
  await healthy(page);
});


test('admin panels render in place, retain origins, and reference titles are searchable', async ({page}) => {
  await authenticate(page);
  await page.goto('/admin');
  await expect(page.getByTestId('stTopNavLink').filter({hasText:'资源'})).toHaveCount(0);
  const panels = [
    ['用户', '搜索用户名或用户 ID'], ['角色审计', '还没有角色修改记录。'],
    ['全站提交', '查询'], ['题目管理', '搜索题号或标题'],
    ['语言', '注册评测语言'], ['公开日志', '公开提交 ID'],
    ['访问审计', '查询访问审计'], ['系统设置', '实验环境'],
  ];
  for (const [section, content] of panels) {
    await page.getByRole('radio').filter({hasText: new RegExp('^'+section+'$')}).click();
    await expect(page.getByText(content,{exact:true}).first()).toBeVisible();
    expect(new URL(page.url()).pathname).toBe('/admin');
    await healthy(page);
  }
  await page.goto('/admin?section='+encodeURIComponent('题目管理'));
  const search = page.getByRole('textbox',{name:'搜索题号或标题',exact:true});
  await search.fill('sum_2'); await search.press('Enter');
  await expect(page.getByRole('button',{name:'编辑题目',exact:true})).toHaveCount(1);
  await page.getByRole('button',{name:'编辑题目',exact:true}).click();
  await expect(page.getByRole('heading',{name:'两数之和',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'返回来源',exact:true}).click();
  await expect(search).toHaveValue('sum_2');
  expect(new URL(page.url()).pathname).toBe('/admin');
  await page.goto('/ai');
  await page.getByRole('tab',{name:'生成整题',exact:true}).click();
  const reference = page.getByRole('combobox',{name:'参考题目（可选）',exact:true});
  await reference.click();
  await expect(page.getByRole('option',{name:'不参考已有题目',exact:true})).toBeVisible();
  await reference.fill('两数之和');
  await page.getByRole('option',{name:'sum_2 · 两数之和',exact:true}).click();
  await expect(reference).toHaveValue('sum_2 · 两数之和');
});


test('ordinary users retain the resource navigation and legacy resource content', async ({page}) => {
  const username = 'resource_user_'+Date.now();
  await authenticate(page);
  expect((await page.request.post(api+'/api/users/',{data:{username,password:'password1'}})).ok()).toBe(true);
  expect((await page.request.post(api+'/api/auth/login',{data:{username,password:'password1'}})).ok()).toBe(true);
  await page.goto('/resources');
  await expect(page.getByRole('heading',{name:'资源',exact:true})).toBeVisible();
  await expect(page.getByTestId('stTopNavLink').filter({hasText:'资源'})).toBeVisible();
  await expect(page.getByTestId('stTopNavLink').filter({hasText:'管理中心'})).toHaveCount(0);
  await expect(page.getByRole('textbox',{name:'搜索题号或标题',exact:true})).toBeVisible();
  expect((await page.request.get(api+'/api/users/')).status()).toBe(403);
});

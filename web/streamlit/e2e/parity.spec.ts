import { test, expect, type Page } from '@playwright/test';
const api = 'http://127.0.0.1:18765';
const unique = (prefix:string) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2,6)}`;
async function login(page:Page, path='/') {
  const response = await page.request.post(api+'/api/auth/login',{data:{username:'admin',password:'admintestpassword'},maxRetries:2});
  expect(response.ok()).toBe(true);
  await page.goto(path);
  await expect(page.getByRole('heading',{name:'题库',exact:true})).toBeVisible();
}
async function openWorkspace(page:Page) {
  await login(page);
  await page.goto('/workspace?id=sum_2&language=python');
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  await expect(page.locator('.monaco-editor textarea')).toBeVisible();
}
async function code(page:Page,text:string) {
  await page.locator('.monaco-editor').click();
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.insertText(text);
  if (text.split('\n')[0].length < 200) await expect(page.locator('.view-lines')).toContainText(text.split('\n')[0]);
  await page.waitForTimeout(700);
}
async function source(page:Page) {
  const r = await page.request.get(api+'/api/workspace-drafts/sum_2/python');
  const p = await r.json();
  return p.data ? {...p.data, code:p.data.code.replace(/\r\n/g,'\n')} : p.data;
}
async function noException(page:Page) { await expect(page.locator('[data-testid="stException"]')).toHaveCount(0); }

test('browser registration preserves a protected deep link and HttpOnly identity after reload', async({page,context})=>{
  await page.goto('/workspace?id=sum_2&language=python');
  await page.getByRole('tab',{name:'注册',exact:true}).click();
  const form = page.getByRole('tabpanel').filter({visible:true});
  await form.getByRole('textbox',{name:'用户名',exact:true}).fill(unique('streamlit'));
  await form.getByRole('textbox',{name:'密码',exact:true}).fill('password1');
  await form.getByRole('textbox',{name:'确认密码',exact:true}).fill('password1');
  await form.getByRole('button',{name:'注册',exact:true}).click();
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  expect(page.url()).toContain('id=sum_2');
  const cookie = (await context.cookies()).find(c=>c.name==='oj_session');
  expect(cookie?.httpOnly).toBe(true);
  expect(await page.evaluate(()=>document.cookie)).not.toContain('oj_session');
  await page.reload();
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('password1');
  await noException(page);
});

test('registration confirmation and UTF-8 byte boundary are validated before authentication',async({page})=>{
  await page.goto('/');
  await page.getByRole('tab',{name:'注册',exact:true}).click();
  const form = page.getByRole('tabpanel').filter({visible:true});
  await form.getByRole('textbox',{name:'用户名',exact:true}).fill(unique('validation'));
  await form.getByRole('textbox',{name:'密码',exact:true}).fill('汉'.repeat(25));
  await form.getByRole('textbox',{name:'确认密码',exact:true}).fill('汉'.repeat(25));
  await form.getByRole('button',{name:'注册',exact:true}).click();
  await expect(page.getByText(/72.*UTF-8|UTF-8.*72/)).toBeVisible();
  await form.getByRole('textbox',{name:'密码',exact:true}).fill('password');
  await form.getByRole('button',{name:'注册',exact:true}).click();
  await expect(page.getByText('两次输入的密码不一致。')).toBeVisible();
});

test('local editor and Markdown controls load without a runtime CDN',async({page})=>{
  const external:string[] = [], missing:string[]=[];
  page.on('request', request=>{ const u=new URL(request.url()); if(!['127.0.0.1','localhost'].includes(u.hostname) && u.protocol.startsWith('http')) external.push(request.url()); });
  page.on('response', response=>{ if(response.status()===404) missing.push(response.url()); });
  await openWorkspace(page);
  await page.waitForTimeout(1000);
  expect(external).toEqual([]);
  // Streamlit probes the deep-link prefix before discovering the root server path.
  expect(missing.filter(url=>!url.endsWith('favicon.ico') && !/\/workspace\/_stcore\/(health|host-config)$/.test(url))).toEqual([]);
  await noException(page);
});

test('Monaco autosaves, refresh restores, source import and submission detail work',async({page})=>{
  await openWorkspace(page);
  const text = '# streamlit autosave\na,b=map(int,input().split())\nprint(a+b)\n';
  await code(page,text);
  await expect.poll(async()=> (await source(page))?.code).toBe(text);
  await page.reload();
  await expect(page.locator('.monaco-editor')).toContainText('streamlit autosave');
  await page.getByRole('button',{name:'提交评测',exact:true}).click();
  await expect(page.getByRole('heading',{name:'评测结果',exact:true})).toBeVisible();
  await page.getByText('本题提交历史',{exact:true}).click();
  await page.locator('[class*=st-key-history-card-]').getByRole('button',{name:'查看详情',exact:true}).first().click();
  await expect(page.getByRole('heading',{name:/提交 #/})).toBeVisible();
  await expect(page.getByText('本次提交代码',{exact:true})).toBeVisible();
  await noException(page);
});

test('two tabs retain both conflicting sources and explicitly resolve revisions',async({page,context})=>{
  await openWorkspace(page);
  const other = await context.newPage();
  await other.goto('/workspace?id=sum_2&language=python');
  await expect(other.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  const first = '# first '+unique('revision');
  const second = '# second '+unique('revision');
  await code(page,first);
  await expect.poll(async()=> (await source(page))?.code).toBe(first);
  await code(other,second);
  await expect(other.getByText('另一页面已保存新版本。请选择要保留的内容；覆盖时仍会检查版本。')).toBeVisible();
  await expect(other.locator('.diff-view')).toContainText(first);
  await expect(other.locator('.diff-view')).toContainText(second);
  await other.getByRole('button',{name:'保留本地并保存',exact:true}).click();
  await expect.poll(async()=> (await source(page))?.code).toBe(second);
  await noException(other);
});

test('assistant streams history, reviews code, blocks stale suggestions and starts new topics',async({page})=>{
  await openWorkspace(page);
  const baseline = '# assistant baseline '+unique('base');
  await code(page,baseline);
  await expect.poll(async()=> (await source(page))?.code).toBe(baseline);
  await page.getByText('AI 做题助手',{exact:true}).click();
  await page.getByRole('textbox',{name:'向助手提问',exact:true}).fill('请给我完整代码用于代码审查验收');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'采纳代码',exact:true})).toBeVisible();
  await expect(page.locator('.diff-view')).toContainText('import sys');
  await page.getByText('已检查 Diff，确认替换整份源码',{exact:true}).click();
  await expect(page.getByRole('checkbox',{name:'已检查 Diff，确认替换整份源码'})).toBeChecked();
  await page.getByRole('button',{name:'采纳代码',exact:true}).click();
  await expect.poll(async()=> (await source(page))?.code).toContain('import sys');
  await page.getByRole('button',{name:'撤销最近一次采纳',exact:true}).click();
  await expect.poll(async()=> (await source(page))?.code).toBe(baseline);
  await expect(page.locator('.view-lines')).toContainText(baseline);
  await code(page,baseline+'\n# changed');
  await expect.poll(async()=> (await source(page))?.code).toBe(baseline+'\n# changed');
  await page.getByText('已检查 Diff，确认替换整份源码',{exact:true}).click();
  await expect(page.getByRole('button',{name:'采纳代码',exact:true})).toBeDisabled();
  await page.reload();
  await page.getByText('AI 做题助手',{exact:true}).click();
  await page.getByText('历史问答',{exact:true}).click();
  await page.locator('summary').filter({hasText:'请给我完整代码'}).click();
  await page.getByRole('button',{name:'打开回答',exact:true}).first().click();
  await expect(page.getByText(/源码或语言已变化/)).toBeVisible();
  await page.getByRole('button',{name:'新话题',exact:true}).click();
  await expect(page.getByRole('button',{name:'打开回答',exact:true})).toHaveCount(0);
  await noException(page);
});

test('incomplete drafts save, export unsaved fields, restore revisions and reject stale review application',async({page})=>{
  await login(page);
  await page.getByRole('button',{name:/新建题目/}).click();
  await page.getByRole('textbox',{name:'题号',exact:true}).fill(unique('draft'));
  await page.getByRole('textbox',{name:'题目标题',exact:true}).fill('未完成草稿');
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  const did = new URL(page.url()).searchParams.get('id');
  await expect.poll(async()=> (await (await page.request.get(api+'/api/problem-drafts/'+did)).json()).data.problem.title).toBe('未完成草稿');
  await page.reload();
  await expect(page.getByRole('textbox',{name:'题目标题',exact:true})).toHaveValue('未完成草稿');
  await page.getByRole('textbox',{name:'题目标题',exact:true}).fill('尚未保存的标题');
  await page.getByRole('textbox',{name:'题目标题',exact:true}).press('Enter');
  await expect(page.getByText('有未保存修改',{exact:true})).toBeVisible();
  await page.getByText('JSON 导入导出',{exact:true}).click();
  await page.getByRole('button',{name:'准备导出当前内容',exact:true}).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button',{name:'导出题目 JSON',exact:true}).click();
  const stream = await (await download).createReadStream();
  let body = ''; for await (const chunk of stream!) body+=chunk.toString();
  expect(JSON.parse(body).title).toBe('尚未保存的标题');
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await page.getByText('版本记录',{exact:true}).click();
  await expect(page.getByRole('button',{name:'载入此版本（保存时新增版本）',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'保存并基础检查',exact:true}).click();
  await expect(page.getByRole('heading',{name:'AI 任务',exact:true})).toBeVisible();
  await expect(page.getByText('请返回来源草稿修复，再运行本地检查。')).toBeVisible();
  await noException(page);
});

for(const width of [1440,1024,390,320]) test(`native responsive layout, keyboard and long code at ${width}px`,async({page},info)=>{
  await page.setViewportSize({width,height:1000});
  await openWorkspace(page);
  await code(page, '# '+('long_comment '.repeat(40))+'\nprint(1)');
  await expect.poll(async()=> (await source(page))?.code).toBe('# '+('long_comment '.repeat(40))+'\nprint(1)');
  await page.keyboard.press('ControlOrMeta+Home');
  await page.getByRole('heading',{name:'代码',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath(`workspace-${width}.png`)});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await noException(page);
});

async function select(page:Page,label:string,value:string) {
  await page.getByRole('combobox',{name:label,exact:true}).focus();
  await page.waitForTimeout(400);
  await page.getByRole('combobox',{name:label,exact:true}).click();
  await page.getByRole('option',{name:value,exact:true}).click();
}
async function importedDraft(page:Page) {
  const problem = (await (await page.request.get(api+'/api/problems/sum_2')).json()).data;
  delete problem.limit_inheritance;
  problem.id = unique('native'); problem.title = 'Streamlit 导入验证题';
  await page.goto('/resources');
  await page.getByText('导入题目 JSON',{exact:true}).click();
  await page.getByRole('textbox',{name:'或粘贴题目 JSON',exact:true}).fill(JSON.stringify(problem));
  await page.getByRole('button',{name:'导入为草稿',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'题目标题',exact:true})).toHaveValue(problem.title);
  return {did:new URL(page.url()).searchParams.get('id')!,problem};
}

test('JSON import, basic verification without a reference, publishing and public log controls',async({page})=>{
  await login(page);
  const {problem} = await importedDraft(page);
  await page.getByRole('button',{name:'保存并基础检查',exact:true}).click();
  await expect(page.getByText('基础检查通过，可发布；不代表完整质量验证通过。')).toBeVisible();
  await expect(page.getByTestId('stAlertContentWarning').getByText('未提供参考解，因此没有自动核对样例和测试点输出。')).toBeVisible();
  await page.getByRole('button',{name:'打开成果草稿',exact:true}).click();
  await page.getByText('已审阅当前草稿，确认发布到题库',{exact:true}).click();
  await page.getByRole('button',{name:'发布题目',exact:true}).click();
  await expect(page).toHaveURL(/\/workspace\?/);
  await expect(page.getByRole('heading',{name:problem.title,exact:true})).toBeVisible();
  await page.getByRole('button',{name:'题目管理',exact:true}).click();
  await page.getByText('公开测试点日志',{exact:true}).click();
  await page.getByRole('button',{name:'保存日志可见性',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get(api+'/api/problems/'+problem.id)).json()).data.public_cases).toBe(true);
  await noException(page);
});

test('scoped AI changes and comprehensive review apply only to their source revision',async({page})=>{
  await login(page);
  const {did} = await importedDraft(page);
  await page.getByRole('textbox',{name:'命题需求 / 修改要求',exact:true}).fill('提供一个简单准确的新样例，保留其他内容。');
  await page.locator('summary').filter({hasText:'AI 修改'}).click();
  await select(page,'修改范围','样例');
  await page.getByRole('textbox',{name:'本次 AI 修改需求',exact:true}).fill('提供一个简单准确的新样例，保留其他内容。');
  await page.getByText('确认发起新的模型调用，费用单独累计',{exact:true}).click();
  await page.getByRole('button',{name:'保存并发起 AI 修改',exact:true}).click();
  await expect(page.getByRole('button',{name:'采纳到草稿',exact:true})).toBeVisible();
  await expect(page.locator('.diff-view')).toContainText('3 4');
  await page.getByText('已审阅修改，确认采纳到草稿',{exact:true}).click();
  await page.getByRole('button',{name:'采纳到草稿',exact:true}).click();
  await expect(page.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
  await expect.poll(async()=> (await (await page.request.get(api+'/api/problem-drafts/'+did)).json()).data.problem.samples[0].input).toBe('3 4');
  await page.getByRole('textbox',{name:'命题需求 / 修改要求',exact:true}).fill('重点检查约束表达和已有测试资产');
  await page.locator('summary').filter({hasText:'AI 修改'}).click();
  await select(page,'修改方式','全面审查');
  await page.getByRole('textbox',{name:'本次 AI 修改需求',exact:true}).fill('重点检查约束表达和已有测试资产');
  await page.getByText('确认发起新的模型调用，费用单独累计',{exact:true}).click();
  await page.getByRole('button',{name:'保存并发起 AI 修改',exact:true}).click();
  await expect(page.getByRole('button',{name:'采纳到草稿',exact:true})).toBeVisible();
  await page.getByText('已审阅修改，确认采纳到草稿',{exact:true}).click();
  // Simulate a genuine concurrent writer after the suggestion has been reviewed.
  const current = (await (await page.request.get(api+'/api/problem-drafts/'+did)).json()).data;
  const {base_problem_id,requirement,problem,reference_solution,brute_solution,generator_code,review,revision}=current;
  await page.request.put(api+'/api/problem-drafts/'+did,{data:{base_problem_id,requirement,problem:{...problem,title:'并发修改保留'},reference_solution,brute_solution,generator_code,review,revision}});
  await page.getByRole('button',{name:'采纳到草稿',exact:true}).click();
  await expect(page.getByText(/草稿已有新版本或未保存修改/)).toBeVisible();
  expect((await (await page.request.get(api+'/api/problem-drafts/'+did)).json()).data.problem.title).toBe('并发修改保留');
  await noException(page);
});

test('generation completes a draft, reports stage usage, and can archive a finished task',async({page})=>{
  await login(page);
  await page.goto('/ai');
  await page.getByRole('tab',{name:'生成整题',exact:true}).click();
  await page.getByRole('textbox',{name:'命题需求',exact:true}).fill('创建一道简单的整数求和题目，覆盖正负数和边界');
  await page.getByRole('button',{name:'生成整题',exact:true}).click();
  await expect(page.getByRole('button',{name:'打开成果草稿',exact:true})).toBeVisible({timeout:45000});
  const taskId = new URL(page.url()).searchParams.get('id');
  await expect(page.getByText(/^输入 Token/)).toBeVisible();
  await page.getByText('分阶段模型、Token 与计价依据',{exact:true}).click();
  await expect(page.getByText(/费用根据任务开始时的配置单价/)).toBeVisible();
  await page.getByRole('button',{name:'打开成果草稿',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'题目标题',exact:true})).toHaveValue('浏览器验收求和题');
  await page.goto('/ai_task?id='+taskId);
  await page.locator('[data-testid="stExpander"] summary').filter({hasText:'归档任务'}).click();
  await page.getByText('确认归档并中断尚未完成的任务',{exact:true}).click();
  await page.getByRole('button',{name:'归档任务',exact:true}).click();
  await expect(page.getByRole('heading',{name:'命题中心',exact:true})).toBeVisible();
  await noException(page);
});

test('failed generation retains its candidate and recovers an editable draft',async({page})=>{
  await login(page);
  await page.goto('/ai');
  await page.getByRole('tab',{name:'生成整题',exact:true}).click();
  await page.getByRole('textbox',{name:'命题需求',exact:true}).fill('创建一道验收失败恢复的简易计算器题目');
  await page.getByRole('button',{name:'生成整题',exact:true}).click();
  await expect(page.getByRole('button',{name:'保留失败成果为恢复草稿',exact:true})).toBeVisible({timeout:45000});
  await page.getByRole('button',{name:'保留失败成果为恢复草稿',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'题目标题',exact:true})).toHaveValue('浏览器验收求和题');
  await expect(page.getByRole('button',{name:'发布题目',exact:true})).toBeDisabled();
  await noException(page);
});

test('slow assistant resumes after reload, cancels, and never creates a replacement paid task',async({page})=>{
  await openWorkspace(page);
  await page.getByText('AI 做题助手',{exact:true}).click();
  await page.getByRole('button',{name:'新话题',exact:true}).click();
  const cid=(await (await page.request.post(api+'/api/ai/conversations/',{data:{problem_id:'sum_2'}})).json()).data.id;
  const messages=()=>page.request.get(api+`/api/ai/conversations/${cid}/messages?include_metadata=true`).then(r=>r.json());
  const before=(await messages()).data.total;
  await page.getByRole('textbox',{name:'向助手提问',exact:true}).fill('模拟慢速回答');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByRole('button',{name:'取消回答',exact:true})).toBeVisible();
  await page.reload();
  await page.getByText('AI 做题助手',{exact:true}).click();
  await expect(page.getByRole('button',{name:'取消回答',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'取消回答',exact:true}).click();
  await expect(page.getByRole('button',{name:'取消回答',exact:true})).toHaveCount(0);
  expect((await messages()).data.total).toBe(before+1);
  await noException(page);
});

test('switching account invalidates the old tab and keeps the new account source empty',async({page,context})=>{
  await openWorkspace(page);
  const secret = '# account scoped '+unique('private');
  await code(page,secret);
  await expect.poll(async()=> (await source(page))?.code).toBe(secret);
  const other = await context.newPage();
  const username=unique('second');
  await other.request.post(api+'/api/users/',{data:{username,password:'password1'}});
  await other.request.post(api+'/api/auth/login',{data:{username,password:'password1'}});
  await expect(page.locator('.view-lines')).not.toContainText(secret,{timeout:15000});
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  expect(await source(page)).toBeNull();
  await noException(page);
});

test('ordinary resources expose language registration, JSON validation and empty public logs',async({page})=>{
  const username=unique('resources');
  await page.request.post(api+'/api/users/',{data:{username,password:'password1'}});
  await page.request.post(api+'/api/auth/login',{data:{username,password:'password1'}});
  await page.goto('/resources?section='+encodeURIComponent('语言'));
  await page.getByText('注册评测语言',{exact:true}).click();
  const language=unique('python');
  await page.getByRole('textbox',{name:'语言标识',exact:true}).fill(language);
  await page.getByRole('textbox',{name:'文件扩展名',exact:true}).fill('.py');
  await page.getByRole('textbox',{name:'运行命令',exact:true}).fill('python3 {src}');
  await page.getByRole('button',{name:'注册语言',exact:true}).click();
  await expect(page.getByText('语言已注册。题目选择继承限制时将使用此配置。')).toBeVisible();
  await page.goto('/resources');
  await page.getByText('导入题目 JSON',{exact:true}).click();
  const input=page.getByRole('textbox',{name:'或粘贴题目 JSON',exact:true});
  for(const value of ['{broken','{"id":"sum_2","title":"duplicate"}','{"id":"new","time_limit":-1}']) {
    await input.fill(value); await input.press('Tab');
    await page.getByRole('button',{name:'导入为草稿',exact:true}).click();
    await expect(page.getByText(/导入失败/)).toBeVisible();
  }
  await page.goto('/records');
  await expect(page.getByText('没有符合条件的提交记录。')).toBeVisible();
  await page.locator('summary').filter({hasText:'查询公开日志'}).click();
  await page.getByRole('textbox',{name:'公开提交 ID',exact:true}).fill('999999999');
  await page.getByRole('button',{name:'查询公开日志',exact:true}).click();
  await expect(page.getByRole('heading',{name:'公开评测日志',exact:true})).toBeVisible();
  await expect(page.getByRole('textbox',{name:'公开提交 ID',exact:true})).toHaveValue('999999999');
  await page.getByRole('button',{name:'关闭当前任务',exact:true}).click();
  await page.getByRole('button',{name:'确认关闭',exact:true}).click();
  await expect(page.getByRole('heading',{name:'提交记录',exact:true})).toBeVisible();
  await page.goto('/admin');
  await expect(page.getByText('此页面仅管理员可访问。')).toBeVisible();
  await noException(page);
});

test('source import resolves ambiguous extensions and preserves code until confirmation',async({page})=>{
  await openWorkspace(page);
  await code(page,'# source before import');
  await expect.poll(async()=> (await source(page))?.code).toBe('# source before import');
  await page.getByText('导入与导出源码',{exact:true}).click();
  await page.locator('input[type=file]').setInputFiles({name:'solution.py',mimeType:'text/plain',buffer:Buffer.from('# 中文导入\nprint(42)')});
  await expect(page.getByRole('button',{name:'载入文件',exact:true})).toBeDisabled();
  expect((await source(page)).code).toBe('# source before import');
  await select(page,'导入目标语言','python');
  await page.getByText('确认替换目标语言的草稿',{exact:true}).click();
  await page.getByRole('button',{name:'载入文件',exact:true}).click();
  await expect.poll(async()=> (await source(page))?.code).toBe('# 中文导入\nprint(42)');
  await expect(page.locator('.view-lines')).toContainText('中文导入');
  await noException(page);
});

test('navigation restores filters, deep-link tasks, scroll, and warns before leaving unsaved drafts',async({page})=>{
  await login(page);
  await page.goto('/?q=sum_2&progress='+encodeURIComponent('尝试中'));
  await expect(page.getByRole('combobox',{name:'学习状态',exact:true})).toHaveValue('尝试中');
  await page.goto('/workspace?id=sum_2&language=python');
  await expect(page.getByRole('button',{name:'关闭当前任务',exact:true})).toBeVisible();
  await page.getByRole('heading',{name:'做题助手',exact:true}).scrollIntoViewIfNeeded();
  const top=await page.locator('[data-testid="stMain"]').evaluate(el=>el.scrollTop);
  await page.waitForTimeout(300);
  await page.reload();
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeAttached();
  await expect.poll(async()=>page.locator('[data-testid="stMain"]').evaluate(el=>el.scrollTop)).toBeGreaterThan(top-100);
  await page.getByRole('button',{name:'编辑题目',exact:true}).click();
  await page.getByRole('textbox',{name:'题目标题',exact:true}).fill('尚未保存的导航修改');
  await page.getByRole('textbox',{name:'题目标题',exact:true}).press('Enter');
  await expect(page.getByText('有未保存修改',{exact:true})).toBeVisible();
  const dialog=page.waitForEvent('dialog');
  const click=page.getByRole('button',{name:'返回来源',exact:true}).click();
  await (await dialog).dismiss(); await click;
  await expect(page.getByRole('textbox',{name:'题目标题',exact:true})).toHaveValue('尚未保存的导航修改');
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();
  await expect(page.getByText('有未保存修改',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'返回来源',exact:true}).click();
  await expect(page.getByRole('button',{name:'提交评测',exact:true})).toBeVisible();
  await noException(page);
});

test('administrator creates accounts, changes roles, queries audit and cancels reset',async({page})=>{
  await login(page);
  await page.goto('/admin');
  await page.getByText('创建新账户',{exact:true}).click();
  const username=unique('managed');
  await page.getByRole('textbox',{name:'用户名',exact:true}).fill(username);
  await page.getByRole('textbox',{name:'初始密码',exact:true}).fill('汉'.repeat(25));
  await page.getByRole('button',{name:'创建账户',exact:true}).click();
  await expect(page.getByText(/72.*UTF-8|UTF-8.*72/)).toBeVisible();
  await page.getByRole('textbox',{name:'初始密码',exact:true}).fill('password1');
  await page.getByRole('button',{name:'创建账户',exact:true}).click();
  await expect(page.getByText('账户已创建',{exact:true})).toBeVisible();
  await page.getByRole('textbox',{name:'搜索用户名或用户 ID',exact:true}).fill(username);
  await page.getByRole('textbox',{name:'搜索用户名或用户 ID',exact:true}).press('Enter');
  await select(page,'角色','已禁用');
  await page.getByText(`确认将 ${username} 从 user 改为 banned`,{exact:true}).click();
  await page.getByRole('button',{name:'保存角色',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get(api+'/api/users/?q='+username)).json()).data.users[0].role).toBe('banned');
  await page.goto('/admin?section='+encodeURIComponent('角色审计'));
  await expect(page.locator('[data-testid="stDataFrame"]')).toBeVisible();
  await page.goto('/admin?section='+encodeURIComponent('访问审计'));
  await expect(page.getByText('请填写用户 ID 或题号后查询访问审计。')).toBeVisible();
  await page.getByRole('textbox',{name:'题号（留空为全部）',exact:true}).fill('sum_2');
  await page.getByRole('button',{name:'查询访问审计',exact:true}).click();
  await expect(page).toHaveURL(/problem_id=sum_2/);
  await page.goto('/admin?section='+encodeURIComponent('系统设置'));
  await page.getByRole('button',{name:'重置实验系统',exact:true}).click();
  await expect(page.getByRole('button',{name:'确认重置',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  expect((await page.request.get(api+'/api/problems/sum_2')).status()).toBe(200);
  await noException(page);
});


test('AI revision validates its own requirement and submission history uses verdict cards', async ({page}) => {
  await login(page);
  await importedDraft(page);
  await page.locator('summary').filter({hasText:'AI 修改'}).click();
  const requirement = page.getByRole('textbox',{name:'本次 AI 修改需求',exact:true});
  await requirement.fill('');
  await page.getByText('确认发起新的模型调用，费用单独累计',{exact:true}).click();
  await page.getByRole('button',{name:'保存并发起 AI 修改',exact:true}).click();
  await expect(page.getByText('请在本次 AI 修改需求中填写至少 10 个字符，说明希望修改的内容。',{exact:true})).toBeVisible();
  const response = await page.request.post(api+'/api/submissions/',{data:{problem_id:'brackets',language:'python',code:'raise RuntimeError()'}});
  expect(response.ok()).toBe(true);
  const sid=(await response.json()).data.submission_id;
  await expect.poll(async()=> (await (await page.request.get(api+'/api/submissions/'+sid)).json()).data.status).not.toBe('pending');
  await page.goto('/workspace?id=brackets&language=python');
  await page.getByText('本题提交历史',{exact:true}).click();
  const card=page.locator('.st-key-history-card-'+sid);
  await expect(card).toContainText('RE · 运行时错误');
  await expect(card).toContainText('北京时间');
  await expect(card).not.toContainText('success');
  await card.getByRole('button',{name:'查看详情',exact:true}).click();
  await expect(page.locator('.st-key-task-strip')).toContainText('提交 #'+sid);
  await page.getByRole('button',{name:'返回来源',exact:true}).click();
  await expect(page.locator('.st-key-task-strip').getByRole('button',{name:'括号的秩序',exact:true})).toBeVisible();
  await noException(page);
});

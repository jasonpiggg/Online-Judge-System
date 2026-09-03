from __future__ import annotations

import json

import streamlit as st
from streamlit_ace import st_ace

from frontend.client import ApiClient
from frontend.ui import call, heading


def problem_form(api: ApiClient, existing: dict[str, object] | None = None) -> None:
    value = existing or {}
    with st.form("problem-editor"):
        a, b = st.columns([1, 2])
        problem_id = a.text_input("题号", value=str(value.get("id", "")), disabled=bool(existing))
        title = b.text_input("标题", value=str(value.get("title", "")))
        description = st.text_area("题目描述", value=str(value.get("description", "")), height=140)
        input_description, output_description = st.columns(2)
        input_text = input_description.text_area(
            "输入格式", value=str(value.get("input_description", ""))
        )
        output_text = output_description.text_area(
            "输出格式", value=str(value.get("output_description", ""))
        )
        constraints = st.text_area("数据范围", value=str(value.get("constraints", "")))
        sample_default = value.get("samples", [{"input": "", "output": ""}])
        cases_default = value.get("testcases", [{"input": "", "output": ""}])
        samples = st.text_area(
            "样例（JSON 数组）",
            value=json.dumps(sample_default, ensure_ascii=False, indent=2),
            height=140,
        )
        testcases = st.text_area(
            "测试点（JSON 数组）",
            value=json.dumps(cases_default, ensure_ascii=False, indent=2),
            height=190,
        )
        c1, c2, c3 = st.columns(3)
        time_limit = c1.number_input(
            "时间限制 / 秒", 0.1, 30.0, float(value.get("time_limit", 3.0)), 0.1
        )
        memory_limit = c2.number_input(
            "内存限制 / MB", 16, 2048, int(value.get("memory_limit", 128)), 16
        )
        difficulty = c3.text_input("难度", value=str(value.get("difficulty", "")))
        tags = st.text_input("标签（逗号分隔）", value=", ".join(value.get("tags", [])))
        hint, source, author = st.columns(3)
        hint_value = hint.text_input("提示", value=str(value.get("hint", "")))
        source_value = source.text_input("来源", value=str(value.get("source", "")))
        author_value = author.text_input("作者", value=str(value.get("author", "")))
        submitted = st.form_submit_button(
            "保存修改" if existing else "创建题目", type="primary", width="stretch"
        )
        if submitted:
            try:
                body = {
                    "id": problem_id,
                    "title": title,
                    "description": description,
                    "input_description": input_text,
                    "output_description": output_text,
                    "samples": json.loads(samples),
                    "constraints": constraints,
                    "testcases": json.loads(testcases),
                    "hint": hint_value,
                    "source": source_value,
                    "tags": [item.strip() for item in tags.split(",") if item.strip()],
                    "time_limit": time_limit,
                    "memory_limit": memory_limit,
                    "author": author_value,
                    "difficulty": difficulty,
                    "public_cases": bool(value.get("public_cases", False)),
                }
            except json.JSONDecodeError:
                st.error("样例和测试点必须是有效的 JSON 数组。")
                return
            result = call(
                lambda: (
                    api.put(f"/api/problems/{problem_id}", json=body)
                    if existing
                    else api.post("/api/problems/", json=body)
                )
            )
            if result:
                st.success("题目已经保存。")


def profile_page(api: ApiClient) -> None:
    heading("Identity / account", "个人资料")
    user = st.session_state.user
    result = call(lambda: api.get(f"/api/users/{user['user_id']}"))
    if not result:
        return
    data = result["data"]
    c1, c2, c3 = st.columns(3)
    c1.metric("提交次数", data["submit_count"])
    c2.metric("通过题目", data["resolve_count"])
    c3.metric("权限角色", str(data["role"]).upper())
    st.markdown(
        f'<div class="plate"><span class="eyebrow">MEMBER SINCE</span><h3>{data["username"]}</h3>'
        f"<code>{data['join_time']} · UID {data['user_id']}</code></div>",
        unsafe_allow_html=True,
    )


def problems_page(api: ApiClient) -> None:
    heading("Library / verified tasks", "题目目录", "选择一道题阅读，或创建新的评测任务。")
    result = call(lambda: api.get("/api/problems/"))
    if not result:
        return
    problems = result["data"]
    mode = st.segmented_control("视图", ["浏览", "新增"], default="浏览")
    if mode == "新增":
        problem_form(api)
        return
    if not problems:
        st.info("题库还是空的。切换到“新增”创建第一道题。")
        return
    labels = {f"{item['id']} · {item['title']}": item["id"] for item in problems}
    selected = st.selectbox("选择题目", labels)
    detail = call(lambda: api.get(f"/api/problems/{labels[selected]}"))
    if not detail:
        return
    problem = detail["data"]
    st.markdown(f"## {problem['title']}")
    st.caption(
        f"{problem['id']} · {problem['difficulty'] or '未分级'} · {problem['source'] or '原创'}"
    )
    description, io_tab, samples_tab, edit_tab = st.tabs(["题面", "输入与输出", "样例", "编辑"])
    with description:
        st.write(problem["description"])
        st.markdown("#### 数据范围")
        st.code(problem["constraints"], language=None)
        if problem["hint"]:
            st.info(problem["hint"])
    with io_tab:
        st.markdown("#### 输入格式")
        st.write(problem["input_description"])
        st.markdown("#### 输出格式")
        st.write(problem["output_description"])
    with samples_tab:
        for index, sample in enumerate(problem["samples"], start=1):
            left, right = st.columns(2)
            left.code(sample["input"], language=None)
            right.code(sample["output"], language=None)
            st.caption(f"SAMPLE / {index:02d}")
    with edit_tab:
        problem_form(api, problem)


def submit_page(api: ApiClient) -> None:
    heading("Judge / new run", "提交评测", "一分钟最多提交三次。评测会在后台异步执行。")
    problem_result = call(lambda: api.get("/api/problems/"))
    language_result = call(lambda: api.get("/api/languages/"))
    if not problem_result or not language_result:
        return
    problems = problem_result["data"]
    if not problems:
        st.info("请先创建题目。")
        return
    options = {f"{p['id']} · {p['title']}": p["id"] for p in problems}
    c1, c2 = st.columns([2, 1])
    selected = c1.selectbox("题目", options)
    language = c2.selectbox("语言", language_result["data"]["name"])
    starter = (
        "a, b = map(int, input().split())\nprint(a + b)"
        if language == "python"
        else "#include <iostream>\nint main(){ long long a,b; std::cin>>a>>b; std::cout<<a+b; }"
    )
    code = st_ace(
        value=starter,
        language="python" if language == "python" else "c_cpp",
        theme="tomorrow_night_eighties",
        height=360,
        key=f"editor-{language}",
    )
    if st.button("提交给评测器", type="primary", width="stretch"):
        result = call(
            lambda: api.post(
                "/api/submissions/",
                json={"problem_id": options[selected], "language": language, "code": code},
            )
        )
        if result:
            st.session_state.last_submission = result["data"]["submission_id"]
            st.success(f"提交 #{st.session_state.last_submission} 已进入队列。")


@st.fragment(run_every=1)
def live_submission(api: ApiClient, submission_id: str) -> None:
    result = call(lambda: api.get(f"/api/submissions/{submission_id}"))
    if not result:
        return
    data = result["data"]
    status = data["status"]
    st.markdown(f'<span class="signal">{str(status).upper()}</span>', unsafe_allow_html=True)
    if status == "pending":
        st.caption("评测器正在运行测试点……")
        return
    if status == "error":
        st.error(data.get("error_info", "评测服务异常"))
        return
    c1, c2 = st.columns(2)
    c1.metric("得分", data["score"])
    c2.metric("总分", data["counts"])
    if data.get("compile_info"):
        st.json(data["compile_info"])
    if data.get("run_info"):
        st.json(data["run_info"])
    logs = call(lambda: api.get(f"/api/submissions/{submission_id}/log"))
    if logs:
        st.dataframe(logs["data"]["details"], width="stretch", hide_index=True)


def submissions_page(api: ApiClient) -> None:
    heading("Archive / evaluations", "提交记录")
    user = st.session_state.user
    problem_result = call(lambda: api.get("/api/problems/"))
    if not problem_result:
        return
    choices = {"全部题目": None} | {
        f"{p['id']} · {p['title']}": p["id"] for p in problem_result["data"]
    }
    c1, c2 = st.columns(2)
    selected_problem = c1.selectbox("题目筛选", choices)
    status = c2.selectbox("状态", ["全部", "pending", "success", "error"])
    params = {"user_id": user["user_id"], "page_size": 50}
    if choices[selected_problem]:
        params["problem_id"] = choices[selected_problem]
    if status != "全部":
        params["status"] = status
    result = call(lambda: api.get("/api/submissions/", params=params))
    if not result:
        return
    records = result["data"]["submissions"]
    st.caption(f"共 {result['data']['total']} 条记录")
    if not records:
        st.info("当前筛选条件下没有提交。")
        return
    st.dataframe(records, width="stretch", hide_index=True)
    default_id = str(st.session_state.get("last_submission", records[0]["submission_id"]))
    ids = [str(record["submission_id"]) for record in records]
    default_index = ids.index(default_id) if default_id in ids else 0
    selected_id = st.selectbox("查看提交详情", ids, index=default_index)
    live_submission(api, selected_id)


def admin_page(api: ApiClient) -> None:
    heading("Control / restricted", "管理控制")
    users_tab, language_tab, audit_tab, visibility_tab = st.tabs(
        ["用户权限", "语言注册", "访问审计", "日志公开"]
    )
    with users_tab:
        users = call(lambda: api.get("/api/users/", params={"page_size": 100}))
        if users:
            st.dataframe(users["data"]["users"], width="stretch", hide_index=True)
            mapping = {
                f"{u['user_id']} · {u['username']} ({u['role']})": u["user_id"]
                for u in users["data"]["users"]
            }
            who = st.selectbox("选择用户", mapping)
            role = st.selectbox("新角色", ["user", "admin", "banned"])
            if st.button("更新角色"):
                if call(lambda: api.put(f"/api/users/{mapping[who]}/role", json={"role": role})):
                    st.success("权限已更新。")
    with language_tab, st.form("language"):
        name = st.text_input("语言名称", placeholder="go")
        ext = st.text_input("文件扩展名", placeholder=".go")
        compile_cmd = st.text_input("编译命令（可选）", placeholder="go build -o {exe} {src}")
        run_cmd = st.text_input("运行命令", placeholder="{exe}")
        time_limit = st.number_input("默认时间限制", 0.1, 30.0, 3.0)
        memory_limit = st.number_input("默认内存限制", 16, 2048, 128)
        if st.form_submit_button("注册语言"):
            body = {
                "name": name,
                "file_ext": ext,
                "compile_cmd": compile_cmd or None,
                "run_cmd": run_cmd,
                "time_limit": time_limit,
                "memory_limit": memory_limit,
            }
            if call(lambda: api.post("/api/languages/", json=body)):
                st.success("语言已注册。")
    with audit_tab:
        logs = call(lambda: api.get("/api/logs/access/", params={"page_size": 100}))
        if logs:
            st.dataframe(logs["data"], width="stretch", hide_index=True)
    with visibility_tab:
        problems = call(lambda: api.get("/api/problems/"))
        if problems and problems["data"]:
            mapping = {f"{p['id']} · {p['title']}": p["id"] for p in problems["data"]}
            selected = st.selectbox("题目", mapping, key="visibility-problem")
            public = st.toggle("公开测试点明细")
            if st.button("保存可见性"):
                if call(
                    lambda: api.put(
                        f"/api/problems/{mapping[selected]}/log_visibility",
                        json={"public_cases": public},
                    )
                ):
                    st.success("可见性已保存。")


@st.fragment(run_every=1)
def live_ai_task(api: ApiClient, task_id: str) -> None:
    result = call(lambda: api.get(f"/api/ai/problem-tasks/{task_id}"))
    if not result:
        return
    data = result["data"]
    st.markdown(
        f'<span class="signal">{str(data["status"]).upper()}</span>', unsafe_allow_html=True
    )
    st.write(data["progress"])
    usage = data["usage"]
    c1, c2, c3 = st.columns(3)
    c1.metric("输入 Token", usage["input_tokens"])
    c2.metric("输出 Token", usage["output_tokens"])
    c3.metric("费用 / USD", f"{usage['cost']:.6f}")
    if data["status"] in {"pending", "running"}:
        if st.button("中断任务", type="secondary"):
            call(lambda: api.put(f"/api/ai/problem-tasks/{task_id}/cancel"))
    if data.get("result"):
        st.session_state.ai_result = data["result"]
        st.json(data["result"])


def ai_page(api: ApiClient) -> None:
    heading("Studio / assisted authoring", "AI 智能命题", "模型配置只保存在服务端，密钥不会回显。")
    config_tab, task_tab, import_tab = st.tabs(["模型配置", "创建任务", "导入题库"])
    with config_tab, st.form("ai-config"):
        provider = st.text_input("提供商 URL", placeholder="https://api.example.com/v1")
        model = st.text_input("模型名称", placeholder="model-name")
        api_key = st.text_input("模型密钥", type="password")
        c1, c2, c3 = st.columns(3)
        input_price = c1.number_input("输入单价", 0.0, value=0.0, format="%.6f")
        output_price = c2.number_input("输出单价", 0.0, value=0.0, format="%.6f")
        unit = c3.number_input("计价 Token", 1, value=1_000_000)
        if st.form_submit_button("保存模型配置", type="primary"):
            body = {
                "provider_url": provider,
                "model": model,
                "api_key": api_key,
                "input_price": input_price,
                "output_price": output_price,
                "price_unit": unit,
            }
            if call(lambda: api.put("/api/ai/model-config", json=body)):
                st.success("配置已加密保存。")
    with task_tab:
        problems = call(lambda: api.get("/api/problems/"))
        options = {"不参考已有题目": None}
        if problems:
            options |= {f"{p['id']} · {p['title']}": p["id"] for p in problems["data"]}
        reference = st.selectbox("参考题目", options)
        requirement = st.text_area(
            "命题需求",
            placeholder="面向初学者，考查列表和双指针；中等难度；覆盖空输入、重复值与大规模数据。",
            height=150,
        )
        if st.button("开始智能命题", type="primary", width="stretch"):
            result = call(
                lambda: api.post(
                    "/api/ai/problem-tasks/",
                    json={"requirement": requirement, "problem_id": options[reference]},
                )
            )
            if result:
                st.session_state.ai_task = result["data"]["task_id"]
        if st.session_state.get("ai_task"):
            live_ai_task(api, st.session_state.ai_task)
    with import_tab:
        result = st.session_state.get("ai_result")
        if not result:
            st.info("完成命题任务后，结果会出现在这里供人工审阅。")
        else:
            st.write("确认题面与测试点后，再写入正式题库。")
            st.json(result)
            if st.button("写入题库", type="primary"):
                problem = result.get("problem", result)
                if call(lambda: api.post("/api/problems/", json=problem)):
                    st.success("AI 题目已进入题库。")


def auth_screen(api: ApiClient) -> None:
    st.markdown(
        '<div class="eyebrow">Programming systems laboratory / 02</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="mast"><h1>把代码交给<br>严格的机器。</h1></div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.markdown("### Atelier OJ")
        st.write("一套克制、透明、可追溯的在线评测工作台。写下解法，剩下的交给评测器。")
        st.markdown('<span class="signal">PYTHON · C++14 · ASYNC</span>', unsafe_allow_html=True)
    with right:
        login_tab, register_tab = st.tabs(["登录", "创建账户"])
        with login_tab, st.form("login"):
            username = st.text_input("用户名", placeholder="admin")
            password = st.text_input("密码", type="password")
            if st.form_submit_button("进入工作台", type="primary", width="stretch"):
                result = call(
                    lambda: api.post(
                        "/api/auth/login", json={"username": username, "password": password}
                    )
                )
                if result:
                    st.session_state.user = result["data"]
                    st.rerun()
        with register_tab, st.form("register"):
            username = st.text_input("新用户名")
            password = st.text_input("新密码（至少 6 位）", type="password")
            if st.form_submit_button("注册", width="stretch"):
                result = call(
                    lambda: api.post(
                        "/api/users/", json={"username": username, "password": password}
                    )
                )
                if result:
                    st.success("账户已创建，现在可以登录。")
    st.caption("演示管理员：admin / admintestpassword")


def dashboard(api: ApiClient) -> None:
    user = st.session_state.user
    with st.sidebar:
        st.markdown("## ⌁ Atelier OJ")
        st.markdown(f"**{user['username']}**  ")
        st.caption(f"ROLE / {str(user['role']).upper()}")
        options = ["题目目录", "提交评测", "提交记录", "个人资料", "AI 智能命题"]
        if user["role"] == "admin":
            options.insert(3, "管理控制")
        page = st.radio("工作区", options, label_visibility="collapsed")
        st.divider()
        if st.button("退出登录", width="stretch"):
            call(lambda: api.post("/api/auth/logout"))
            st.session_state.pop("user", None)
            st.rerun()
    pages = {
        "题目目录": problems_page,
        "提交评测": submit_page,
        "提交记录": submissions_page,
        "个人资料": profile_page,
        "管理控制": admin_page,
        "AI 智能命题": ai_page,
    }
    pages[page](api)

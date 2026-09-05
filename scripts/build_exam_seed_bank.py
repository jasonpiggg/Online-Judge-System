# ruff: noqa: E501
from __future__ import annotations

import argparse
import ast
import heapq
import json
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "problem_seeds"


@dataclass(frozen=True)
class Spec:
    id: str
    title: str
    difficulty: str
    tags: list[str]
    description: str
    input_description: str
    output_description: str
    constraints: str
    hint: str
    inputs: list[str]
    solve: Callable[[str], str]
    source: str = "Atelier OJ 分级题库"
    time_limit: float = 2.0
    memory_limit: int = 256


def lines(text: str) -> list[str]:
    return text.strip("\n").splitlines()


def solve_coin(text: str) -> str:
    value = int(text)
    answer = []
    for unit in (100, 50, 20, 10, 5, 1):
        count, value = divmod(value, unit)
        answer.append(str(count))
    return " ".join(answer) + "\n"


def solve_calendar(text: str) -> str:
    year, month = map(int, text.split())
    leap = year % 400 == 0 or year % 4 == 0 and year % 100 != 0
    days = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return f"{days[month - 1]}\n"


def solve_digits(text: str) -> str:
    counts = Counter(c for c in text if c.isdigit())
    return " ".join(str(counts[str(i)]) for i in range(10)) + "\n"


def solve_grades(text: str) -> str:
    values = list(map(int, text.split()))[1:]
    buckets = [0] * 5
    for value in values:
        buckets[0 if value >= 90 else 1 if value >= 80 else 2 if value >= 70 else 3 if value >= 60 else 4] += 1
    return " ".join(map(str, buckets)) + "\n"


def solve_tier(text: str) -> str:
    value = int(text)
    return f"{min(value, 100) * 2 + min(max(value - 100, 0), 100) * 3 + max(value - 200, 0) * 5}\n"


def solve_word_frequency(text: str) -> str:
    counts = Counter(text.split())
    best = min(counts, key=lambda word: (-counts[word], word))
    return f"{best} {counts[best]}\n"


def solve_rotate(text: str) -> str:
    raw = lines(text)
    n, m = map(int, raw[0].split())
    matrix = [list(map(int, row.split())) for row in raw[1 : n + 1]]
    return "\n".join(" ".join(str(matrix[n - 1 - i][j]) for i in range(n)) for j in range(m)) + "\n"


def solve_merge(text: str) -> str:
    raw = lines(text)
    intervals = sorted(tuple(map(int, row.split())) for row in raw[1:])
    merged: list[list[int]] = []
    for left, right in intervals:
        if not merged or left > merged[-1][1]:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    return f"{len(merged)}\n" + "\n".join(f"{a} {b}" for a, b in merged) + "\n"


def solve_relations(text: str) -> str:
    raw = lines(text)
    n, m, q = map(int, raw[0].split())
    parent = list(range(n + 1))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for row in raw[1 : m + 1]:
        a, b = map(int, row.split())
        parent[find(a)] = find(b)
    return "\n".join("YES" if find(a) == find(b) else "NO" for a, b in (map(int, row.split()) for row in raw[m + 1 : m + q + 1])) + "\n"


def solve_rle(text: str) -> str:
    value = text.strip()
    answer: list[str] = []
    start = 0
    for index in range(1, len(value) + 1):
        if index == len(value) or value[index] != value[start]:
            answer.append(f"{value[start]}{index - start}")
            start = index
    return " ".join(answer) + "\n"


def solve_dynamic_sum(text: str) -> str:
    raw = lines(text)
    n, _ = map(int, raw[0].split())
    values = list(map(int, raw[1].split()))
    answer = []
    for row in raw[2:]:
        op, a, b = row.split()
        x, y = int(a), int(b)
        if op == "U":
            values[x - 1] = y
        else:
            answer.append(str(sum(values[x - 1 : y])))
    return "\n".join(answer) + ("\n" if answer else "")


def solve_grid(text: str) -> str:
    raw = lines(text)
    n, m = map(int, raw[0].split())
    grid = raw[1 : n + 1]
    start = next((i, row.index("S")) for i, row in enumerate(grid) if "S" in row)
    queue = deque([(start[0], start[1], 0)])
    seen = {start}
    while queue:
        x, y, distance = queue.popleft()
        if grid[x][y] == "E":
            return f"{distance}\n"
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < n and 0 <= ny < m and grid[nx][ny] != "#" and (nx, ny) not in seen:
                seen.add((nx, ny))
                queue.append((nx, ny, distance + 1))
    return "-1\n"


def solve_expression(text: str) -> str:
    tree = ast.parse(text.strip(), mode="eval")

    def visit(node: ast.AST) -> int:
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -visit(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            left, right = visit(node.left), visit(node.right)
            return left + right if isinstance(node.op, ast.Add) else left - right if isinstance(node.op, ast.Sub) else left * right
        raise ValueError("unsupported expression")

    return f"{visit(tree.body)}\n"


def solve_quota(text: str) -> str:
    raw = lines(text)
    n, quota = map(int, raw[0].split())
    chosen = sorted(((-int(score), name) for name, score in (row.split() for row in raw[1 : n + 1])))[:quota]
    return "\n".join(name for _, name in chosen) + "\n"


def solve_dependencies(text: str) -> str:
    raw = lines(text)
    n, m = map(int, raw[0].split())
    graph = [[] for _ in range(n + 1)]
    degree = [0] * (n + 1)
    for row in raw[1 : m + 1]:
        before, after = map(int, row.split())
        graph[before].append(after)
        degree[after] += 1
    ready = [i for i in range(1, n + 1) if degree[i] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for nxt in graph[node]:
            degree[nxt] -= 1
            if degree[nxt] == 0:
                heapq.heappush(ready, nxt)
    return (" ".join(map(str, order)) if len(order) == n else "CYCLE") + "\n"


def solve_range_add(text: str) -> str:
    raw = lines(text)
    n, _ = map(int, raw[0].split())
    values = list(map(int, raw[1].split()))
    answer = []
    for row in raw[2:]:
        parts = row.split()
        left, right = int(parts[1]), int(parts[2])
        if parts[0] == "ADD":
            for index in range(left - 1, right):
                values[index] += int(parts[3])
        else:
            answer.append(str(sum(values[left - 1 : right])))
    return "\n".join(answer) + "\n"


def solve_weighted_schedule(text: str) -> str:
    rows = [tuple(map(int, row.split())) for row in lines(text)[1:]]
    rows.sort(key=lambda item: item[1])
    dp = [0] * (len(rows) + 1)
    for i, (start, _, value) in enumerate(rows, 1):
        compatible = max((j for j in range(i - 1) if rows[j][1] <= start), default=-1) + 1
        dp[i] = max(dp[i - 1], dp[compatible] + value)
    return f"{dp[-1]}\n"


def tree_path(adjacency: list[list[int]], start: int, target: int) -> list[int]:
    parent = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == target:
            break
        for nxt in adjacency[node]:
            if nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)
    path = []
    node = target
    while node:
        path.append(node)
        if node == start:
            break
        node = parent[node]
    return path[::-1]


def solve_tree_counts(text: str) -> str:
    raw = lines(text)
    n, q = map(int, raw[0].split())
    edges = [tuple(map(int, row.split())) for row in raw[1:n]]
    graph = [[] for _ in range(n + 1)]
    for a, b in edges:
        graph[a].append(b)
        graph[b].append(a)
    counts = Counter()
    for row in raw[n : n + q]:
        path = tree_path(graph, *map(int, row.split()))
        for a, b in zip(path, path[1:], strict=False):
            counts[tuple(sorted((a, b)))] += 1
    return " ".join(str(counts[tuple(sorted(edge))]) for edge in edges) + "\n"


def solve_matching(text: str) -> str:
    raw = lines(text)
    n = int(raw[0])
    costs = [list(map(int, row.split())) for row in raw[1 : n + 1]]
    return f"{min(sum(costs[i][p[i]] for i in range(n)) for p in permutations(range(n)))}\n"


def solve_patterns(text: str) -> str:
    raw = lines(text)
    source, count = raw[0], int(raw[1])
    answer = []
    for pattern in raw[2 : 2 + count]:
        answer.append(str(sum(source.startswith(pattern, index) for index in range(len(source)))))
    return "\n".join(answer) + "\n"


def solve_connectivity(text: str) -> str:
    raw = lines(text)
    _, q = map(int, raw[0].split())
    edges: set[tuple[int, int]] = set()
    answer = []
    for row in raw[1 : q + 1]:
        op, a_raw, b_raw = row.split()
        a, b = int(a_raw), int(b_raw)
        edge = tuple(sorted((a, b)))
        if op == "+":
            edges.add(edge)
        elif op == "-":
            edges.remove(edge)
        else:
            graph: dict[int, list[int]] = {}
            for x, y in edges:
                graph.setdefault(x, []).append(y)
                graph.setdefault(y, []).append(x)
            seen, queue = {a}, deque([a])
            while queue:
                for nxt in graph.get(queue.popleft(), []):
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
            answer.append("YES" if b in seen else "NO")
    return "\n".join(answer) + "\n"


def solve_tree_chain(text: str) -> str:
    raw = lines(text)
    n, q = map(int, raw[0].split())
    values = [0] + list(map(int, raw[1].split()))
    graph = [[] for _ in range(n + 1)]
    for row in raw[2 : n + 1]:
        a, b = map(int, row.split())
        graph[a].append(b)
        graph[b].append(a)
    answer = []
    for row in raw[n + 1 : n + q + 1]:
        parts = row.split()
        path = tree_path(graph, int(parts[1]), int(parts[2]))
        if parts[0] == "ADD":
            for node in path:
                values[node] += int(parts[3])
        else:
            answer.append(str(sum(values[node] for node in path)))
    return "\n".join(answer) + "\n"


def solve_transport(text: str) -> str:
    raw = lines(text)
    n, m = map(int, raw[0].split())
    supply = list(map(int, raw[1].split()))
    demand = list(map(int, raw[2].split()))
    costs = [list(map(int, row.split())) for row in raw[3 : 3 + n]]
    graph: list[list[list[int]]] = [[] for _ in range(n + m + 2)]
    source, sink = n + m, n + m + 1

    def add(a: int, b: int, cap: int, cost: int) -> None:
        graph[a].append([b, cap, cost, len(graph[b])])
        graph[b].append([a, 0, -cost, len(graph[a]) - 1])

    for i, cap in enumerate(supply):
        add(source, i, cap, 0)
    for i in range(n):
        for j in range(m):
            add(i, n + j, 10**9, costs[i][j])
    for j, cap in enumerate(demand):
        add(n + j, sink, cap, 0)
    result, required = 0, sum(demand)
    while required:
        dist = [10**18] * len(graph)
        prev: list[tuple[int, int] | None] = [None] * len(graph)
        dist[source] = 0
        for _ in range(len(graph)):
            changed = False
            for node, edges in enumerate(graph):
                if dist[node] == 10**18:
                    continue
                for index, edge in enumerate(edges):
                    if edge[1] and dist[edge[0]] > dist[node] + edge[2]:
                        dist[edge[0]] = dist[node] + edge[2]
                        prev[edge[0]] = (node, index)
                        changed = True
            if not changed:
                break
        flow, node = required, sink
        while node != source:
            parent, index = prev[node] or (_ for _ in ()).throw(ValueError("infeasible"))
            flow = min(flow, graph[parent][index][1])
            node = parent
        node = sink
        while node != source:
            parent, index = prev[node]  # type: ignore[misc]
            edge = graph[parent][index]
            edge[1] -= flow
            graph[node][edge[3]][1] += flow
            node = parent
        result += flow * dist[sink]
        required -= flow
    return f"{result}\n"


def solve_repeated(text: str) -> str:
    raw = lines(text)
    value, q = raw[0], int(raw[1])
    answer = []
    for k in map(int, raw[2 : 2 + q]):
        best = 0
        for length in range(1, len(value) + 1):
            counts = Counter(value[i : i + length] for i in range(len(value) - length + 1))
            if max(counts.values(), default=0) >= k:
                best = length
        answer.append(str(best))
    return "\n".join(answer) + "\n"


def solve_partition(text: str) -> str:
    raw = lines(text)
    n, groups = map(int, raw[0].split())
    values = list(map(int, raw[1].split()))
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    dp = [[10**30] * (n + 1) for _ in range(groups + 1)]
    dp[0][0] = 0
    for group in range(1, groups + 1):
        for end in range(group, n + 1):
            dp[group][end] = min(dp[group - 1][start] + (prefix[end] - prefix[start]) ** 2 for start in range(group - 1, end))
    return f"{dp[groups][n]}\n"


def solve_inventory(text: str) -> str:
    raw = lines(text)
    total_count = total_value = 0
    for row in raw[1:]:
        _, count, price = row.split()
        total_count += int(count)
        total_value += int(count) * int(price)
    return f"{total_count} {total_value}\n"


def solve_knn(text: str) -> str:
    raw = lines(text)
    n, dimensions, queries, k = map(int, raw[0].split())
    train = []
    for row in raw[1 : n + 1]:
        values = list(map(int, row.split()))
        train.append((values[:dimensions], values[-1]))
    answer = []
    for row in raw[n + 1 : n + 1 + queries]:
        target = list(map(int, row.split()))
        nearest = sorted(
            (sum((a - b) ** 2 for a, b in zip(point, target, strict=True)), index, label)
            for index, (point, label) in enumerate(train)
        )[:k]
        counts = Counter(label for _, _, label in nearest)
        answer.append(str(min(counts, key=lambda label: (-counts[label], label))))
    return "\n".join(answer) + "\n"


def solve_round_robin(text: str) -> str:
    raw = lines(text)
    n, quantum = map(int, raw[0].split())
    tasks = sorted((int(a), name, int(b)) for name, a, b in (row.split() for row in raw[1 : n + 1]))
    remaining = {name: burst for _, name, burst in tasks}
    arrival = {name: at for at, name, _ in tasks}
    queue: deque[str] = deque()
    time = index = 0
    answer = []
    while index < n or queue:
        if not queue and index < n and time < tasks[index][0]:
            time = tasks[index][0]
        while index < n and tasks[index][0] <= time:
            queue.append(tasks[index][1])
            index += 1
        name = queue.popleft()
        used = min(quantum, remaining[name])
        remaining[name] -= used
        time += used
        while index < n and tasks[index][0] <= time:
            queue.append(tasks[index][1])
            index += 1
        if remaining[name]:
            queue.append(name)
        else:
            answer.append(f"{name} {time - arrival[name]}")
    return "\n".join(answer) + "\n"


def solve_course_state(text: str) -> str:
    raw = lines(text)
    selected: set[str] = set()
    answer = []
    for row in raw[1:]:
        parts = row.split()
        if parts[0] == "ADD":
            selected.add(parts[1])
        elif parts[0] == "DROP":
            selected.discard(parts[1])
        elif parts[0] == "HAS":
            answer.append("YES" if parts[1] in selected else "NO")
        else:
            answer.append(" ".join(sorted(selected)) if selected else "EMPTY")
    return "\n".join(answer) + "\n"


def solve_command_stats(text: str) -> str:
    raw = lines(text)
    counts = Counter(row.split()[0] for row in raw[1:])
    return "\n".join(f"{key} {counts[key]}" for key in sorted(counts)) + "\n"


def solve_risk_report(text: str) -> str:
    raw = lines(text)
    rows = []
    for row in raw[1:]:
        user_id, age, income, overdue = row.split()
        score = int(overdue) * 35 + (20 if int(income) < 5000 else 0) + (10 if int(age) < 25 else 0)
        rows.append((score, user_id))
    rows.sort(key=lambda item: (-item[0], item[1]))
    return "\n".join(f"{user_id} {score}" for score, user_id in rows) + "\n"


def solve_crawler(text: str) -> str:
    raw = lines(text)
    queue: deque[str] = deque()
    queued: set[str] = set()
    visited: set[str] = set()
    answer = []
    for row in raw[1:]:
        parts = row.split()
        if parts[0] == "ADD":
            url = parts[1]
            if url not in queued and url not in visited:
                queue.append(url)
                queued.add(url)
        elif parts[0] == "POP":
            if queue:
                url = queue.popleft()
                queued.remove(url)
                visited.add(url)
                answer.append(url)
            else:
                answer.append("EMPTY")
        else:
            answer.append(f"{len(queue)} {len(visited)}")
    return "\n".join(answer) + "\n"


def solve_forms(text: str) -> str:
    raw = lines(text)
    state: dict[str, str] = {}
    history: list[dict[str, str]] = []
    answer = []
    for row in raw[1:]:
        parts = row.split()
        if parts[0] == "SET":
            history.append(state.copy())
            state[parts[1]] = parts[2]
        elif parts[0] == "UNDO":
            for _ in range(min(int(parts[1]), len(history))):
                state = history.pop()
        else:
            answer.append(state.get(parts[1], "NULL"))
    return "\n".join(answer) + "\n"


def simple_inputs(values: list[str]) -> list[str]:
    return [value if value.endswith("\n") else value + "\n" for value in values]


def specs() -> list[Spec]:
    rated = [
        Spec("coin_change", "零钱换算", "入门", ["模拟", "算术"], "把给定的整数金额按 100、50、20、10、5、1 六种面额贪心换算。", "一行一个整数金额。", "依次输出六种面额的张数。", "0 ≤ 金额 ≤ 10^9。", "从最大面额开始整除并取余。", simple_inputs(["0", "1", "76", "186", "999"]), solve_coin),
        Spec("leap_calendar", "闰年日历", "入门", ["分支", "日期"], "判断指定年月的天数，采用公历闰年规则。", "一行两个整数 year month。", "输出该月天数。", "1 ≤ year ≤ 9999，1 ≤ month ≤ 12。", "能被 400 整除，或能被 4 但不能被 100 整除的是闰年。", simple_inputs(["2000 2", "1900 2", "2024 2", "2023 11", "2023 12"]), solve_calendar),
        Spec("digit_histogram", "数字位统计", "入门", ["字符串", "计数"], "统计一个十进制整数表示中每个数字出现的次数，负号不计。", "一行一个十进制整数。", "输出数字 0 到 9 的出现次数。", "输入长度不超过 100000。", "按字符扫描即可。", simple_inputs(["0", "-1002", "9876543210", "111223", "909090"]), solve_digits),
        Spec("grade_levels", "成绩等级", "入门", ["分支", "计数"], "按 A≥90、B≥80、C≥70、D≥60、F<60 统计成绩。", "第一行 n，第二行 n 个整数成绩。", "依次输出 A B C D F 的人数。", "1 ≤ n ≤ 100000，0 ≤ 成绩 ≤ 100。", "边界分数属于较高等级。", simple_inputs(["1\n100", "5\n90 80 70 60 59", "4\n0 1 2 3", "6\n89 89 79 69 99 100", "3\n60 60 60"]), solve_grades),
        Spec("tiered_billing", "阶梯计费", "入门", ["分支", "算术"], "用量前 100 单位每单位 2 元，接下来 100 单位每单位 3 元，超过 200 的部分每单位 5 元。", "一行非负整数用量。", "输出总费用。", "0 ≤ 用量 ≤ 10^9。", "分段计算每一档。", simple_inputs(["0", "100", "101", "200", "345"]), solve_tier),
        Spec("word_frequency_winner", "词频冠军", "简单", ["哈希表", "字符串"], "找出出现次数最多的单词；次数相同时输出字典序最小者。", "一行由小写单词和空格组成的文本。", "输出单词及出现次数。", "单词总数 1..100000。", "计数后按次数降序、单词升序比较。", simple_inputs(["a", "cat dog cat", "b a b a", "red blue green red blue red", "z y x"]), solve_word_frequency),
        Spec("matrix_rotate", "矩阵旋转", "简单", ["矩阵", "模拟"], "将 n×m 整数矩阵顺时针旋转 90 度。", "第一行 n m，随后 n 行矩阵。", "输出旋转后的 m×n 矩阵。", "1 ≤ n,m ≤ 500。", "新矩阵第 j 行来自原矩阵第 j 列的逆序。", simple_inputs(["1 1\n5", "2 3\n1 2 3\n4 5 6", "3 1\n1\n2\n3", "2 2\n-1 0\n2 3", "1 4\n1 2 3 4"]), solve_rotate),
        Spec("merge_appointments", "合并预约", "简单", ["排序", "区间"], "合并所有重叠或首尾相接的预约时间段。", "第一行 n，随后 n 行闭区间 l r。", "先输出合并后数量，再逐行输出区间。", "1 ≤ n ≤ 100000，0 ≤ l ≤ r ≤ 10^9。", "按左端点排序后线性扫描。", simple_inputs(["1\n1 2", "3\n1 3\n2 5\n8 9", "3\n5 5\n1 2\n2 4", "4\n1 1\n3 3\n5 5\n7 7", "3\n-2 0\n0 2\n10 20"]), solve_merge),
        Spec("roster_relations", "名单关系", "简单", ["并查集", "图"], "给出人员之间的同组关系，回答两人是否通过关系链属于同一组。", "第一行 n m q；随后 m 行关系和 q 行询问，人员编号为 1..n。", "每个询问输出 YES 或 NO。", "1 ≤ n,m,q ≤ 200000。", "使用并查集合并关系。", simple_inputs(["3 1 2\n1 2\n1 2\n1 3", "4 3 2\n1 2\n2 3\n3 4\n1 4\n2 4", "2 0 1\n1 2", "5 2 3\n1 5\n2 3\n1 5\n3 2\n4 5", "1 0 1\n1 1"]), solve_relations),
        Spec("run_length_encode", "游程编码", "简单", ["字符串", "模拟"], "把连续相同字符编码为字符和连续长度。", "一行仅含大小写英文字母的非空字符串。", "各段输出为 字符+长度，以空格分隔。", "1 ≤ 长度 ≤ 100000。", "记录当前段起点。", simple_inputs(["A", "AAABB", "abbbbCC", "xyz", "ZZZZZZZZZZ"]), solve_rle),
        Spec("dynamic_range_sum", "动态区间和", "中等", ["树状数组", "数据结构"], "维护整数序列，支持单点赋值和闭区间求和。", "第一行 n q，第二行数组；操作 U i x 或 Q l r。", "每个 Q 输出区间和。", "1 ≤ n,q ≤ 200000。", "树状数组维护差值更新。", simple_inputs(["3 3\n1 2 3\nQ 1 3\nU 2 5\nQ 2 3", "1 2\n-2\nQ 1 1\nU 1 0", "4 4\n0 0 0 0\nU 4 9\nQ 1 4\nU 1 -3\nQ 1 1", "5 2\n1 2 3 4 5\nQ 3 3\nQ 2 5", "2 3\n10 -10\nQ 1 2\nU 1 7\nQ 1 2"]), solve_dynamic_sum),
        Spec("obstacle_shortest_path", "带障碍最短路", "中等", ["BFS", "网格"], "在网格中从 S 四方向移动到 E，# 不可经过，求最少步数。", "第一行 n m，随后 n 行网格。", "不可达输出 -1，否则输出最少步数。", "1 ≤ n,m ≤ 1000，恰有一个 S 和 E。", "无权图最短路使用 BFS。", simple_inputs(["1 2\nSE", "2 2\nS#\n.E", "3 3\nS..\n##.\n..E", "3 4\nS#..\n.#E.\n....", "4 4\nS...\n.##.\n....\n...E"]), solve_grid),
        Spec("arithmetic_expression", "表达式求值", "中等", ["栈", "解析"], "计算包含整数、括号、+、-、* 和一元负号的表达式。", "一行合法表达式，不含空格。", "输出整数结果。", "表达式长度不超过 200000，中间结果在 64 位整数内。", "用运算符栈处理优先级与括号。", simple_inputs(["1+2*3", "(1+2)*3", "-5+2*4", "10-(2+3)*2", "2*(-3+7)"]), solve_expression),
        Spec("quota_enrollment", "限额选课", "中等", ["排序", "结构体"], "课程按分数从高到低录取 quota 人；同分按姓名字典序。", "第一行 n quota，随后每行姓名和分数。", "按录取优先级逐行输出姓名。", "1 ≤ quota ≤ n ≤ 200000，姓名不重复。", "使用复合排序键。", simple_inputs(["3 2\na 90\nb 80\nc 95", "2 1\nz 100\na 100", "1 1\nsolo 0", "4 3\nd 60\nc 60\nb 60\na 60", "5 2\nu1 1\nu2 5\nu3 3\nu4 4\nu5 2"]), solve_quota),
        Spec("course_dependencies", "课程依赖", "中等", ["拓扑排序", "图"], "课程依赖边 a b 表示必须先修 a 再修 b，输出字典序最小的可行编号序列。", "第一行 n m，随后 m 行依赖。", "有环输出 CYCLE，否则输出顺序。", "1 ≤ n,m ≤ 200000。", "用小根堆维护当前入度为零的课程。", simple_inputs(["3 2\n1 2\n2 3", "3 2\n1 3\n2 3", "2 2\n1 2\n2 1", "4 0", "4 3\n4 2\n1 2\n2 3"]), solve_dependencies),
        Spec("range_update_query", "区间修改与查询", "困难", ["线段树", "懒标记"], "维护数组，支持区间加法和区间求和。", "第一行 n q，第二行数组；操作 ADD l r x 或 SUM l r。", "每个 SUM 输出一行。", "1 ≤ n,q ≤ 200000，答案在 64 位整数内。", "线段树用懒标记下传区间增量。", simple_inputs(["3 3\n1 2 3\nSUM 1 3\nADD 1 2 4\nSUM 2 3", "1 3\n0\nADD 1 1 -2\nSUM 1 1\nSUM 1 1", "4 4\n1 1 1 1\nADD 1 4 2\nSUM 1 4\nADD 2 3 -1\nSUM 2 3", "5 2\n5 4 3 2 1\nSUM 3 5\nADD 1 5 100", "2 3\n-5 5\nSUM 1 2\nADD 2 2 -5\nSUM 1 2"]), solve_range_add),
        Spec("weighted_appointments", "带权预约", "困难", ["动态规划", "二分"], "每个半开预约区间 [s,e) 有收益，选择互不重叠的预约使总收益最大。", "第一行 n，随后 n 行 s e value。", "输出最大总收益。", "1 ≤ n ≤ 200000，0 ≤ s < e ≤ 10^9。", "按结束时间排序，并二分最后一个相容区间。", simple_inputs(["1\n0 1 5", "3\n1 3 5\n3 5 6\n2 4 20", "4\n1 2 3\n2 3 4\n3 4 5\n1 4 20", "3\n0 10 1\n0 5 10\n5 10 10", "5\n1 2 2\n2 5 8\n1 4 7\n5 6 3\n4 6 9"]), solve_weighted_schedule),
        Spec("tree_path_statistics", "树上路径统计", "困难", ["树", "差分"], "给定一棵树和多条路径，按输入边顺序统计每条边被多少条路径经过。", "第一行 n q，随后 n-1 行边，再 q 行路径端点。", "输出 n-1 个边使用次数。", "2 ≤ n,q ≤ 200000。", "对路径端点做树上差分，再自底向上累加。", simple_inputs(["2 2\n1 2\n1 2\n2 1", "3 2\n1 2\n2 3\n1 3\n1 2", "4 2\n1 2\n1 3\n1 4\n2 3\n3 4", "5 3\n1 2\n2 3\n3 4\n4 5\n1 5\n2 4\n3 3", "4 1\n1 2\n2 3\n3 4\n4 4"]), solve_tree_counts),
        Spec("minimum_cost_matching", "最小费用匹配", "困难", ["二分图", "最小费用"], "把 n 名学生与 n 个项目一一匹配，给定费用矩阵，求最小总费用。", "第一行 n，随后 n 行费用矩阵。", "输出最小总费用。", "1 ≤ n ≤ 20，费用非负；需使用状态压缩 DP。", "状态表示已使用的项目集合。", simple_inputs(["1\n7", "2\n1 9\n8 2", "3\n9 2 7\n6 4 3\n5 8 1", "3\n1 1 1\n1 1 1\n1 1 1", "4\n4 1 3 2\n2 0 5 3\n3 2 2 3\n4 3 1 2"]), solve_matching),
        Spec("multi_pattern_matching", "多模式匹配", "困难", ["AC 自动机", "字符串"], "统计每个模式串在文本中出现的次数，允许重叠。", "第一行小写文本，第二行 k，随后 k 行模式串。", "按输入顺序输出每个模式的出现次数。", "文本和模式总长度不超过 500000。", "构建 AC 自动机并沿 fail 树汇总出现次数。", simple_inputs(["aaaa\n2\na\naa", "abcabc\n3\nabc\nbc\nc", "xyz\n2\na\nxyz", "abababa\n3\naba\nbab\nab", "mississippi\n4\nissi\nss\ni\nppi"]), solve_patterns),
        Spec("offline_dynamic_connectivity", "离线动态连通性", "挑战", ["可撤销并查集", "分治"], "无向图支持加边、删边和连通性询问；同一边不会重复加入或删除不存在的边。", "第一行 n q，随后 q 行 + u v、- u v 或 ? u v。", "每个询问输出 YES 或 NO。", "1 ≤ n,q ≤ 200000。", "把边的生存区间加入时间线段树，DFS 时使用可撤销并查集。", simple_inputs(["3 5\n+ 1 2\n? 1 2\n? 1 3\n+ 2 3\n? 1 3", "2 4\n+ 1 2\n? 1 2\n- 1 2\n? 1 2", "4 6\n+ 1 2\n+ 3 4\n? 1 4\n+ 2 3\n? 1 4\n- 2 3", "1 1\n? 1 1", "5 7\n+ 1 2\n+ 2 3\n? 1 3\n- 1 2\n? 1 3\n+ 4 5\n? 4 5"]), solve_connectivity),
        Spec("tree_chain_operations", "树链修改与查询", "挑战", ["重链剖分", "线段树"], "维护树上节点权值，支持路径加法与路径求和。", "第一行 n q，第二行节点权值，随后 n-1 行边，再 q 行 ADD u v x 或 SUM u v。", "每个 SUM 输出一行。", "1 ≤ n,q ≤ 200000。", "重链剖分把路径拆成若干连续区间。", simple_inputs(["2 3\n1 2\n1 2\nSUM 1 2\nADD 1 2 3\nSUM 1 1", "3 2\n1 1 1\n1 2\n2 3\nADD 1 3 2\nSUM 1 3", "4 3\n1 2 3 4\n1 2\n1 3\n1 4\nSUM 2 3\nADD 3 4 -1\nSUM 3 4", "1 2\n5\nSUM 1 1\nADD 1 1 10", "5 3\n0 0 0 0 0\n1 2\n2 3\n3 4\n4 5\nADD 2 4 7\nSUM 1 5\nSUM 2 3"]), solve_tree_chain),
        Spec("costed_transport_network", "带费用运输网络", "挑战", ["最小费用最大流", "网络流"], "从若干仓库向若干门店运输，满足全部需求且不超过供给，求最小运输费用。", "第一行 n m；第二行供给，第三行需求；随后 n 行单位费用矩阵。", "输出满足需求的最小总费用。", "总供给不少于总需求，n,m ≤ 30，数量非负。", "建立源点、仓库、门店和汇点的最小费用流网络。", simple_inputs(["1 1\n5\n3\n2", "2 2\n3 3\n2 4\n1 5\n4 2", "2 1\n2 5\n6\n3\n1", "1 3\n10\n2 3 1\n5 1 4", "3 2\n2 2 2\n3 3\n1 9\n4 4\n9 1"]), solve_transport),
        Spec("repeated_substring_queries", "重复子串查询", "挑战", ["后缀数组", "字符串"], "对每个 k，求至少出现 k 次的最长子串长度，出现可重叠。", "第一行小写字符串，第二行 q，随后 q 行 k。", "每个询问输出最大长度；不存在输出 0。", "字符串长度和 q 均不超过 200000，2 ≤ k。", "后缀数组的 LCP 区间可转化为离线查询。", simple_inputs(["aaaa\n3\n2\n3\n4", "banana\n2\n2\n3", "abc\n2\n2\n4", "abababa\n2\n2\n3", "mississippi\n3\n2\n3\n5"]), solve_repeated),
        Spec("segmented_cost_optimization", "分段代价优化", "挑战", ["动态规划优化", "凸包"], "把非负数组恰好分成 k 个非空连续段，总代价为每段元素和的平方，求最小总代价。", "第一行 n k，第二行 n 个非负整数。", "输出最小总代价。", "1 ≤ k ≤ n ≤ 200000，元素和不超过 10^9。", "转移式可展开成直线最值并用凸包优化。", simple_inputs(["3 1\n1 2 3", "3 3\n1 2 3", "4 2\n1 1 1 1", "5 2\n5 0 0 0 5", "6 3\n1 2 1 2 1 2"]), solve_partition),
    ]

    mock_a = [
        Spec("mock_a_inventory_summary", "仓库盘点汇总", "", ["模拟卷A", "基础语法"], "汇总多种商品的库存件数和库存金额，金额均为整数分。", "第一行 n；随后每行商品编号、数量、单价。", "输出总件数和总金额。", "1 ≤ n ≤ 100000，数量与单价非负。", "逐行累加，注意总金额使用 64 位整数。", [f"{n}\n" + "\n".join(f"p{i} {i + 1} {10 + i}" for i in range(n)) + "\n" for n in range(1, 11)], solve_inventory, "程序设计训练期末模拟卷 A"),
        Spec("mock_a_batch_knn", "批量 KNN 推断", "", ["模拟卷A", "NumPy", "机器学习"], "使用欧氏距离完成批量 KNN 分类。距离相同时按训练行序稳定选择；投票相同时选择较小标签。允许使用 numpy.asarray、广播、sum、argsort、unique。", "第一行 n d q k；随后 n 行 d 个整数特征和标签；再 q 行查询特征。", "每个查询输出预测标签。", "1 ≤ n,q ≤ 5000，1 ≤ d ≤ 30，1 ≤ k ≤ n。", "可用 NumPy 广播一次计算一个查询到全部训练样本的平方距离。", [f"3 2 {q} {1 + q % 3}\n0 0 0\n2 0 1\n0 2 1\n" + "\n".join(f"{i % 3} {(i * 2) % 3}" for i in range(q)) + "\n" for q in range(1, 11)], solve_knn, "程序设计训练期末模拟卷 A", memory_limit=512),
        Spec("mock_a_round_robin", "轮转任务调度器", "", ["模拟卷A", "大模拟", "队列"], "按到达时间执行 Round Robin 调度。每个时间片结束时，先将期间到达的任务入队，再把未完成任务放回队尾。", "第一行 n quantum；随后每行任务名、到达时间、运行时长。", "按完成顺序输出任务名和周转时间。", "1 ≤ n ≤ 100000，任务名唯一，quantum≥1。", "事件时间推进配合 FIFO 队列。", [f"{n} {1 + n % 4}\n" + "\n".join(f"t{i} {i // 2} {i % 5 + 1}" for i in range(n)) + "\n" for n in range(1, 11)], solve_round_robin, "程序设计训练期末模拟卷 A"),
        Spec("mock_a_course_state", "选课系统状态机", "", ["模拟卷A", "大模拟", "状态机"], "维护当前选课集合。ADD 重复课程和 DROP 不存在课程均为幂等操作；HAS 查询是否存在；LIST 按字典序列出全部课程。", "第一行操作数 q，随后为 ADD id、DROP id、HAS id 或 LIST。", "依次输出 HAS 和 LIST 的结果；空列表输出 EMPTY。", "1 ≤ q ≤ 200000。", "用集合保存状态，仅在 LIST 时排序。", [f"{4 + i}\nADD c1\nHAS c1\nDROP c1\nLIST\n" + "\n".join("ADD c2" if j % 2 == 0 else "HAS c2" for j in range(i)) + "\n" for i in range(10)], solve_course_state, "程序设计训练期末模拟卷 A"),
    ]
    mock_b = [
        Spec("mock_b_command_stats", "命令记录统计", "", ["模拟卷B", "基础语法"], "统计命令日志中每种命令名出现的次数，并按命令名字典序输出。", "第一行 n，随后 n 行非空命令；命令名是每行第一个字段。", "逐行输出命令名和次数。", "1 ≤ n ≤ 200000。", "按空白切分首字段并用字典计数。", [f"{n}\n" + "\n".join(("GET /x" if i % 3 == 0 else "POST /y" if i % 3 == 1 else "DELETE /z") for i in range(n)) + "\n" for n in range(1, 11)], solve_command_stats, "程序设计训练期末模拟卷 B"),
        Spec("mock_b_risk_report", "风险评分报表", "", ["模拟卷B", "Pandas", "机器学习"], "为每位用户计算规则风险分：每次逾期 35 分，收入低于 5000 加 20 分，年龄低于 25 加 10 分；按风险分降序、用户 ID 升序生成报表。允许使用 pandas.DataFrame、布尔索引、sort_values。", "第一行 n；随后每行 user_id age income overdue。", "逐行输出 user_id 和风险分。", "1 ≤ n ≤ 200000，各字段为整数且 user_id 唯一。", "用向量化布尔表达式生成 score 列，再稳定排序。", [f"{n}\n" + "\n".join(f"u{i:02d} {18 + i} {3000 + i * 700} {i % 4}" for i in range(n)) + "\n" for n in range(1, 11)], solve_risk_report, "程序设计训练期末模拟卷 B", memory_limit=512),
        Spec("mock_b_crawler_queue", "单线程爬虫队列", "", ["模拟卷B", "大模拟", "队列"], "模拟单线程爬虫。ADD 仅把从未入队且未访问的 URL 加入队尾；POP 访问队首或输出 EMPTY；STAT 输出待访问数和已访问数。", "第一行 q，随后为 ADD url、POP 或 STAT。", "依次输出 POP 与 STAT 的结果。", "1 ≤ q ≤ 200000，URL 不含空格。", "同时维护队列、queued 集合和 visited 集合。", [f"{5 + i}\nADD /a\nADD /b\nPOP\nSTAT\nADD /a\n" + "\n".join("POP" if j % 2 else f"ADD /x{j}" for j in range(i)) + "\n" for i in range(10)], solve_crawler, "程序设计训练期末模拟卷 B"),
        Spec("mock_b_form_undo", "表单版本与撤销", "", ["模拟卷B", "大模拟", "撤销"], "维护键值表单。每次 SET 产生一个版本；UNDO k 撤销最近最多 k 次 SET；GET 查询当前值，不存在输出 NULL。", "第一行 q，随后为 SET key value、UNDO k 或 GET key。", "依次输出 GET 的结果。", "1 ≤ q ≤ 200000，键和值不含空格。", "保存可回滚的变更记录，UNDO 不产生新版本。", [f"{6 + i}\nSET a 1\nGET a\nSET a 2\nUNDO 1\nGET a\nGET b\n" + "\n".join(f"SET k{j} v{j}" for j in range(i)) + "\n" for i in range(10)], solve_forms, "程序设计训练期末模拟卷 B"),
    ]
    return rated + mock_a + mock_b


def materialize(spec: Spec) -> dict[str, object]:
    tests = [{"input": value, "output": spec.solve(value)} for value in spec.inputs]
    return {
        "id": spec.id,
        "title": spec.title,
        "description": spec.description,
        "input_description": spec.input_description,
        "output_description": spec.output_description,
        "samples": tests[:2],
        "constraints": spec.constraints,
        "testcases": tests,
        "hint": spec.hint,
        "source": spec.source,
        "tags": spec.tags,
        "time_limit": spec.time_limit,
        "memory_limit": spec.memory_limit,
        "author": "Atelier OJ",
        "difficulty": spec.difficulty,
        "public_cases": False,
    }


def validate(items: list[Spec]) -> None:
    assert len(items) == 33
    assert len({item.id for item in items}) == 33
    counts = Counter(item.difficulty for item in items)
    assert {level: counts[level] for level in ("入门", "简单", "中等", "困难", "挑战")} == {
        level: 5 for level in ("入门", "简单", "中等", "困难", "挑战")
    }
    assert counts[""] == 8
    for item in items:
        problem = materialize(item)
        assert all(case["output"].endswith("\n") for case in problem["testcases"])  # type: ignore[index,union-attr]
        if "模拟卷" in " ".join(item.tags):
            assert len(item.inputs) == 10


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args()
    items = specs()
    validate(items)
    if args.check:
        return
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for item in items:
        path = SEED_DIR / f"{item.id}.json"
        path.write_text(json.dumps(materialize(item), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

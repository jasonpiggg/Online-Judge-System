import {
  cleanup,
  fireEvent,
  render,
  screen,
  act,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchInput } from "./SearchInput";
import { EvaluationView, ScoreBadge } from "./Evaluation";
import { RichText } from "./Markdown";
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
describe("Chinese search", () => {
  it("keeps pinyin local until composition ends, supports Enter and clear", () => {
    vi.useFakeTimers();
    const commit = vi.fn();
    render(
      <SearchInput
        value=""
        onCommit={commit}
        navigationKey="a"
        label="搜索"
        placeholder="搜索"
      />,
    );
    const input = screen.getByRole("textbox");
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "kuohao" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    act(() => vi.advanceTimersByTime(400));
    expect(commit).not.toHaveBeenCalled();
    expect(input).toHaveValue("kuohao");
    fireEvent.compositionEnd(input, { target: { value: "括号" } });
    expect(commit).toHaveBeenLastCalledWith("括号");
    fireEvent.change(input, { target: { value: "括号2" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(commit).toHaveBeenLastCalledWith("括号2");
    fireEvent.click(screen.getByLabelText("清空搜索"));
    expect(commit).toHaveBeenLastCalledWith("");
  });
  it("cancels stale search when browser navigation restores the URL", () => {
    vi.useFakeTimers();
    const commit = vi.fn();
    const { rerender } = render(
      <SearchInput
        value="old"
        onCommit={commit}
        navigationKey="a"
        label="搜索"
        placeholder="搜索"
      />,
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "late" },
    });
    rerender(
      <SearchInput
        value="restored"
        onCommit={commit}
        navigationKey="b"
        label="搜索"
        placeholder="搜索"
      />,
    );
    act(() => vi.advanceTimersByTime(500));
    expect(screen.getByRole("textbox")).toHaveValue("restored");
    expect(commit).not.toHaveBeenCalled();
  });
});
it("paginates real test cases and distinguishes points from case counts", () => {
  const cases = Array.from({ length: 103 }, (_, i) => ({
    id: i + 1,
    result: i === 100 ? "WA" : "AC",
    time: 0.1,
    memory: 2,
  }));
  render(
    <EvaluationView
      submission={{
        submission_id: "1",
        problem_id: "x",
        language: "python",
        created_at: "",
        status: "success",
        score: 1020,
        counts: 1030,
        evaluation: {
          status: "success",
          verdict: "partial",
          score: 1020,
          max_score: 1030,
          executed_cases: 103,
          total_cases: 103,
          passed_cases: 102,
          all_passed: false,
          result_counts: { AC: 102, WA: 1 },
        },
      }}
      cases={cases}
    />,
  );
  expect(screen.getAllByRole("button", { name: /^测试点/ })).toHaveLength(50);
  fireEvent.click(screen.getByRole("button", { name: "未通过" }));
  fireEvent.click(screen.getByRole("button", { name: "测试点 101 WA" }));
  expect(screen.getByText("耗时 0.1 秒")).toBeInTheDocument();
  expect(screen.getByText("得分")).toBeInTheDocument();
});
it("shows a private-log explanation without exposing case controls", () => {
  render(
    <EvaluationView
      submission={{
        submission_id: "1",
        problem_id: "x",
        language: "python",
        created_at: "",
        status: "success",
        score: 10,
        counts: 20,
        evaluation: {
          status: "success",
          verdict: "partial",
          score: 10,
          max_score: 20,
          executed_cases: null,
          total_cases: null,
          passed_cases: null,
          all_passed: false,
          result_counts: {},
        },
      }}
      caseDetailsHidden
    />,
  );
  expect(screen.getByText(/未公开测试点明细/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "全部" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("读取测试点…")).not.toBeInTheDocument();
});
it("renders math, preserves streaming fragments and exposes invalid math safely", () => {
  const { container, rerender } = render(
    <RichText
      text={
        "$a_i^2$ $\\frac{a}{b}$ $\\sum_{i=1}^n i$ $O(n \\log n)$\n\n$$\n\\begin{pmatrix}1&2\\\\3&4\\end{pmatrix}\n$$"
      }
    />,
  );
  expect(container.querySelectorAll(".katex")).toHaveLength(5);
  expect(container.querySelector(".katex-html [style]")).not.toBeNull();
  rerender(<RichText text={"$$\n\\frac{a"} />);
  expect(container.querySelector(".katex")).toBeNull();
  expect(container).toHaveTextContent("\\frac{a");
  rerender(<RichText text={"$\\invalidcommand{x}$"} />);
  expect(container).toHaveTextContent("公式格式需检查");
  rerender(<RichText text={"$$a+b=c$$"} />);
  expect(container.querySelector(".katex")).not.toBeNull();
});

it.each([
  [100, 100, "满分", "AC"],
  [40, 100, "部分得分", "partial"],
  [0, 100, "零分", "failed"],
  [0, 0, "仅显示得分", "unknown"],
  [null, 100, "仅显示得分", "unknown"],
  [110, 100, "仅显示得分", "unknown"],
  [-1, 100, "仅显示得分", "unknown"],
  [NaN, 100, "仅显示得分", "unknown"],
])("uses only valid disclosed scores %s/%s", (score, maxScore, label, tone) => {
  const { container } = render(
    <ScoreBadge score={score as number | null} maxScore={maxScore as number} />,
  );
  expect(screen.getByText(label as string)).toBeInTheDocument();
  expect(container.querySelector(`.tone-${tone} .icon`)).not.toBeNull();
});

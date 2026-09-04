import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "./ui/button";

type Mode = "split" | "unified";
type Segment = { value: string; tone?: "add" | "remove" };
const proseFields = new Set(["title", "description", "input_description", "output_description", "constraints", "hint", "source", "author", "review"]);
const labels: Record<string, string> = {
  title: "标题", description: "题目描述", input_description: "输入格式",
  output_description: "输出格式", constraints: "数据范围", hint: "提示",
  samples: "公开样例", testcases: "评测测试点", difficulty: "难度",
  tags: "标签", time_limit: "时间限制", memory_limit: "内存限制",
  public_cases: "日志公开", source: "来源", author: "作者",
};

function text(value: unknown) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2) ?? "";
}

function changedParts(before: string, after: string, words: boolean): [Segment[], Segment[]] {
  const split = (value: string) => words ? value.split(/(\s+|(?=[，。；：、,.!?()（）]))/) : value.split(/(?<=\n)/);
  const left = split(before), right = split(after);
  let start = 0;
  while (start < left.length && start < right.length && left[start] === right[start]) start++;
  let end = 0;
  while (end < left.length - start && end < right.length - start && left[left.length - 1 - end] === right[right.length - 1 - end]) end++;
  const prefix = left.slice(0, start).join("");
  const suffix = end ? left.slice(left.length - end).join("") : "";
  return [
    [{ value: prefix }, { value: left.slice(start, end ? left.length - end : undefined).join(""), tone: "remove" }, { value: suffix }],
    [{ value: prefix }, { value: right.slice(start, end ? right.length - end : undefined).join(""), tone: "add" }, { value: suffix }],
  ];
}

function Parts({ values }: { values: Segment[] }) {
  return <pre className="diff-text">{values.map((part, index) => <span className={part.tone ? `diff-${part.tone}` : ""} key={index}>{part.value}</span>)}</pre>;
}

export function DiffView({ before, after }: { before: Record<string, unknown>; after: Record<string, unknown> }) {
  const [mode, setMode] = useState<Mode>(() => typeof window.matchMedia === "function" && window.matchMedia("(max-width: 700px)").matches ? "unified" : "split");
  const [showSame, setShowSame] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(max-width: 700px)");
    const change = () => setMode(media.matches ? "unified" : "split");
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  const rows = useMemo(() => Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).map((key) => {
    const oldText = text(before[key]);
    const newText = text(after[key]);
    return { key, oldText, newText, same: oldText === newText, parts: changedParts(oldText, newText, proseFields.has(key)) };
  }).filter((row) => showSame || !row.same), [before, after, showSame]);
  return (
    <section className={`diff-view diff-layout-${mode}`}>
      <div className="diff-toolbar">
        <div className="segmented" aria-label="差异布局">
          <Button aria-pressed={mode === "split"} onClick={() => setMode("split")}>并排</Button>
          <Button aria-pressed={mode === "unified"} onClick={() => setMode("unified")}>单列</Button>
        </div>
        <label className="inline-check"><input type="checkbox" checked={showSame} onChange={(event) => setShowSame(event.target.checked)} />显示未修改字段</label>
      </div>
      {rows.length ? rows.map((row) => (
        <article className={`diff-field ${row.same ? "same" : ""}`} key={row.key}>
          <h3>{labels[row.key] || row.key}</h3>
          {mode === "split" ? (
            <div className="diff-columns"><DiffSide title="修改前" tone="remove">{row.same ? <Parts values={[{ value: row.oldText }]} /> : <Parts values={row.parts[0]} />}</DiffSide><DiffSide title="修改后" tone="add">{row.same ? <Parts values={[{ value: row.newText }]} /> : <Parts values={row.parts[1]} />}</DiffSide></div>
          ) : (
            <div className="diff-unified"><DiffSide title="− 修改前" tone="remove"><Parts values={row.parts[0]} /></DiffSide><DiffSide title="+ 修改后" tone="add"><Parts values={row.parts[1]} /></DiffSide></div>
          )}
        </article>
      )) : <p className="empty compact">没有检测到字段变化。</p>}
    </section>
  );
}

function DiffSide({ title, tone, children }: { title: string; tone: "add" | "remove"; children: ReactNode }) {
  return <div className={`diff-side tone-${tone}`}><strong>{title}</strong>{children}</div>;
}

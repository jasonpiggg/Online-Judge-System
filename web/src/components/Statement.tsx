import type { Problem } from "../types";
import { Code, RichText } from "./Markdown";
export function Statement({ problem: p }: { problem: Problem }) {
  return (
    <article className="statement">
      <RichText text={p.description} />
      {[
        ["输入格式", p.input_description],
        ["输出格式", p.output_description],
      ].map(([title, text]) => (
        <section key={title}>
          <h3>{title}</h3>
          <RichText text={text} />
        </section>
      ))}
      <section>
        <h3>样例</h3>
        {p.samples?.map((s, i) => (
          <div key={i}>
            <p className="muted">样例 {i + 1}</p>
            <div className="samples">
              <div>
                <h4>输入</h4>
                <Code text={s.input} />
              </div>
              <div>
                <h4>输出</h4>
                <Code text={s.output} />
              </div>
            </div>
          </div>
        ))}
      </section>
      <section>
        <h3>数据范围</h3>
        <RichText text={p.constraints} />
      </section>
      {p.hint && (
        <details>
          <summary>解题提示</summary>
          <RichText text={p.hint} />
        </details>
      )}
    </article>
  );
}

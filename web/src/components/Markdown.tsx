import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import katex from "katex";
import { useState, type ReactNode } from "react";
import "katex/dist/katex.min.css";

// remark-math accepts an unclosed display fence. While streaming, keep it literal.
function unfinishedMath() {
  return (tree: any, file: any) => {
    const source = String(file.value);
    const visit = (node: any) => {
      if (!node.children) return;
      node.children = node.children.map((child: any) => {
        if (child.type === "math") {
          const raw = source.slice(
            child.position.start.offset,
            child.position.end.offset,
          );
          const lines = raw.trim().split("\n");
          if (
            !/^\${2}[^\n]+\${2}$/.test(raw.trim()) &&
            (lines.length < 2 ||
              !/^\s*\${2,}\s*$/.test(lines[lines.length - 1]))
          )
            return {
              type: "paragraph",
              children: [{ type: "text", value: raw }],
            };
        }
        if (child.type === "math" || child.type === "inlineMath") {
          try {
            katex.renderToString(child.value, {
              throwOnError: true,
              trust: false,
            });
          } catch {
            return {
              type: "inlineCode",
              value: child.value,
              data: {
                hName: "span",
                hProperties: { className: ["katex-error"] },
              },
            };
          }
        }
        visit(child);
        return child;
      });
    };
    visit(tree);
  };
}
export function logText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "message" in value)
    return String(value.message);
  return JSON.stringify(value, null, 2) || "";
}
export function Copy({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <button
      className="copy"
      type="button"
      onClick={() =>
        void navigator.clipboard
          .writeText(text)
          .then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          })
          .catch(() => setFailed(true))
      }
    >
      {copied ? "已复制" : failed ? "请手动选择复制" : "复制"}
    </button>
  );
}
export function Code({ text: raw }: { text: unknown }) {
  const text = logText(raw);
  return (
    <div className="code-block">
      <Copy text={text} />
      <pre>
        <code>{text}</code>
      </pre>
    </div>
  );
}
function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node)
    return textOf((node.props as { children?: ReactNode }).children);
  return "";
}
export function RichText({ text }: { text: unknown }) {
  return (
    <div className="markdown">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm, remarkMath, unfinishedMath]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={{
          span: ({ node: _node, className, children, ...props }) =>
            className?.includes("katex-error") ? (
              <span className="math-fallback">
                <code>{children}</code>
                <span className="muted">（公式格式需检查）</span>
              </span>
            ) : (
              <span {...props} className={className}>
                {children}
              </span>
            ),
          pre: ({ children }) => (
            <div className="code-block">
              <Copy text={textOf(children)} />
              <pre>{children}</pre>
            </div>
          ),
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {typeof text === "string" ? text : ""}
      </Markdown>
    </div>
  );
}

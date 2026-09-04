import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import { useState, type ReactNode } from "react";
import "katex/dist/katex.min.css";
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
export function Code({ text }: { text: string }) {
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
export function RichText({ text }: { text: string }) {
  return (
    <div className="markdown">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={{
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
        {text}
      </Markdown>
    </div>
  );
}

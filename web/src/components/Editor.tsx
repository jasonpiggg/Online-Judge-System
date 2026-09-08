import Editor, { loader } from "@monaco-editor/react";
import { useRef } from "react";
import * as monaco from "monaco-editor/editor/editor.api";
import "monaco-editor/languages/definitions/python/register";
import "monaco-editor/languages/definitions/cpp/register";
import "monaco-editor/languages/definitions/javascript/register";
import "monaco-editor/languages/definitions/java/register";
import "monaco-editor/languages/definitions/go/register";
import "monaco-editor/languages/definitions/rust/register";
import EditorWorker from "monaco-editor/editor/editor.worker?worker&inline";
(globalThis as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};
loader.config({ monaco });
export function editorLanguage(language: string) {
  const aliases: Record<string, string> = { python3: "python", c: "cpp", "c++": "cpp", node: "javascript", nodejs: "javascript" };
  const candidate = aliases[language] || language;
  return ["python", "cpp", "javascript", "java", "go", "rust"].includes(candidate) ? candidate : "plaintext";
}
export function CodeEditor({
  value,
  onChange,
  language = "python",
  size = 14,
  onSubmit,
}: {
  value: string;
  onChange: (v: string) => void;
  language?: string;
  size?: number;
  onSubmit?: () => void;
}) {
  const submit = useRef(onSubmit);
  submit.current = onSubmit;
  return (
    <Editor
      height="var(--editor-height, 520px)"
      language={editorLanguage(language)}
      theme="vs"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      onMount={(editor) => {
        void document.fonts?.load('14px "JetBrains Mono"').then(() => monaco.editor.remeasureFonts()).catch(() => { /* System monospace remains available offline. */ });
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () =>
          submit.current?.(),
        );
      }}
      options={{
        fontSize: size,
        fontFamily: '"JetBrains Mono", "Cascadia Code", Consolas, "Microsoft YaHei", monospace',
        lineHeight: Math.round(size * 1.65),
        fontLigatures: false,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 4,
        padding: { top: 10 },
        wordWrap: "on",
        accessibilitySupport: "on",
      }}
    />
  );
}

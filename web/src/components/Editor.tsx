import Editor, { loader } from "@monaco-editor/react";
import { useRef } from "react";
import * as monaco from "monaco-editor/editor/editor.api";
import "monaco-editor/languages/definitions/python/register";
import "monaco-editor/languages/definitions/cpp/register";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
(globalThis as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};
loader.config({ monaco });
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
      language={language.startsWith("py") ? "python" : "cpp"}
      theme="vs"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      onMount={(editor) => {
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () =>
          submit.current?.(),
        );
      }}
      options={{
        fontSize: size,
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

import { useEffect, useRef, useState } from "react";
import { errorText, queryClient } from "../api";
import {
  fileLanguages,
  languageAccept,
  languageOptions,
  useLanguages,
} from "../languages";
import { readCodeFile } from "../file-import";
import { Button } from "./ui/button";
import { Code } from "./Markdown";

export function CodeImport({
  language,
  disabled,
  onApply,
}: {
  language: string;
  disabled: boolean;
  onApply: (language: string, code: string) => Promise<void>;
}) {
  const languages = useLanguages();
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const epoch = useRef(0);
  const [preview, setPreview] = useState<{
    name: string;
    size: number;
    code: string;
  }>();
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(
    () => () => {
      epoch.current++;
    },
    [],
  );
  useEffect(() => {
    if (preview) dialog.current?.showModal();
  }, [preview]);
  const supported = languages.data?.languages || [];
  const matches = preview ? fileLanguages(preview.name, supported) : [];
  const cancel = () => {
    epoch.current++;
    dialog.current?.close();
    setPreview(undefined);
    setBusy(false);
  };
  return (
    <>
      <input
        ref={input}
        type="file"
        hidden
        aria-label="选择代码文件"
        accept={languageAccept(supported)}
        onChange={async (event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          const current = ++epoch.current;
          setError("");
          setBusy(true);
          try {
            const metadata = await queryClient.fetchQuery(languageOptions);
            const matching = fileLanguages(file.name, metadata.languages);
            if (!matching.length)
              throw new Error("当前语言配置不支持此扩展名。");
            const code = await readCodeFile(file);
            if (current !== epoch.current) return;
            setTarget(
              matching.some((item) => item.name === language)
                ? language
                : matching.length === 1
                  ? matching[0].name
                  : "",
            );
            setPreview({ name: file.name, size: file.size, code });
          } catch (e) {
            if (current === epoch.current) setError(errorText(e));
          } finally {
            if (current === epoch.current) setBusy(false);
          }
        }}
      />
      <Button
        type="button"
        disabled={disabled || busy || !supported.length || languages.isError}
        onClick={() => {
          setError("");
          input.current?.click();
        }}
      >
        导入代码文件
      </Button>
      <small className="muted">
        支持 {languageAccept(supported) || "正在读取语言配置…"}
      </small>
      {languages.isError && (
        <Button type="button" onClick={() => void languages.refetch()}>
          重试语言配置
        </Button>
      )}
      {error && !preview && (
        <span role="alert" className="field-error">
          {error}
        </span>
      )}
      <dialog
        ref={dialog}
        className="import-dialog"
        aria-labelledby="code-import-title"
        onCancel={(event) => {
          event.preventDefault();
          if (!busy) cancel();
        }}
      >
        {preview && (
          <>
            <h2 id="code-import-title">导入代码预览</h2>
            <p>
              {preview.name} · {preview.size.toLocaleString()} 字节
            </p>
            <label>
              目标语言
              <select
                aria-label="导入目标语言"
                value={target}
                disabled={busy}
                onChange={(event) => setTarget(event.target.value)}
              >
                <option value="">请选择语言</option>
                {matches.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="muted">
              确认后替换目标语言的编辑器内容并保存；检查代码后再提交评测。
            </p>
            <Code text={preview.code} />
            {error && (
              <p role="alert" className="field-error">
                {error}
              </p>
            )}
            <div className="action-group">
              <Button type="button" disabled={busy} onClick={cancel}>
                取消
              </Button>
              <Button
                type="button"
                variant="default"
                disabled={
                  busy ||
                  disabled ||
                  !matches.some((item) => item.name === target)
                }
                onClick={async () => {
                  const current = epoch.current;
                  setBusy(true);
                  setError("");
                  try {
                    const latest =
                      await queryClient.fetchQuery(languageOptions);
                    if (current !== epoch.current) return;
                    if (
                      !fileLanguages(preview.name, latest.languages).some(
                        (item) => item.name === target,
                      )
                    )
                      throw new Error(
                        "语言配置已变化，请重新选择文件或目标语言。",
                      );
                    await onApply(target, preview.code);
                    if (current === epoch.current) cancel();
                  } catch (e) {
                    if (current === epoch.current) setError(errorText(e));
                  } finally {
                    if (current === epoch.current) setBusy(false);
                  }
                }}
              >
                确认替换代码
              </Button>
            </div>
          </>
        )}
      </dialog>
    </>
  );
}

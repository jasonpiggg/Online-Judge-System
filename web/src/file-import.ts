export async function readTextFile(file: File, limit: number): Promise<string> {
  if (!file.size) throw new Error("文件为空，请选择包含内容的文件。");
  if (file.size > limit)
    throw new Error(`文件过大，上限为 ${limit / 1024 / 1024} MiB。`);
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(
      await file.arrayBuffer(),
    );
  } catch {
    throw new Error("无法读取文件，请使用 UTF-8 编码的文本文件。");
  }
  if (!text.trim()) throw new Error("文件内容为空。");
  if (
    [...text].some(
      (character) =>
        character.charCodeAt(0) < 32 &&
        ![9, 10, 13].includes(character.charCodeAt(0)),
    )
  )
    throw new Error("文件包含二进制或非法控制字符。");
  return text;
}
export async function readCodeFile(file: File) {
  const text = await readTextFile(file, 1024 * 1024);
  if ([...text].length > 200_000)
    throw new Error("代码不能超过 200,000 个字符。");
  return text;
}
export async function readProblemFile(
  file: File,
): Promise<Record<string, unknown>> {
  if (!file.name.toLowerCase().endsWith(".json"))
    throw new Error("请选择 .json 文件。");
  const text = await readTextFile(file, 10 * 1024 * 1024);
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("JSON 格式错误，请检查括号、引号和逗号。");
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("文件必须是单道题目的 JSON 对象。");
  if (!Object.keys(value).length) throw new Error("题目内容为空。");
  // Backend DraftProblem performs strict field/type/size validation before insertion.
  return value as Record<string, unknown>;
}

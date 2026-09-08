import { describe, expect, it } from "vitest";
import { readCodeFile, readProblemFile } from "./file-import";
import { fileLanguages, languageAccept, type Language } from "./languages";
function file(name: string, text: string | Uint8Array, size?: number): File {
  const data = typeof text === "string" ? new TextEncoder().encode(text) : text;
  return {
    name,
    size: size ?? data.byteLength,
    arrayBuffer: async () => data.buffer,
  } as File;
}
const python = { name: "python", file_ext: ".py" } as Language;
const cpp = { name: "cpp", file_ext: ".cpp" } as Language;
describe("file imports", () => {
  it("preserves UTF-8 Chinese and CRLF while accepting a BOM", async () => {
    expect(
      await readCodeFile(file("answer.PY", "\ufeff# 中文\r\nprint(1)\r\n")),
    ).toBe("# 中文\r\nprint(1)\r\n");
  });
  it("rejects invalid UTF-8, binary, empty and oversized code", async () => {
    for (const input of [
      file("a.py", new Uint8Array([255])),
      file("a.py", "a\0b"),
      file("a.py", ""),
      file("a.py", " "),
      file("a.py", "x".repeat(200001)),
      file("a.py", "x", 1048577),
    ])
      await expect(readCodeFile(input)).rejects.toThrow();
  });
  it("accepts a single partial JSON object and rejects arrays or malformed JSON", async () => {
    expect(await readProblemFile(file("p.JSON", '{"title":"题目"}'))).toEqual({
      title: "题目",
    });
    for (const input of [
      file("p.py", "{}"),
      file("p.json", "[]"),
      file("p.json", "{}"),
      file("p.json", "{"),
      file("p.json", "null"),
      file("p.json", "{}", 10485761),
    ])
      await expect(readProblemFile(input)).rejects.toThrow();
  });
  it("derives extensions and ambiguous matches from live language metadata", () => {
    const languages = [python, cpp, { name: "c", file_ext: ".c" } as Language];
    expect(languageAccept(languages)).toBe(".c,.cpp,.py");
    expect(fileLanguages("ANSWER.CPP", languages)).toEqual([cpp]);
    expect(fileLanguages("a.zip", languages)).toEqual([]);
    expect(
      fileLanguages("a.py", [...languages, { ...python, name: "python_alt" }]),
    ).toHaveLength(2);
  });
});

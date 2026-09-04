import { beforeEach, expect, test } from "vitest";
import { readBackup, writeBackup, clearBackup } from "./draft-backup";
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});
test("a stale acknowledgement preserves another tab's content", () => {
  writeBackup("draft", "original", 1);
  localStorage.setItem(
    "draft",
    JSON.stringify({ code: "other tab", revision: 1 }),
  );
  clearBackup("draft", "original");
  expect(JSON.parse(localStorage.getItem("draft")!).code).toBe("other tab");
  expect(sessionStorage.getItem("draft")).toBeNull();
});
test("a tab restores its own code before another tab's backup", () => {
  writeBackup("draft", "own code", 3);
  localStorage.setItem(
    "draft",
    JSON.stringify({ code: "another", revision: 4 }),
  );
  expect(readBackup("draft")).toEqual({ code: "own code", revision: 3 });
});
test("legacy backups require an explicit conflict choice", () => {
  localStorage.setItem("draft", "print(1)");
  expect(readBackup("draft")).toEqual({ code: "print(1)", revision: -1 });
});

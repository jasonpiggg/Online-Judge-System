import { beforeEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { editingDraftPath } from "./problem-actions";
import type { Problem } from "./types";
vi.mock("./api", () => ({ api: vi.fn(), json: (method: string) => ({ method }) }));
beforeEach(() => { vi.mocked(api).mockReset(); });
const problem = { id: "p1" } as Problem;
it("restores an open editable draft without allocating another", async () => {
  vi.mocked(api).mockResolvedValue({ status: "ready" });
  expect(await editingDraftPath(problem, { path: "/authoring/drafts/d1?step=题面" })).toBe("/authoring/drafts/d1?step=题面");
  expect(api).toHaveBeenCalledOnce();
});
it.each(["published", "archived"])("does not reuse an open %s draft", async status => {
  vi.mocked(api).mockResolvedValueOnce({ status }).mockResolvedValueOnce({ id: "d2" });
  expect(await editingDraftPath(problem, { path: "/authoring/drafts/d1" })).toBe("/authoring/drafts/d2");
  expect(api).toHaveBeenLastCalledWith("/problems/p1/editing-draft", { method: "POST" });
});
it("does not create a draft when restoring fails due to a network error", async () => {
  vi.mocked(api).mockRejectedValue(new Error("network"));
  await expect(editingDraftPath(problem, { path: "/authoring/drafts/d1" })).rejects.toThrow("network");
  expect(api).toHaveBeenCalledOnce();
});

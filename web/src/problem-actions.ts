import { api, json } from "./api";
import type { Problem } from "./types";

export async function createEditingDraft(problem: Problem) {
  return api<{ id: string }>(`/problems/${problem.id}/editing-draft`, json("POST"));
}

export async function editingDraftPath(problem: Problem, opened?: { path: string }) {
  if (opened) {
    const id = new URL(opened.path, "http://oj.local").pathname.split("/").pop()!;
    try {
      const draft = await api<{ status: string }>(`/problem-drafts/${id}`);
      if (["draft", "ready"].includes(draft.status)) return opened.path;
    } catch (error) {
      if (![403, 404].includes((error as { status?: number }).status || 0)) throw error;
    }
  }
  const draft = await createEditingDraft(problem);
  return `/authoring/drafts/${draft.id}`;
}

import { api, json } from "./api";
import type { Problem } from "./types";

export async function createEditingDraft(problem: Problem) {
  const { limit_inheritance } = problem;
  const editable = { ...problem };
  delete editable.limit_inheritance;
  delete editable.progress;
  return api<{ id: string }>(
    "/problem-drafts/",
    json("POST", {
      base_problem_id: problem.id,
      problem: {
        ...editable,
        time_limit: limit_inheritance?.time_limit ? null : problem.time_limit,
        memory_limit: limit_inheritance?.memory_limit
          ? null
          : problem.memory_limit,
      },
    }),
  );
}

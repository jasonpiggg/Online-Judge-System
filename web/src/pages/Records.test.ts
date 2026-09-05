import { describe, expect, it } from "vitest";
import type { Submission } from "../types";
import { submissionBackPath } from "./Records";

const submission: Submission = {
  submission_id: "42",
  problem_id: "sum_2",
  language: "python",
  status: "success",
  score: 2,
  counts: 2,
  created_at: "2026-09-05T00:00:00Z",
};

describe("submissionBackPath", () => {
  it("accepts only the matching problem path", () => {
    expect(
      submissionBackPath("/problems/sum_2?submission=42&tab=结果", submission, false),
    ).toBe("/problems/sum_2?submission=42&tab=结果");
    expect(submissionBackPath("/problems/other?tab=结果", submission, false)).toBe(
      "/submissions",
    );
    expect(submissionBackPath("https://evil.example", submission, false)).toBe(
      "/submissions",
    );
  });

  it("allows management returns only for administrators", () => {
    expect(submissionBackPath("/admin?tab=提交", submission, true)).toBe(
      "/admin?tab=提交",
    );
    expect(submissionBackPath("/admin?tab=提交", submission, false)).toBe(
      "/submissions",
    );
  });
});

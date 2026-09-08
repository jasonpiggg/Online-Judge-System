import { describe, expect, it } from "vitest";
import { equivalentDraft } from "./draft-state";

describe("Streamlit draft dirty state", () => {
  it("ignores empty defaults added by an untouched form", () => {
    expect(equivalentDraft({problem:{title:"题目"}}, {problem:{title:"题目",hint:"",samples:[],time_limit:null}})).toBe(true);
  });
  it("preserves whitespace, zero, false and array entries", () => {
    for (const value of [" ", 0, false, [{input:"",output:""}]]) {
      expect(equivalentDraft({}, {value})).toBe(false);
    }
    expect(equivalentDraft({input:"x\n"}, {input:"x"})).toBe(false);
    expect(equivalentDraft({value:false}, {value:0})).toBe(false);
  });
  it("ignores object ordering but preserves array order", () => {
    expect(equivalentDraft({a:1,b:2}, {b:2,a:1})).toBe(true);
    expect(equivalentDraft({cases:[1,2]}, {cases:[2,1]})).toBe(false);
  });
});

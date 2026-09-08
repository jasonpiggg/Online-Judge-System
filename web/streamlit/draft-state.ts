// Match frontend.authoring.equivalent_draft: form-only empty defaults are not edits.
function normalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalize);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .filter(([, item]) => item !== null && item !== undefined && item !== ""
        && !(Array.isArray(item) && item.length === 0)
        && !(item !== null && typeof item === "object" && !Array.isArray(item) && Object.keys(item).length === 0))
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, normalize(item)]));
  }
  return value;
}

export function equivalentDraft(left: unknown, right: unknown): boolean {
  return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right));
}

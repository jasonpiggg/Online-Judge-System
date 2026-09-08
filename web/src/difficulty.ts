import levels from "../../src/oj/difficulties.json";

export const difficulties = levels;
export function difficultyLevel(value?: string) {
  const key = (value || "").trim().toLowerCase();
  return (
    levels.find(
      (level) => level.value === key || level.aliases.includes(key),
    ) || { ...levels[0], value: value || "", label: value || levels[0].label }
  );
}

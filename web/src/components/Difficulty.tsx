import { difficulties, difficultyLevel } from "../difficulty";

export function DifficultyBadge({ value }: { value?: string }) {
  const level = difficultyLevel(value);
  return (
    <span
      className={`badge difficulty difficulty-${level.tone}`}
      title={level.description}
    >
      {level.label}
    </span>
  );
}

export function DifficultyGuide({ compact = false }: { compact?: boolean }) {
  return (
    <details className={`difficulty-guide${compact ? " compact-guide" : ""}`}>
      <summary>难度分级标准</summary>
      <dl>
        {difficulties
          .filter((level) => level.value)
          .map((level) => (
            <div key={level.value}>
              <dt>
                <DifficultyBadge value={level.value} />
              </dt>
              <dd>{level.description}</dd>
            </div>
          ))}
      </dl>
      <p className="muted">
        按解题思维与算法要求分级，不以测试点数或分数判断。自定义等级保留原文并使用中性色。
      </p>
    </details>
  );
}

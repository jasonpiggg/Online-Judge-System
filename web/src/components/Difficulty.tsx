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

export function DifficultyGuide() {
  return (
    <details className="difficulty-guide">
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
        按解题思维与算法要求分级，不以测试点数或分数判断。未知等级显示「未分级」。
      </p>
    </details>
  );
}

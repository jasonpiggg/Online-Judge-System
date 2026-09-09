import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, errorText } from "../api";
import { DiffView } from "./DiffView";
import { DisclosureCard } from "./DisclosureCard";
import { Button } from "./ui/button";

export type PublishedAssetData = {
  reference_solution: string;
  brute_solution: string;
  generator_code: string;
  review: {
    review?: string;
    coverage?: Record<string, string>;
    wrong_solutions?: { code: string; reason: string }[];
  };
};
type Source = {
  assets: PublishedAssetData;
  source_draft_id: string;
  source_revision: number;
};
type AssetResponse = Partial<Source> & { status: string; sources: Source[] };

export function PublishedAssets({
  problemId,
  before,
  onRestore,
}: {
  problemId: string;
  before?: PublishedAssetData;
  onRestore?: (assets: PublishedAssetData) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const query = useQuery({
    queryKey: ["published-assets", problemId],
    queryFn: () => api<AssetResponse>(`/problems/${problemId}/assets`),
    enabled: open,
  });
  const data = query.data;
  const assets =
    data?.status === "ambiguous"
      ? data.sources.find((s) => s.source_draft_id === source)?.assets
      : data?.assets;
  return (
    <DisclosureCard
      summary={onRestore ? "恢复已发布资产" : "参考解与验证资产"}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      {open && (
        <div className="stack">
          {query.isLoading && <p>正在加载资产…</p>}
          {(query.error || error) && (
            <p role="alert">{error || errorText(query.error)}</p>
          )}
          {data?.status === "missing" && (
            <p>没有找到匹配的已发布资产，不会自动调用 AI 生成。</p>
          )}
          {data?.status === "stale" && (
            <p role="status">
              题目发布后已修改，以下资产来自旧版本，须重新审阅和验证。
            </p>
          )}
          {data?.status === "ambiguous" && (
            <label>
              多个历史版本的资产不同，请选择来源
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="">请选择资产来源</option>
                {data.sources.map((s) => (
                  <option key={s.source_draft_id} value={s.source_draft_id}>
                    {s.source_draft_id} · v{s.source_revision}
                  </option>
                ))}
              </select>
            </label>
          )}
          {assets && (
            <>
              <p className="muted">
                已发布命题资产向所有登录用户开放。参考解供学习使用，有限测试不代表正确性证明。
              </p>
              {onRestore && before ? (
                <>
                  <DiffView before={before} after={assets} />
                  <p>采纳会替换上述资产并保存当前草稿，需要重新验证。</p>
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError("");
                      try {
                        await onRestore(assets);
                      } catch (e) {
                        setError(errorText(e));
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    采纳并保存资产
                  </Button>
                </>
              ) : (
                <>
                  {(
                    [
                      "reference_solution",
                      "brute_solution",
                      "generator_code",
                    ] as const
                  ).map((key, i) => (
                    <div key={key}>
                      <h3>{["参考解", "独立解法", "数据生成器"][i]}</h3>
                      <div className="code-block">
                        <pre>
                          <code>{assets[key] || "未提供"}</code>
                        </pre>
                      </div>
                    </div>
                  ))}
                  <p>{assets.review.review}</p>
                  {Object.entries(assets.review.coverage || {}).map(
                    ([key, value]) => (
                      <p key={key}>
                        {{
                          basic: "基础覆盖",
                          boundary: "边界覆盖",
                          scale: "规模覆盖",
                        }[key] || key}
                        ：{value}
                      </p>
                    ),
                  )}
                  {assets.review.wrong_solutions?.map((wrong, i) => (
                    <div key={i}>
                      <h3>错误解 {i + 1}</h3>
                      <p>{wrong.reason}</p>
                      <div className="code-block">
                        <pre>
                          <code>{wrong.code}</code>
                        </pre>
                      </div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>
      )}
    </DisclosureCard>
  );
}

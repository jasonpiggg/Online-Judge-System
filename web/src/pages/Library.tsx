import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  Link,
  useSearchParams,
  useNavigationType,
  useLocation,
} from "react-router-dom";
import { api } from "../api";
import type { Problem } from "../types";
import { Button } from "../components/ui/button";
import { SearchInput } from "../components/SearchInput";
import { Icon } from "../components/Icon";
import { difficulties, difficultyLevel } from "../difficulty";
import { DifficultyBadge, DifficultyGuide } from "../components/Difficulty";
import { Pagination } from "../components/Pagination";
export function Library() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigation = useNavigationType();
  const scrollKey = "oj-library-scroll:" + params.toString();
  const { data: problems, error } = useQuery({
    queryKey: ["problems"],
    queryFn: () =>
      api<Problem[]>("/problems/?include_metadata=true&include_progress=true"),
  });
  const q = params.get("q") || "",
    difficulty = params.get("difficulty")
      ? difficultyLevel(params.get("difficulty") || "").label
      : "",
    status = params.get("status") || "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const update = (key: string, value: string) => {
    const p = new URLSearchParams(params);
    if (value) p.set(key, value);
    else p.delete(key);
    p.delete("page");
    setParams(p, { replace: key === "q" });
  };
  const label = (p: Problem) =>
    p.progress?.passed ? "已通过" : p.progress?.attempts ? "尝试中" : "未开始";
  const filtered = problems?.filter(
    (p) =>
      (p.id + p.title + (p.tags || []).join(" "))
        .toLowerCase()
        .includes(q.toLowerCase()) &&
      (!difficulty || difficultyLevel(p.difficulty).label === difficulty) &&
      (!status || label(p) === status),
  );
  useEffect(() => {
    if (!problems) return;
    const saved = sessionStorage.getItem(scrollKey);
    if (
      saved &&
      (navigation === "POP" ||
        sessionStorage.getItem("oj-return-library") === "1")
    ) {
      requestAnimationFrame(() => window.scrollTo(0, Number(saved)));
      sessionStorage.removeItem("oj-return-library");
    }
    const remember = () =>
      sessionStorage.setItem(scrollKey, String(window.scrollY));
    window.addEventListener("scroll", remember, { passive: true });
    return () => window.removeEventListener("scroll", remember);
  }, [problems, scrollKey, navigation]);
  return (
    <div className="page">
      <div className="page-heading">
        <h1>
          <Icon name="book" />
          题库
        </h1>
        <span className="muted">从一道题开始。</span>
      </div>
      <div className="filters filter-panel">
        <SearchInput
          label="搜索题目"
          navigationKey={location.key}
          placeholder="搜索题号、标题或标签"
          value={q}
          onCommit={(value) => update("q", value)}
        />
        <select
          aria-label="难度"
          value={difficulty}
          onChange={(e) => update("difficulty", e.target.value)}
        >
          <option value="">全部难度</option>
          {[...difficulties.slice(1), difficulties[0]].map((level) => (
            <option key={level.label} value={level.label}>
              {level.label}
            </option>
          ))}
        </select>
        <select
          aria-label="学习状态"
          value={status}
          onChange={(e) => update("status", e.target.value)}
        >
          <option value="">全部状态</option>
          {["未开始", "尝试中", "已通过"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </div>
      <DifficultyGuide />
      {error && <p role="alert">{error.message}</p>}
      {!problems && !error ? (
        <div className="skeleton">正在加载题目…</div>
      ) : (
        <>
          <p className="list-summary">
            共 <strong>{filtered?.length}</strong> 道题目
          </p>
          <div className="problem-list">
            <div className="list-head">
              <span className="library-id">题号</span>
              <span>题目</span>
              <span>难度</span>
              <span>状态</span>
            </div>
            {filtered?.slice((page - 1) * 20, page * 20).map((p) => (
              <Link
                className="problem-row"
                key={p.id}
                to={`/problems/${p.id}`}
                onClick={() =>
                  sessionStorage.setItem(scrollKey, String(window.scrollY))
                }
                state={{
                  listSearch: params.toString(),
                  ids: filtered.map((p) => p.id),
                  scrollY: window.scrollY,
                }}
              >
                <span className="problem-id library-id">{p.id}</span>
                <div className="problem-title">
                  <strong>{p.title}</strong>
                  <div className="tags">
                    {p.tags?.slice(0, 3).map((t) => (
                      <span key={t}>{t}</span>
                    ))}
                  </div>
                </div>
                <DifficultyBadge value={p.difficulty} />
                <span
                  className={
                    p.progress?.passed
                      ? "badge problem-progress tone-AC"
                      : "badge problem-progress tone-pending"
                  }
                >
                  {label(p)}
                </span>
              </Link>
            ))}
          </div>
          {!filtered?.length && (
            <div className="empty">
              没有匹配的题目，试试其他关键词。
              <Button onClick={() => setParams({})}>清除筛选</Button>
            </div>
          )}
          <Pagination
            page={page}
            totalPages={Math.ceil((filtered?.length || 0) / 20)}
            label="题库分页"
            onChange={(next) =>
              setParams({
                ...Object.fromEntries(params),
                page: String(next),
              })
            }
          />
        </>
      )}
    </div>
  );
}

import { useEffect } from "react";
import { Button } from "./ui/button";

export function paginationWindow(page: number, totalPages: number) {
  const total = Math.max(1, Math.floor(totalPages) || 1);
  const current = Math.min(total, Math.max(1, Math.floor(page) || 1));
  const count = Math.min(5, total);
  const start = Math.min(Math.max(1, current - 2), total - count + 1);
  return Array.from({ length: count }, (_, index) => start + index);
}

export function Pagination({
  page,
  totalPages,
  onChange,
  label = "分页",
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  label?: string;
}) {
  const total = Math.max(1, Math.floor(totalPages) || 1);
  const current = Math.min(total, Math.max(1, Math.floor(page) || 1));
  useEffect(() => {
    if (page !== current) onChange(current);
  }, [current, onChange, page]);
  const go = (next: number) => {
    const value = Math.min(total, Math.max(1, next));
    if (value !== current) onChange(value);
  };
  return (
    <nav className="pagination" aria-label={label}>
      <Button disabled={current === 1} onClick={() => go(1)}>
        首页
      </Button>
      <Button
        className="page-arrow"
        aria-label="上一页"
        title="上一页"
        disabled={current === 1}
        onClick={() => go(current - 1)}
      >
        ‹
      </Button>
      <div className="page-numbers">
        {paginationWindow(current, total).map((number) => (
          <Button
            key={number}
            className="page-number"
            variant={number === current ? "default" : "ghost"}
            aria-current={number === current ? "page" : undefined}
            aria-label={`第 ${number} 页`}
            onClick={() => go(number)}
          >
            {number}
          </Button>
        ))}
      </div>
      <Button
        className="page-arrow"
        aria-label="下一页"
        title="下一页"
        disabled={current === total}
        onClick={() => go(current + 1)}
      >
        ›
      </Button>
      <Button disabled={current === total} onClick={() => go(total)}>
        尾页
      </Button>
    </nav>
  );
}

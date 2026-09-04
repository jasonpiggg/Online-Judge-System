import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Pagination, paginationWindow } from "./Pagination";

afterEach(cleanup);

describe("Pagination", () => {
  it("keeps a five-page window near both boundaries", () => {
    expect(paginationWindow(1, 20)).toEqual([1, 2, 3, 4, 5]);
    expect(paginationWindow(10, 20)).toEqual([8, 9, 10, 11, 12]);
    expect(paginationWindow(20, 20)).toEqual([16, 17, 18, 19, 20]);
  });

  it("renders the one-page boundary without duplicate page numbers", () => {
    render(<Pagination page={1} totalPages={1} onChange={vi.fn()} />);
    expect(screen.getAllByRole("button")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "第 1 页" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    for (const name of ["首页", "上一页", "下一页", "尾页"])
      expect(screen.getByRole("button", { name })).toBeDisabled();
  });

  it("navigates by number, arrows, first and last page", () => {
    const onChange = vi.fn();
    render(<Pagination page={10} totalPages={20} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "第 12 页" }));
    fireEvent.click(screen.getByRole("button", { name: "上一页" }));
    fireEvent.click(screen.getByRole("button", { name: "首页" }));
    fireEvent.click(screen.getByRole("button", { name: "尾页" }));
    expect(onChange.mock.calls.map(([page]) => page)).toEqual([12, 9, 1, 20]);
  });

  it("moves back to the last valid page after an archive shrinks the list", () => {
    const onChange = vi.fn();
    render(<Pagination page={2} totalPages={1} onChange={onChange} />);
    expect(onChange).toHaveBeenCalledWith(1);
  });
});

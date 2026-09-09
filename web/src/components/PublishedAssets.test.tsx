import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { PublishedAssets } from "./PublishedAssets";
import { api } from "../api";

vi.mock("../api", () => ({
  api: vi.fn(),
  errorText: (e: unknown) => String(e),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const assets = {
  reference_solution: "print(42)",
  brute_solution: "",
  generator_code: "",
  review: {},
};
function mount(onRestore?: (value: typeof assets) => Promise<void>) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PublishedAssets problemId="p" before={assets} onRestore={onRestore} />
    </QueryClientProvider>,
  );
  const details = screen
    .getByText(onRestore ? "恢复已发布资产" : "参考解与验证资产")
    .closest("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
}
it("requires an explicit ambiguous source selection and surfaces restore conflicts", async () => {
  vi.mocked(api).mockResolvedValue({
    status: "ambiguous",
    sources: [{ source_draft_id: "old", source_revision: 2, assets }],
  });
  const restore = vi.fn().mockRejectedValue(new Error("revision conflict"));
  mount(restore);
  fireEvent.change(await screen.findByRole("combobox"), {
    target: { value: "old" },
  });
  const button = await screen.findByRole("button", { name: "采纳并保存资产" });
  expect(button).toHaveAttribute("type", "button");
  fireEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "revision conflict",
  );
  expect(restore).toHaveBeenCalledExactlyOnceWith(assets);
});
it("shows published reference code with a stale-version warning", async () => {
  vi.mocked(api).mockResolvedValue({ status: "stale", assets, sources: [] });
  mount();
  expect(await screen.findByText("print(42)")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("旧版本");
});

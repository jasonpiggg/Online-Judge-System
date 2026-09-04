import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, it, expect } from "vitest";
import { RichText, Code } from "./Markdown";
afterEach(cleanup);
describe("shared Markdown", () => {
  it("renders tables, math and code while rejecting HTML and unsafe links", () => {
    const { container } = render(
      <RichText
        text={
          "| A | B |\n|---|---|\n| 1 | 2 |\n\n$x^2$\n\n```python\nprint(1)\n```\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert)"
        }
      />,
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelector(".katex")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByRole("button", { name: "复制" })).toBeInTheDocument();
    expect(container.querySelector("a")?.getAttribute("href")).not.toMatch(
      /^javascript:/,
    );
  });
  it("preserves literal code whitespace", () => {
    const { container } = render(<Code text={"  a\n\n b\n"} />);
    expect(container.querySelector("code")?.textContent).toBe("  a\n\n b\n");
  });
});

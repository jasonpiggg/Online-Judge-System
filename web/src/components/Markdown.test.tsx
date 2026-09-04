import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, it, expect } from "vitest";
import { RichText, Code } from "./Markdown";
import { Statement } from "./Statement";
import type { Problem } from "../types";
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
  it("keeps incomplete model fields from crashing the preview", () => {
    const { container, rerender } = render(
      <Statement
        problem={
          {
            description: { invalid: true },
            input_description: [],
            samples: [null, { input: 1 }, { input: "1 2", output: "3" }],
          } as unknown as Problem
        }
      />,
    );
    expect(container.querySelectorAll("code")).toHaveLength(2);
    expect(container).toHaveTextContent("1 2");
    rerender(
      <Statement
        problem={{ samples: { invalid: true } } as unknown as Problem}
      />,
    );
    expect(container.querySelectorAll("code")).toHaveLength(0);
    rerender(<Code text={{ unexpected: "model structure" }} />);
    expect(container).toHaveTextContent("model structure");
  });
});

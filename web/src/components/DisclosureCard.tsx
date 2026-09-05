import type { ComponentProps, ReactNode } from "react";
import { clsx } from "clsx";

type DisclosureCardProps = Omit<ComponentProps<"details">, "children"> & {
  summary: ReactNode;
  children: ReactNode;
};

/** Shared spacing and disclosure semantics for expandable content cards. */
export function DisclosureCard({
  summary,
  children,
  className,
  ...props
}: DisclosureCardProps) {
  return (
    <details className={clsx("disclosure-card", className)} {...props}>
      <summary>{summary}</summary>
      <div className="disclosure-content">{children}</div>
    </details>
  );
}

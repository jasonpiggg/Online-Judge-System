import { Link, type LinkProps } from "react-router-dom";
import { Icon } from "./Icon";

export function BackLink({ children, ...props }: LinkProps) {
  return (
    <Link className="back-link" {...props}>
      <Icon name="chevronLeft" />
      <span>{children}</span>
    </Link>
  );
}

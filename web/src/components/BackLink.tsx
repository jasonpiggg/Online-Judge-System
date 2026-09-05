import { useEffect } from "react";
import { Link, useNavigate, type LinkProps } from "react-router-dom";
import { Icon } from "./Icon";

const USER_KEY = "oj-navigation-user";
const START_KEY = "oj-navigation-start-index";

export function useNavigationBoundary(userId?: string) {
  useEffect(() => {
    if (!userId) {
      sessionStorage.removeItem(USER_KEY);
      sessionStorage.removeItem(START_KEY);
      return;
    }
    if (sessionStorage.getItem(USER_KEY) !== userId) {
      sessionStorage.setItem(USER_KEY, userId);
      sessionStorage.setItem(START_KEY, String(window.history.state?.idx ?? 0));
    }
  }, [userId]);
}

export function BackLink({ children, ...props }: LinkProps) {
  const navigate = useNavigate();
  return (
    <Link
      className="back-link"
      {...props}
      onClick={(event) => {
        props.onClick?.(event);
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
          return;
        const current = Number(window.history.state?.idx ?? 0);
        const start = Number(sessionStorage.getItem(START_KEY) ?? current);
        if (sessionStorage.getItem(USER_KEY) && current > start) {
          event.preventDefault();
          navigate(-1);
        }
      }}
    >
      <Icon name="chevronLeft" />
      <span>{children}</span>
    </Link>
  );
}

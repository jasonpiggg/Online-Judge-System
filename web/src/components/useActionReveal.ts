import { useCallback, useRef } from "react";

function revealElement(element: HTMLElement) {
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  element.scrollIntoView?.({ behavior: reduced ? "auto" : "smooth", block: "start" });
  if (!element.hasAttribute("tabindex")) element.tabIndex = -1;
  window.setTimeout(() => element.focus({ preventScroll: true }), reduced ? 0 : 180);
}

/** Queues exactly one reveal for a user action, including asynchronously rendered targets. */
export function useActionReveal<T extends HTMLElement>() {
  const target = useRef<T | null>(null);
  const pending = useRef(false);
  const reveal = useCallback(() => {
    pending.current = true;
    if (target.current) {
      pending.current = false;
      revealElement(target.current);
    }
  }, []);
  const ref = useCallback((node: T | null) => {
    target.current = node;
    if (node && pending.current) {
      pending.current = false;
      requestAnimationFrame(() => revealElement(node));
    }
  }, []);
  return { ref, reveal };
}

import { Icon } from "./Icon";
import { useActivity } from "./Activity";

export function useNavigationBoundary(_userId?: string) {
  // Compatibility no-op: per-task TaskSlot history owns navigation boundaries.
}

export function BackLink() {
  const { activeSlot, back } = useActivity();
  const previous = activeSlot?.backStack.at(-1);
  if (!previous) return null;
  return (
    <button type="button" className="back-link" onClick={back}>
      <Icon name="chevronLeft" />
      <span>返回 {previous.title}</span>
    </button>
  );
}

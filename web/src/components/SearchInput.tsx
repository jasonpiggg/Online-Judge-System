import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

/** Keep IME composition synchronous and independent of router navigation. */
export function SearchInput({
  value,
  onCommit,
  label,
  placeholder,
  navigationKey,
}: {
  value: string;
  onCommit: (value: string) => void;
  label: string;
  placeholder: string;
  navigationKey: string;
}) {
  const [text, setText] = useState(value);
  const composing = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const commit = useRef(onCommit);
  commit.current = onCommit;
  const cancel = () => clearTimeout(timer.current);
  useEffect(() => {
    cancel();
    setText(value);
    composing.current = false;
    return cancel;
  }, [value, navigationKey]);
  const publish = (next: string, delay = 0) => {
    cancel();
    if (delay) timer.current = setTimeout(() => commit.current(next), delay);
    else commit.current(next);
  };
  return (
    <div className="search-field">
      <Icon name="search" />
      <input
        aria-label={label}
        placeholder={placeholder}
        value={text}
        onBlur={(e) => {
          if (!composing.current) publish(e.currentTarget.value);
        }}
        onCompositionStart={() => {
          composing.current = true;
          cancel();
        }}
        onCompositionEnd={(e) => {
          composing.current = false;
          setText(e.currentTarget.value);
          publish(e.currentTarget.value);
        }}
        onChange={(e) => {
          setText(e.target.value);
          if (!composing.current) publish(e.target.value, 250);
        }}
        onKeyDown={(e) => {
          if (
            e.key === "Enter" &&
            !composing.current &&
            !e.nativeEvent.isComposing &&
            e.keyCode !== 229
          ) {
            e.preventDefault();
            publish(e.currentTarget.value);
          }
        }}
      />
      {text && (
        <button
          type="button"
          aria-label="清空搜索"
          onClick={() => {
            composing.current = false;
            setText("");
            publish("");
          }}
        >
          <Icon name="cross" />
        </button>
      )}
    </div>
  );
}

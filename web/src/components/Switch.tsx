export function Switch({
  checked,
  disabled,
  label,
  ariaLabel,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  ariaLabel?: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="switch-control">
      <input
        type="checkbox"
        role="switch"
        aria-label={ariaLabel}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch-track" aria-hidden="true"><span /></span>
      <span className="switch-label">{label}</span>
    </label>
  );
}

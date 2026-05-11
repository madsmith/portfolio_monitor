export function ToggleSlider({
  enabled,
  onChange,
  disabled,
}: {
  enabled: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={() => onChange(!enabled)}
      className={[
        "relative inline-flex h-4 w-7 shrink-0 cursor-pointer rounded-full border border-transparent transition-colors duration-150 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed",
        enabled ? "bg-[#3a7040]" : "bg-[#2a2f45]",
      ].join(" ")}
    >
      <span
        className={[
          "inline-block h-3 w-3 rounded-full bg-white shadow transition-transform duration-150 mt-[0.5px]",
          enabled ? "translate-x-3" : "translate-x-0.5",
        ].join(" ")}
      />
    </button>
  );
}

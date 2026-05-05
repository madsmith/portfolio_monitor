export function Input({
  value,
  onChange,
  placeholder,
  type = "text",
  className,
  disabled,
  onKeyDown,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "password" | "number";
  className?: string;
  disabled?: boolean;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      onKeyDown={onKeyDown}
      className={`bg-[#0f1117] border border-[#404868] rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-400 disabled:opacity-50 ${className ?? ""}`}
    />
  );
}

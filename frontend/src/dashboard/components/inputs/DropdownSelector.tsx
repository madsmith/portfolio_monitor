export function DropdownSelector({
  value,
  onChange,
  options,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}) {
  return (
    <div className={`relative ${className ?? ""}`}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-[#0f1117] border border-[#404868] rounded px-2 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-400 appearance-none cursor-pointer pr-6"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <svg className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-slate-400" width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

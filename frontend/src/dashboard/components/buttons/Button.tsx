export type ButtonVariant = "ghost" | "default" | "primary" | "danger" | "dangerGhost";
export type ButtonSize = "sm" | "md";

const BASE = "rounded font-medium transition-colors cursor-pointer disabled:opacity-50";

const SIZE: Record<ButtonSize, string> = {
  sm: "px-3 py-1 text-xs",
  md: "px-3 py-1.5 text-sm",
};

const VARIANT: Record<ButtonVariant, string> = {
  ghost:       "border border-[#2a2d3a] bg-transparent text-slate-400 hover:border-[#404868] hover:text-slate-300",
  default:     "border border-[#404868] bg-[#2a2f45] text-slate-300 hover:bg-[#363d58]",
  primary:     "border border-[#5060a0] bg-[#252a40] text-slate-100 hover:bg-[#2e345a]",
  danger:      "border border-red-900 bg-[#3a1a1a] text-red-400 hover:bg-[#5a2020]",
  dangerGhost: "border border-[#2a2d3a] bg-transparent text-slate-500 hover:border-red-700 hover:text-red-400",
};

export function Button({
  onClick,
  disabled,
  variant = "default",
  size = "sm",
  className = "",
  children,
}: {
  onClick?: () => void;
  disabled?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`${BASE} ${SIZE[size]} ${VARIANT[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

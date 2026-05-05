export function CancelButton({
  onClick,
  disabled,
  children = "Cancel",
}: {
  onClick: () => void;
  disabled?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-1.5 text-sm text-slate-400 bg-[#2a2d3a] hover:bg-[#333748] hover:text-slate-200 rounded transition-colors cursor-pointer disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function ConfirmButton({
  onClick,
  disabled,
  children = "Confirm",
}: {
  onClick: () => void;
  disabled?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-1.5 text-sm bg-[#252a40] border border-[#5060a0] text-slate-100 rounded hover:bg-[#2e345a] transition-colors cursor-pointer disabled:opacity-50"
    >
      {children}
    </button>
  );
}

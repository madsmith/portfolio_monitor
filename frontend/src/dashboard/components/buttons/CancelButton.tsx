import { Button } from "./Button";

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
    <Button variant="default" size="md" onClick={onClick} disabled={disabled}>
      {children}
    </Button>
  );
}

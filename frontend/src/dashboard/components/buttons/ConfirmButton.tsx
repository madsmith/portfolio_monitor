import { Button } from "./Button";

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
    <Button variant="primary" size="md" onClick={onClick} disabled={disabled}>
      {children}
    </Button>
  );
}

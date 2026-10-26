import type { ReactNode } from "react";
import { Spinner } from "@shared/ui/Spinner";

// Кнопка действия в рамке итога.
export const Btn = ({
  primary,
  onClick,
  children,
  disabled,
  busy,
}: {
  primary?: boolean;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  busy?: boolean;
}) => (
  <button
    type="button"
    className={primary ? "btn primary" : "btn"}
    disabled={disabled === true || busy === true}
    onClick={onClick}
  >
    {busy && <Spinner size="sm" />}
    {children}
  </button>
);

import type { ReactNode } from "react";
import { Spinner } from "@shared/ui";
import { useCapabilities } from "../api/sessionQueries";
import type { Capabilities } from "../api/schemas";

export type RequireCapabilityProps = {
  capability: keyof Capabilities;
  // Что показать, если возможности нет. По умолчанию ничего.
  fallback?: ReactNode;
  children: ReactNode;
};

/**
 * Показывает детей только при наличии возможности. Решает bootstrap, а не
 * `mode === "server"`: клиент не гадает о режиме, он читает, что ему разрешено.
 * Пока bootstrap не пришёл, возможность считается отсутствующей, а вместо
 * содержимого стоит спиннер: показать и тут же спрятать хуже.
 */
export const RequireCapability = ({
  capability,
  fallback = null,
  children,
}: RequireCapabilityProps) => {
  const { isLoading, has } = useCapabilities();
  if (isLoading) {
    return (
      <div
        data-testid="require-capability-loading"
        style={{ display: "flex", justifyContent: "center", padding: 24 }}
      >
        <Spinner size="md" />
      </div>
    );
  }
  return has(capability) ? <>{children}</> : <>{fallback}</>;
};

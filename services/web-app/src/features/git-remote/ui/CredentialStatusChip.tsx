import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui/Badge";

export type CredentialStatusChipProps = {
  status: string;
};

const VARIANT: Record<string, "success" | "error" | "warning" | "default"> = {
  ok: "success",
  auth_failed: "error",
  unreadable: "warning",
  unverified: "default",
};

// Итог последней проверки доступа: цвет подкрепляет слова, а не заменяет их.
export const CredentialStatusChip = ({ status }: CredentialStatusChipProps) => {
  const { t } = useTranslation("gitRemote");
  return (
    <Badge variant={VARIANT[status] ?? "default"}>
      {t(`credentialStatus.${status}`, { defaultValue: status })}
    </Badge>
  );
};

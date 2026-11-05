import { useTranslation } from "react-i18next";
import { Banner } from "@features/admin-ops/ui/parts";
import { useDiagnosticsQuiet } from "../api/queries";
import { acceptedCheck } from "../lib/acceptance";
import { RevokeButton } from "./RevokeButton";

/**
 * Вместо баннера-предупреждения: проблема принята осознанно, показываем причину и кнопку возврата.
 * Ничего не рисует, пока принятия нет.
 */
export const AcceptedBanner = ({
  check,
  testId,
}: {
  check: string;
  testId?: string;
}) => {
  const { t } = useTranslation("adminDiagnostics");
  const found = acceptedCheck(useDiagnosticsQuiet().data, check);
  if (!found?.accepted) return null;
  return (
    <Banner
      tone="info"
      title={t("accepted.banner", {
        check: t(`check.${check}`, { defaultValue: check }),
      })}
      testId={testId ?? `diag-accepted-banner-${check}`}
      action={<RevokeButton check={check} />}
    >
      {t("accepted.bannerReason", { reason: found.accepted.reason })}
    </Banner>
  );
};

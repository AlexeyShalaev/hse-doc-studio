import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  ErrorState,
  Input,
  PageHeader,
  Section,
  TableSkeleton,
  type InputProps,
} from "@shared/ui";

/** Заголовок раздела админки. */
export const PageHead = ({
  title,
  lead,
  actions,
}: {
  title: string;
  lead: string;
  actions?: ReactNode;
}) => <PageHeader title={title} description={lead} actions={actions} />;

/** Страница настроек: на время загрузки скелеты разделов, при отказе ошибка с повтором. */
export const LoadState = ({
  failed,
  onRetry,
  sections = 2,
}: {
  failed: boolean;
  onRetry: () => void;
  sections?: number;
}) => {
  const { t } = useTranslation("adminInstall");
  if (failed) {
    return (
      <ErrorState
        framed
        title={t("loadFailed")}
        description={t("loadFailedBody")}
        onRetry={onRetry}
        testId="install-load-failed"
      />
    );
  }
  return (
    <div
      className="flex flex-col"
      style={{ gap: 16 }}
      data-testid="install-loading"
    >
      {Array.from({ length: sections }, (_, i) => (
        <Section
          key={i}
          title={<span className="adm-skel" style={{ width: 140 }} />}
        >
          <TableSkeleton rows={2} columns={2} framed={false} />
        </Section>
      ))}
    </div>
  );
};

/** Числовое поле с единицей справа: «5 мин». */
export const UnitInput = ({
  unit,
  ...props
}: InputProps & { unit: string }) => (
  <span className="adm-unit">
    <Input inputMode="numeric" autoComplete="off" {...props} />
    <span aria-hidden="true" className="adm-unit-label">
      {unit}
    </span>
  </span>
);

/** Низ раздела, где всё задано окружением. */
export const AllLockedNote = () => {
  const { t } = useTranslation("adminInstall");
  return (
    <span className="adm-field-note" data-testid="all-locked-note">
      <Lock size={12} aria-hidden="true" />
      {t("locked.note")}
    </span>
  );
};

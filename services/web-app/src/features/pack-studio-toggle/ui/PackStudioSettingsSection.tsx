import { ArrowRight } from "lucide-react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  PACK_STUDIO_PATH,
  packErrorText,
  usePackStudioSection,
  useSetPackStudioSection,
} from "@entities/pack-studio";
import { Button, ErrorState, Section, SettingRow, Spinner } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";

/**
 * Настройки локальной Студии, «Студия шаблонов» (template-studio.md, D4):
 * переключатель «Инструменты автора шаблонов». Включение задано окружением или
 * профилем standalone: переключатель только для чтения. На сервере раздел
 * включает администратор, этого блока там нет.
 */
export const PackStudioSettingsSection = () => {
  const { t } = useTranslation("settings");
  const navigate = useNavigate();
  const section = usePackStudioSection();
  const toggle = useSetPackStudioSection();

  if (section.isPending) return <Spinner />;
  if (section.isError) {
    return (
      <ErrorState
        description={packErrorText(section.error)}
        onRetry={() => void section.refetch()}
      />
    );
  }
  const data = section.data;
  return (
    <div
      id="pack-studio"
      className="settings-anchor flex flex-col"
      style={{ gap: "1rem" }}
      data-testid="pack-studio-settings"
    >
      <div className="flex flex-col" style={{ gap: "0.25rem" }}>
        <h4 style={{ margin: 0, fontSize: "0.875rem", fontWeight: 600 }}>
          {t("packStudio.title")}
        </h4>
        <p style={{ margin: 0, color: "var(--fg-2)", fontSize: "0.75rem" }}>
          {t("packStudio.lead")}
        </p>
      </div>
      <Section>
        <SettingRow
          label={t("packStudio.toggle")}
          hint={
            data.locked ? t("packStudio.locked") : t("packStudio.toggleHint")
          }
          locked={data.locked}
        >
          <Switch
            checked={data.enabled}
            disabled={data.locked || toggle.isPending}
            onChange={(next) => {
              toggle.mutate(next);
            }}
            label={t("packStudio.toggle")}
            testId="pack-studio-toggle"
          />
        </SettingRow>
        {toggle.isError && (
          <Notice tone="err" role="alert" text={packErrorText(toggle.error)} />
        )}
      </Section>
      {data.allowed && (
        <div>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              void navigate(PACK_STUDIO_PATH);
            }}
            data-testid="pack-studio-open"
          >
            {t("packStudio.open")}
            <ArrowRight size="0.75rem" />
          </Button>
        </div>
      )}
    </div>
  );
};

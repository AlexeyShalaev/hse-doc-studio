import { useTranslation } from "react-i18next";
import { packErrorText, usePackOfficialAdmin } from "@entities/pack-studio";
import { Badge, ErrorState, Section, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import "./packStudioAdmin.css";

/**
 * «Официальные шаблоны» (template-studio.md, 4.7): репозиторий паков установки
 * из окружения, только для чтения. Вклад в него идёт PR от людей своим
 * аккаунтом GitHub, настроек у вклада нет.
 */
export const OfficialSection = () => {
  const { t } = useTranslation("adminPackStudio");
  const state = usePackOfficialAdmin();

  if (state.isPending) {
    return (
      <Section title={t("official.title")}>
        <Spinner />
      </Section>
    );
  }
  if (state.isError) {
    return (
      <Section title={t("official.title")}>
        <ErrorState
          compact
          description={packErrorText(state.error)}
          onRetry={() => void state.refetch()}
        />
      </Section>
    );
  }
  const repo = state.data.repo;

  return (
    <Section title={t("official.title")} description={t("official.lead")}>
      <div data-testid="ps-official">
        {repo ? (
          <div className="sp-repo-meta">
            <span className="mono">{repo.web_url}</span>
            <Badge variant="subtle">
              {t("official.path", { path: repo.packs_path })}
            </Badge>
            <Badge variant="subtle">
              {t("official.branch", { branch: repo.base_branch })}
            </Badge>
            {repo.license && (
              <Badge variant="subtle">
                {t("official.license", { license: repo.license })}
              </Badge>
            )}
          </div>
        ) : (
          <Notice tone="info" role="status" text={t("official.hidden")} />
        )}
      </div>
    </Section>
  );
};

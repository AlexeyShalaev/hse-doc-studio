import { useTranslation } from "react-i18next";
import { packErrorText, usePackOfficialAdmin } from "@entities/pack-studio";
import { ErrorState, Section, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

/**
 * «Официальные паки» (template-studio.md, 4.7): репозиторий паков установки
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
          <p className="mono" style={{ margin: 0, fontSize: "0.75rem" }}>
            {t("official.repo", {
              url: repo.web_url,
              path: repo.packs_path,
              branch: repo.base_branch,
            })}
          </p>
        ) : (
          <Notice tone="info" role="status" text={t("official.hidden")} />
        )}
      </div>
    </Section>
  );
};

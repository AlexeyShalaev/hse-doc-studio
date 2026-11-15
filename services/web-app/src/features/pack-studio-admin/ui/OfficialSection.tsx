import { useState } from "react";
import { BookOpen, GitFork, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackOfficialAdmin,
  useSetPackOfficialAdmin,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import {
  Button,
  ErrorState,
  Input,
  Section,
  SettingRow,
  Spinner,
} from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import { Notice } from "@shared/ui/ConflictKit";
import { AddServiceAccessDialog } from "./ServiceAccessSection";

/** Справка «Официальные паки: вклад без аккаунта GitHub» на сайте документации. */
const officialBotHelp = (language: string): string =>
  `https://alexeyshalaev.github.io/hse-doc-studio/${
    language.startsWith("en") ? "en/" : ""
  }deploy/pack-studio-bot/`;

/**
 * «Официальные паки» (template-studio.md, 4.7): репозиторий паков установки из
 * окружения, доступ бота (служебный доступ в режиме форка), выключатель вклада
 * без аккаунта GitHub и лимит предложений на человека в сутки.
 */
export const OfficialSection = () => {
  const { t, i18n } = useTranslation("adminPackStudio");
  const state = usePackOfficialAdmin();
  const save = useSetPackOfficialAdmin();
  const [limit, setLimit] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  if (state.isPending) {
    return (
      <Section title={t("official.title")}>
        <Spinner />
      </Section>
    );
  }
  if (state.isError) {
    if (
      state.error instanceof ApiError &&
      state.error.code === "official_unavailable"
    ) {
      return null;
    }
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
  const data = state.data;
  const bot = data.service_access;
  const shown = limit ?? String(data.daily_limit);
  const parsed = Number.parseInt(shown, 10);
  const limitValid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 1000;

  return (
    <Section
      title={t("official.title")}
      description={t("official.lead")}
      actions={
        <a
          href={officialBotHelp(i18n.language)}
          target="_blank"
          rel="noopener noreferrer"
          className="btn sm"
          style={{ gap: "0.375rem", textDecoration: "none" }}
        >
          <BookOpen size="0.75rem" aria-hidden="true" />
          {t("official.help")}
        </a>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="ps-official"
      >
        {data.repo ? (
          <p className="mono" style={{ margin: 0, fontSize: "0.75rem" }}>
            {t("official.repo", {
              url: data.repo.web_url,
              path: data.repo.packs_path,
              branch: data.repo.base_branch,
            })}
          </p>
        ) : (
          <Notice tone="info" role="status" text={t("official.hidden")} />
        )}
        {bot?.fork_mode ? (
          <p
            style={{ margin: 0, fontSize: "0.75rem" }}
            data-testid="ps-official-bot"
          >
            <GitFork size="0.75rem" aria-hidden="true" />{" "}
            {bot.fork_url
              ? t("official.botReady", { label: bot.label, url: bot.fork_url })
              : t("official.botNoFork", { label: bot.label })}
          </p>
        ) : (
          data.repo && (
            <div data-testid="ps-official-no-bot">
              <Notice
                tone="info"
                role="status"
                text={bot ? t("official.botDirect") : t("official.noBot")}
                action={
                  bot ? undefined : (
                    <Button
                      size="xs"
                      variant="secondary"
                      onClick={() => {
                        setAdding(true);
                      }}
                      data-testid="ps-official-add-bot"
                    >
                      <Plus size="0.75rem" />
                      {t("official.addBot")}
                    </Button>
                  )
                }
              />
            </div>
          )
        )}
        <SettingRow
          label={t("official.enabled")}
          hint={t("official.enabledHint")}
        >
          <Switch
            checked={data.bot_enabled}
            disabled={save.isPending}
            onChange={(next) => {
              save.mutate({ bot_enabled: next, daily_limit: data.daily_limit });
            }}
            label={t("official.enabled")}
            testId="ps-official-enabled"
          />
        </SettingRow>
        <div className="flex items-end" style={{ gap: "0.5rem" }}>
          <Input
            label={t("official.limit")}
            hint={t("official.limitHint", { value: data.default_daily_limit })}
            type="number"
            min={1}
            max={1000}
            value={shown}
            onChange={(e) => {
              setLimit(e.target.value);
            }}
            data-testid="ps-official-limit"
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={
              save.isPending || !limitValid || parsed === data.daily_limit
            }
            onClick={() => {
              save.mutate(
                { bot_enabled: data.bot_enabled, daily_limit: parsed },
                {
                  onSuccess: () => {
                    setLimit(null);
                  },
                },
              );
            }}
            data-testid="ps-official-limit-save"
          >
            {t("official.save")}
          </Button>
        </div>
        {save.isError && (
          <Notice tone="err" role="alert" text={packErrorText(save.error)} />
        )}
      </div>
      <AddServiceAccessDialog
        isOpen={adding}
        onClose={() => {
          setAdding(false);
          void state.refetch();
        }}
        preset={data.repo ? { url: data.repo.url, forkMode: true } : null}
      />
    </Section>
  );
};

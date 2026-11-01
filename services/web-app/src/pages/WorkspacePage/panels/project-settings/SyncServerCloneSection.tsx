import { useId, useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { CopyField } from "@shared/ui/CopyField";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import { useProjectGitRemote } from "@entities/git-server";
import { SectionCard } from "../SectionCard";

export type SyncServerCloneSectionProps = {
  projectId: string;
};

type Tab = "desktop" | "cli";
const TABS: Tab[] = ["desktop", "cli"];

/** Ссылка на создание токена только для git (раздел «Аккаунт → Токены»). */
export const GIT_TOKEN_LINK = "/settings/account?preset=git#account-tokens";

/**
 * «Синхронизация → Клонировать с сервера» (раздел 10.12): адрес проекта для
 * git, право отправки и подсказки для Студии на компьютере и командной строки.
 */
export const SyncServerCloneSection = ({
  projectId,
}: SyncServerCloneSectionProps) => {
  const { t } = useTranslation("gitServer");
  const uid = useId();
  const [tab, setTab] = useState<Tab>("desktop");
  const remote = useProjectGitRemote(projectId);
  const data = remote.data;
  return (
    <SectionCard title={t("clone.title")} fullSpan>
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="project-git-remote"
        data-state={
          remote.isError
            ? "error"
            : !data
              ? "loading"
              : data.enabled && data.clone_url
                ? "ready"
                : "disabled"
        }
      >
        {remote.isLoading && (
          <span className="flex items-center dim" style={{ gap: 8 }}>
            <Spinner size="sm" />
            {t("clone.loading")}
          </span>
        )}
        {remote.isError && (
          <Notice tone="err" role="alert" text={t("clone.loadFailed")} />
        )}
        {data && (!data.enabled || !data.clone_url) && (
          <Notice tone="warn" text={t("clone.disabled")} />
        )}
        {data?.enabled && data.clone_url && (
          <>
            <p className="dim" style={{ margin: 0, fontSize: 13 }}>
              {t("clone.lead")}
            </p>
            <div data-testid="project-git-remote-url">
              <CopyField value={data.clone_url} label={t("clone.url")} />
            </div>
            <div
              className="flex"
              style={{ gap: 16, fontSize: 12.5, flexWrap: "wrap" }}
            >
              <span data-testid="project-git-remote-branch">
                {t("clone.branch", { branch: data.branch ?? "master" })}
              </span>
              <span
                data-testid="project-git-remote-push"
                data-can-push={data.can_push ? "true" : "false"}
                style={{
                  color: data.can_push ? "var(--c-ok)" : "var(--fg-2)",
                }}
              >
                {data.can_push ? t("clone.canPush") : t("clone.readOnly")}
              </span>
            </div>
            <div
              className="seg"
              role="tablist"
              aria-label={t("clone.tabs.label")}
              style={{ alignSelf: "flex-start" }}
            >
              {TABS.map((value) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  id={`${uid}-tab-${value}`}
                  aria-selected={tab === value}
                  aria-controls={`${uid}-panel`}
                  className={tab === value ? "active" : undefined}
                  onClick={() => {
                    setTab(value);
                  }}
                  data-testid={`project-git-remote-tab-${value}`}
                >
                  {t(`clone.tabs.${value}`)}
                </button>
              ))}
            </div>
            <div
              role="tabpanel"
              id={`${uid}-panel`}
              aria-labelledby={`${uid}-tab-${tab}`}
              className="flex flex-col"
              style={{ gap: 10, fontSize: 13 }}
            >
              {tab === "desktop" ? (
                <p style={{ margin: 0, lineHeight: 1.5 }}>
                  {t("clone.desktopSteps")}
                </p>
              ) : (
                <>
                  <CopyField
                    value={`git clone ${data.clone_url}`}
                    label={t("clone.cliCommand")}
                    multiline
                    wrap="spaces"
                  />
                  <span className="dim">{t("clone.cliAuth")}</span>
                  <Link
                    to={GIT_TOKEN_LINK}
                    className="btn xs"
                    style={{ alignSelf: "flex-start", textDecoration: "none" }}
                    data-testid="project-git-remote-token"
                  >
                    {t("clone.createToken")}
                  </Link>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </SectionCard>
  );
};

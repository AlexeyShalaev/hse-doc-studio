import { useId } from "react";
import { Building2, Plus } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { Spinner, StatusDot } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  RUNNER_STATE_DOT,
  type BuildRunnersPolicy,
  type ProjectBuildRunners,
} from "@entities/runner";

export type ProjectBuildsViewProps = {
  status: "loading" | "error" | "ready";
  info?: ProjectBuildRunners | null;
  /** Политика сохраняется: выбор занят. */
  saving?: boolean;
  onChange: (policy: BuildRunnersPolicy) => void;
  onRetry?: () => void;
};

const POLICIES: readonly BuildRunnersPolicy[] = ["shared", "owner"];

/** Раннеры владельца точками состояния: только имя и состояние, без адресов. */
const RunnerChips = ({
  runners,
}: {
  runners: ProjectBuildRunners["owner_runners"];
}) => {
  const { t } = useTranslation("workspace");
  return (
    <ul
      className="flex"
      style={{
        gap: 8,
        flexWrap: "wrap",
        listStyle: "none",
        margin: 0,
        padding: 0,
      }}
    >
      {runners.map((runner) => (
        <li
          key={runner.name}
          className="chip sans"
          style={{ display: "inline-flex", gap: 6, alignItems: "center" }}
        >
          <StatusDot
            status={RUNNER_STATE_DOT[runner.state]}
            hideLabel
            label={t(`projectSettings.builds.state.${runner.state}`)}
          />
          <span style={{ color: "var(--fg-0)" }}>{runner.name}</span>
          <span className="dim">
            {t(`projectSettings.builds.state.${runner.state}`)}
          </span>
        </li>
      ))}
    </ul>
  );
};

/**
 * Настройка проекта «Сборки»: где идут сборки соавторов (решает владелец) и
 * куда идут собственные сборки того, кто смотрит. Соавтор видит только чтение.
 */
export const ProjectBuildsView = ({
  status,
  info = null,
  saving = false,
  onChange,
  onRetry,
}: ProjectBuildsViewProps) => {
  const { t } = useTranslation("workspace");
  const name = useId();

  if (status === "loading" || (status === "ready" && !info)) {
    return (
      <div
        className="flex items-center"
        style={{ gap: 8, fontSize: 12 }}
        data-testid="project-builds-loading"
      >
        <Spinner size="sm" />
        <span className="dim">{t("projectSettings.builds.loading")}</span>
      </div>
    );
  }
  if (status === "error" || !info) {
    return (
      <Notice
        tone="err"
        role="alert"
        text={t("projectSettings.builds.loadFailed")}
        action={
          onRetry && (
            <button type="button" className="btn xs" onClick={onRetry}>
              {t("projectSettings.builds.retry")}
            </button>
          )
        }
      />
    );
  }

  const enabled = info.personal_runners_enabled;

  if (info.project_kind === "org") {
    return (
      <div
        className="flex items-start"
        style={{ gap: 8, fontSize: 12.5, color: "var(--fg-1)" }}
        data-testid="project-builds-org"
      >
        <Building2 size={14} aria-hidden="true" style={{ marginTop: 2 }} />
        <span>{t("projectSettings.builds.org")}</span>
      </div>
    );
  }

  const disabledNote = !enabled && (
    <div data-testid="project-builds-disabled">
      <Notice tone="info" text={t("projectSettings.builds.disabled")} />
    </div>
  );

  if (!info.editable) {
    const first = info.owner_runners[0]?.name;
    return (
      <div
        className="flex flex-col"
        style={{ gap: 10 }}
        data-testid="project-builds-readonly"
        data-policy={info.policy}
      >
        {disabledNote}
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-1)" }}>
          {info.policy === "owner" && enabled
            ? first
              ? t("projectSettings.builds.coauthorOwner", { name: first })
              : t("projectSettings.builds.coauthorOwnerNoName")
            : t("projectSettings.builds.coauthorShared")}
        </p>
        {info.policy === "owner" &&
          enabled &&
          info.owner_runners.length > 0 && (
            <div data-testid="project-builds-owner-runners">
              <RunnerChips runners={info.owner_runners} />
            </div>
          )}
      </div>
    );
  }

  return (
    <div
      className="flex flex-col"
      style={{ gap: 14 }}
      data-testid="project-builds"
    >
      {disabledNote}
      <fieldset
        style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
        disabled={!enabled || saving}
      >
        <legend
          style={{
            padding: 0,
            fontSize: 12.5,
            fontWeight: 500,
            marginBottom: 2,
          }}
        >
          {t("projectSettings.builds.coauthorsLabel")}
        </legend>
        <p className="dim" style={{ margin: "0 0 8px", fontSize: 11.5 }}>
          {t("projectSettings.builds.coauthorsHint")}
        </p>
        <div className="flex flex-col" style={{ gap: 6 }}>
          {POLICIES.map((policy) => {
            const checked = info.policy === policy;
            return (
              <label
                key={policy}
                className="flex items-start"
                data-testid={`project-builds-policy-${policy}`}
                data-checked={checked ? "true" : undefined}
                style={{
                  gap: 10,
                  padding: "10px 12px",
                  borderRadius: "var(--r-2)",
                  border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
                  background: checked
                    ? "var(--accent-soft, var(--bg-2))"
                    : "var(--bg-1)",
                  cursor: enabled && !saving ? "pointer" : "default",
                  opacity: enabled ? 1 : 0.6,
                }}
              >
                <input
                  type="radio"
                  name={name}
                  value={policy}
                  checked={checked}
                  onChange={() => {
                    onChange(policy);
                  }}
                  style={{ marginTop: 3 }}
                />
                <span className="flex flex-col" style={{ gap: 2 }}>
                  <strong style={{ fontSize: 12.5, fontWeight: 500 }}>
                    {t(`projectSettings.builds.policy.${policy}.title`)}
                  </strong>
                  <span className="dim" style={{ fontSize: 11.5 }}>
                    {t(`projectSettings.builds.policy.${policy}.hint`)}
                  </span>
                </span>
                {saving && checked && <Spinner size="sm" />}
              </label>
            );
          })}
        </div>
      </fieldset>
      <p
        style={{
          margin: 0,
          fontSize: 12,
          color: "var(--fg-1)",
          lineHeight: 1.5,
        }}
        data-testid="project-builds-own"
      >
        {t("projectSettings.builds.ownBuilds", { seconds: info.wait_s })}
      </p>
      <div
        className="flex flex-col"
        style={{ gap: 6 }}
        data-testid="project-builds-owner-runners"
      >
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("projectSettings.builds.myRunners")}
        </span>
        {info.owner_runners.length > 0 ? (
          <RunnerChips runners={info.owner_runners} />
        ) : (
          <span className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
            <span className="dim">{t("projectSettings.builds.noRunners")}</span>
            <Link
              to="/settings/runners"
              className="btn xs"
              style={{ gap: 4, textDecoration: "none" }}
              data-testid="project-builds-connect"
            >
              <Plus size={11} aria-hidden="true" />
              {t("projectSettings.builds.connect")}
            </Link>
          </span>
        )}
      </div>
    </div>
  );
};

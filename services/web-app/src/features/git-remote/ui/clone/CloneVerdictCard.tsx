import { CircleCheck, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Probe } from "@entities/git-remote";
import { Notice } from "@shared/ui/ConflictKit";
import type { ParsedRemoteUrl } from "../../lib/parseRemoteUrl";
import type { CloneVerdict } from "../../model/cloneVerdict";
import { ProbeIssueCard, type IssueHandlers } from "../ProbeResultCard";
import { Facts, ResultFrame } from "@shared/ui/ResultFrame";
import { Btn } from "../ResultFrame";

export type CloneVerdictCardProps = {
  verdict: CloneVerdict;
  probe: Probe | null;
  url: ParsedRemoteUrl | null;
  /** Ветка, которую выбрал человек (пусто: главная ветка репозитория). */
  branch: string;
  onPickBranch: (branch: string) => void;
  /** Вернуться к адресу и доступу: прежний результат проверки больше не нужен. */
  onChange: () => void;
  issueHandlers: IssueHandlers;
};

const ACCESS_ICON = {
  full: CircleCheck,
  read_only: TriangleAlert,
  files_only: TriangleAlert,
} as const;

// Итог проверки адреса при клонировании: что за проект лежит в репозитории и как
// он откроется. Отказы разобраны по кодам, как в окне подключения.
export const CloneVerdictCard = ({
  verdict,
  probe,
  url,
  branch,
  onPickBranch,
  onChange,
  issueHandlers,
}: CloneVerdictCardProps) => {
  const { t } = useTranslation("gitRemote");

  if (verdict.kind === "error") {
    return (
      <ProbeIssueCard
        issue={verdict.issue}
        probe={probe}
        fixing={false}
        handlers={issueHandlers}
      />
    );
  }

  if (verdict.kind === "empty") {
    return (
      <ResultFrame
        tone="info"
        role="alert"
        title={t("clone.source.empty.title")}
        testId="clone-verdict-empty"
        actions={
          <Btn primary onClick={onChange}>
            {t("result.chooseAnother")}
          </Btn>
        }
      >
        <p style={{ margin: 0 }}>{t("clone.source.empty.text")}</p>
      </ResultFrame>
    );
  }

  if (verdict.kind === "not_studio") {
    return (
      <ResultFrame
        tone="err"
        role="alert"
        title={t("clone.source.notStudio.title")}
        testId="clone-verdict-not_studio"
        actions={
          <Btn primary onClick={onChange}>
            {t("result.chooseAnother")}
          </Btn>
        }
      >
        <p style={{ margin: 0 }}>{t("clone.source.notStudio.text")}</p>
      </ResultFrame>
    );
  }

  const project = probe?.project ?? null;
  const repoPath = url
    ? [url.host, url.owner, url.repo].filter(Boolean).join("/")
    : "";
  const facts: [string, string][] = [];
  if (repoPath !== "") facts.push([t("clone.source.found.repo"), repoPath]);
  if (project) {
    facts.push([t("clone.source.found.project"), project.name]);
    facts.push([
      t("clone.source.found.template"),
      `${project.pack_id} / ${project.template_id} ${project.template_version}`,
    ]);
    const staffing =
      project.staffing === "solo"
        ? t("clone.source.found.staffing_solo")
        : project.staffing === "team"
          ? t("clone.source.found.staffing_team")
          : project.staffing;
    facts.push([
      t("clone.source.found.staffing"),
      `${staffing} · ${t("clone.source.found.authorsCount", { count: project.authors_count })}`,
    ]);
  }

  const branches = probe?.branches ?? [];
  const shownBranch = branch !== "" ? branch : (probe?.default_branch ?? "");
  const AccessIcon = ACCESS_ICON[verdict.access];
  const full = verdict.access === "full";

  return (
    <ResultFrame
      tone={full ? "ok" : "warn"}
      role="status"
      title={t("clone.source.found.title")}
      testId={`clone-verdict-ready-${verdict.access}`}
      actions={<Btn onClick={onChange}>{t("clone.source.found.change")}</Btn>}
    >
      <Facts items={facts} />

      {branches.length > 1 && (
        <div>
          <div className="dim" style={{ fontSize: 11.5, marginBottom: 5 }}>
            {t("clone.source.found.branchPick")}
          </div>
          <div
            className="flex"
            role="group"
            aria-label={t("clone.source.found.branchPick")}
            style={{
              gap: 6,
              flexWrap: "wrap",
              maxHeight: 96,
              overflowY: "auto",
            }}
          >
            {branches.map((name) => (
              <button
                key={name}
                type="button"
                aria-pressed={name === shownBranch}
                className={name === shownBranch ? "chip accent" : "chip"}
                style={{ cursor: "pointer", height: 24 }}
                onClick={() => {
                  if (name !== shownBranch) onPickBranch(name);
                }}
              >
                {name}
                {name === probe?.default_branch && (
                  <span className="dim" style={{ fontWeight: 400 }}>
                    {" · "}
                    {t("clone.source.found.branchDefault")}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
      {branches.length <= 1 && shownBranch !== "" && (
        <Facts items={[[t("clone.source.found.branch"), shownBranch]]} />
      )}

      <div
        role="group"
        aria-label={t("clone.source.verdict.label")}
        className="flex flex-col"
        style={{ gap: 6 }}
        data-testid="clone-access-verdict"
      >
        <div
          className="flex items-start"
          style={{
            gap: 8,
            fontSize: 12.5,
            color: "var(--fg-0)",
            fontWeight: 500,
          }}
        >
          <AccessIcon
            size={14}
            aria-hidden="true"
            style={{
              flexShrink: 0,
              marginTop: 2,
              color: full ? "var(--c-ok)" : "var(--c-warn)",
            }}
          />
          <span>{t(`clone.source.verdict.${verdict.access}`)}</span>
        </div>
        {verdict.reasons.includes("schema_newer") && (
          <Notice
            tone="warn"
            role="status"
            text={
              verdict.requiredStudio
                ? `${t("clone.source.verdict.schemaNewer")} ${t("result.warn.schemaNewerVersion", { version: verdict.requiredStudio })}`
                : t("clone.source.verdict.schemaNewer")
            }
          />
        )}
        {verdict.reasons.includes("template_missing") && (
          <Notice
            tone="warn"
            role="status"
            text={t("result.warn.templateMissing")}
          />
        )}
      </div>
    </ResultFrame>
  );
};

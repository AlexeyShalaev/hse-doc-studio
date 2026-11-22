import { useId, useMemo, useState } from "react";
import {
  CheckCircle2,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  usePackOutcomeLint,
} from "@entities/pack-studio";
import {
  SEVERITIES,
  countsOf,
  indexFindings,
  type Severity,
} from "@features/pack-outcome/check";
import { EmptyState } from "@shared/ui";
import { useSpace, parseSelection } from "../context/SpaceContext";
import { CheckFailure } from "./CheckFailure";
import { Coverage } from "./Coverage";
import { FindingGroups } from "./Findings";
import { Notice } from "./Notice";
import { plainFinding } from "../plain/findings";
import { useCheckEnv } from "./useCheckEnv";

/** Фильтры и поиск нужны, когда находок много: до этого они только мешают. */
const FILTER_FROM = 6;

type Severities = Severity | "all";

/**
 * «Замечания»: итог проверки шаблона одной фразой, находки по уровням (что не так и как исправить),
 * какие правила проверены готовыми случаями. Всё считает сервер (`outcome/lint`); тексты шаблонов
 * проверяются по кнопке: это дольше и ограничено по частоте.
 */
export const IssuesPart = () => {
  const { t } = useTranslation("packSpace");
  const env = useCheckEnv();
  const { selection } = useSpace();
  const { workspaceId, ref, released, naming } = env;
  const [textsAsked, setTextsAsked] = useState(false);
  const [severity, setSeverity] = useState<Severities>("all");
  const [query, setQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const searchId = useId();

  const base = usePackOutcomeLint(
    workspaceId,
    ref,
    { state: "work_tree" },
    true,
  );
  const texts = usePackOutcomeLint(
    workspaceId,
    ref,
    { state: "work_tree", jinja: true },
    textsAsked,
  );
  // С проверкой текстов ответ полный (те же правила и ещё сборка шаблонов): он заменяет прежний.
  const data = textsAsked && texts.data ? texts.data : base.data;
  const textsBusy = textsAsked && texts.isFetching && !texts.data;
  const textsFailed = textsAsked && texts.isError && !texts.data;

  const element = parseSelection(selection);
  const findings = useMemo(() => data?.findings ?? [], [data?.findings]);
  const shownItems = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return indexFindings(findings).filter(
      ({ finding }) =>
        (severity === "all" || finding.severity === severity) &&
        (!selectedOnly ||
          finding.elements.some(
            (item) => `${item.section}:${item.id}` === selection,
          )) &&
        (needle === "" ||
          (() => {
            const plain = plainFinding(finding, naming, t);
            return [
              plain.title,
              plain.how,
              finding.file ?? "",
              ...finding.elements.map((item) =>
                naming.element(item.section, item.id),
              ),
            ];
          })().some((text) => text.toLocaleLowerCase().includes(needle))),
    );
  }, [findings, severity, query, selectedOnly, selection, naming, t]);
  const groups = SEVERITIES.flatMap((level) => {
    const items = shownItems.filter((item) => item.finding.severity === level);
    return items.length > 0 ? [{ severity: level, items }] : [];
  });

  if (!data) {
    if (base.isError) {
      return (
        <CheckFailure
          kind="issues"
          error={base.error}
          onRetry={() => void base.refetch()}
        />
      );
    }
    const waiting = classifyOutcomeFailure(base.failureReason);
    return (
      <p className="sp-ck-loading" role="status">
        <RefreshCw size="0.875rem" aria-hidden="true" className="sp-ck-spin" />
        {base.failureCount > 0 && waiting.kind === "rate_limited"
          ? t("check.issues.rateWait", { seconds: waiting.retryAfterS })
          : base.failureCount > 0
            ? t("check.issues.busyRetry", { count: base.failureCount })
            : t("check.issues.loading")}
      </p>
    );
  }

  const counts = countsOf(data);
  const clean = findings.length === 0;
  const filterOn = severity !== "all" || query.trim() !== "" || selectedOnly;
  return (
    <div
      className="sp-ck-stack"
      aria-busy={base.isFetching || textsBusy || undefined}
    >
      <section
        className="sp-ck-card sp-ck-summary"
        data-clean={clean || undefined}
      >
        <div>
          <h3 className="sp-ck-h3">
            {counts.errors > 0 ? (
              <TriangleAlert size="1rem" aria-hidden="true" />
            ) : (
              <CheckCircle2 size="1rem" aria-hidden="true" />
            )}
            {t("check.issues.summary", {
              errors: counts.errors,
              warnings: counts.warnings,
            })}
          </h3>
          {counts.infos > 0 && (
            <p className="sp-ck-note">
              {t("check.issues.infos", { count: counts.infos })}
            </p>
          )}
        </div>
        <div className="sp-ck-actions">
          <button
            type="button"
            className="btn sm"
            disabled={base.isFetching}
            onClick={() => void base.refetch()}
          >
            <RefreshCw
              size="0.8125rem"
              aria-hidden="true"
              className={base.isFetching ? "sp-ck-spin" : undefined}
            />
            {t("check.issues.recheck")}
          </button>
          <button
            type="button"
            className="btn sm"
            disabled={textsBusy || data.jinja === "ran"}
            title={t("check.issues.textsHint")}
            onClick={() => {
              if (textsFailed) void texts.refetch();
              else setTextsAsked(true);
            }}
          >
            <ShieldCheck size="0.8125rem" aria-hidden="true" />
            {data.jinja === "ran"
              ? t("check.issues.textsDone")
              : t("check.issues.textsRun")}
          </button>
        </div>
      </section>

      {released && <Notice title={t("check.issues.released")} />}
      {data.atlas_skipped === true && (
        <Notice title={t("check.issues.skippedTitle")}>
          {t("check.issues.skippedLead")}
        </Notice>
      )}
      {base.isError && (
        <Notice
          tone="error"
          title={t("check.issues.stale")}
          actions={
            <button
              type="button"
              className="btn sm"
              onClick={() => void base.refetch()}
            >
              {t("check.retry")}
            </button>
          }
        />
      )}
      {textsBusy && (
        <p className="sp-ck-loading" role="status">
          <RefreshCw
            size="0.875rem"
            aria-hidden="true"
            className="sp-ck-spin"
          />
          {t("check.issues.textsRunning")}
        </p>
      )}
      {textsFailed && (
        <CheckFailure
          kind="issues"
          error={texts.error}
          onRetry={() => void texts.refetch()}
        />
      )}
      {data.jinja === "unavailable" && (
        <p className="sp-ck-note">{t("check.issues.textsUnavailable")}</p>
      )}

      <section aria-label={t("check.issues.title")}>
        {findings.length >= FILTER_FROM && (
          <div className="sp-ck-toolbar" role="search">
            <label htmlFor={searchId} className="sp-ck-search">
              <span className="sr-only">{t("check.issues.search")}</span>
              <input
                id={searchId}
                type="search"
                className="input"
                placeholder={t("check.issues.searchPlaceholder")}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
              />
            </label>
            <div
              className="sp-ck-seg"
              role="group"
              aria-label={t("check.issues.level")}
            >
              {(["all", ...SEVERITIES] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={severity === value}
                  onClick={() => {
                    setSeverity(value);
                  }}
                >
                  {t(`check.issues.filter.${value}`)}
                </button>
              ))}
            </div>
            {element && (
              <label className="sp-ck-check">
                <input
                  type="checkbox"
                  checked={selectedOnly}
                  onChange={(event) => {
                    setSelectedOnly(event.target.checked);
                  }}
                />
                {t("check.issues.selectedOnly", {
                  name: naming.element(element.section, element.id),
                })}
              </label>
            )}
          </div>
        )}
        {clean ? (
          <EmptyState
            framed
            icon={<CheckCircle2 size="1.5rem" />}
            title={t("check.issues.emptyTitle")}
            description={t("check.issues.emptyLead")}
          />
        ) : groups.length === 0 && filterOn ? (
          <EmptyState
            framed
            title={t("check.issues.noMatchTitle")}
            description={t("check.issues.noMatchLead")}
            action={
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  setSeverity("all");
                  setQuery("");
                  setSelectedOnly(false);
                }}
              >
                {t("check.issues.reset")}
              </button>
            }
          />
        ) : (
          <FindingGroups groups={groups} env={env} />
        )}
      </section>

      <Coverage coverage={data.coverage} env={env} />
    </div>
  );
};

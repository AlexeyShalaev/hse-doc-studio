import { useId, useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  Eye,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  usePackOutcome,
  usePackScenarioRun,
  usePackScenarios,
  type PackScenarioEntry,
  type PackScenarioRunResult,
} from "@entities/pack-studio";
import {
  ChangeList,
  SCENARIO_LANGS,
  badgeOf,
  formOf,
  nameProblem,
  resultsById,
  scenarioName,
  type ScenarioBadge,
  type ScenarioForm,
} from "@features/pack-outcome/check";
import { Modal } from "@shared/ui";
import { useCopyVersion } from "../../next-step/useCopyVersion";
import { useNaming } from "../../plain/useNaming";
import { WordsOverlay } from "../WordsOverlay";
import { CheckChangeEnv } from "../ChangeEnv";
import { Notice } from "../Notice";
import type { CheckEnv } from "../useCheckEnv";
import { ExpectEditor } from "./ExpectEditor";
import { describeExpect, expectNamesOf } from "./expect";
import { useCaseActions, useFailureText } from "./useCaseActions";

const BADGE_ICON = {
  passed: CheckCircle2,
  failed: CircleAlert,
  error: CircleAlert,
  broken: CircleAlert,
  unchecked: CircleDashed,
  pending: CircleDashed,
  unknown: CircleDashed,
} satisfies Record<ScenarioBadge, typeof CircleDashed>;

const sameForm = (a: ScenarioForm, b: ScenarioForm): boolean =>
  JSON.stringify(a) === JSON.stringify(b);

/** Расхождения: ожидания, которые не сошлись, и что изменилось против запомненного результата. */
const CaseDiff = ({
  entry,
  result,
  env,
  names,
}: {
  entry: PackScenarioEntry;
  result: PackScenarioRunResult;
  env: CheckEnv;
  names: ReturnType<typeof expectNamesOf>;
}) => {
  const { t } = useTranslation("packSpace");
  const asserted = entry.scenario?.assertions ?? [];
  return (
    <div className="sp-ck-diff" data-testid="case-diff">
      {result.failures.length > 0 && (
        <ul className="sp-ck-plain" aria-label={t("check.case.mismatch")}>
          {result.failures.map((failure, index) => {
            const item =
              failure.index === null ? undefined : asserted[failure.index];
            return (
              <li key={`${String(failure.index)}-${String(index)}`}>
                <p className="sp-ck-message">
                  {item
                    ? t("check.case.expectedLine", {
                        text: describeExpect(item, names, t),
                      })
                    : t("check.case.snapshotMismatch")}
                </p>
                <details className="sp-ck-tech">
                  <summary>{t("check.tech")}</summary>
                  <dl>
                    <dt>{t("check.case.techExpected")}</dt>
                    <dd>{failure.expected}</dd>
                    <dt>{t("check.case.techActual")}</dt>
                    <dd>{failure.actual}</dd>
                  </dl>
                </details>
              </li>
            );
          })}
        </ul>
      )}
      {result.changes.length > 0 && (
        <section aria-label={t("check.case.changes")}>
          <h4 className="sp-ck-h4">{t("check.case.changes")}</h4>
          <WordsOverlay path="check.case.words">
            <CheckChangeEnv env={env}>
              <ChangeList changes={result.changes} testId="case-changes" />
            </CheckChangeEnv>
          </WordsOverlay>
        </section>
      )}
    </div>
  );
};

/** Форма правки: название на двух языках и ожидания. Пересоздаётся с новой записью файла (ETag). */
const EditForm = ({
  entry,
  env,
  names,
  outcome,
  actions,
}: {
  entry: PackScenarioEntry;
  env: CheckEnv;
  names: ReturnType<typeof expectNamesOf>;
  outcome: ReturnType<typeof usePackOutcome>["data"];
  actions: ReturnType<typeof useCaseActions>;
}) => {
  const { t } = useTranslation("packSpace");
  const failureText = useFailureText();
  const refresh = usePackScenarios(
    env.workspaceId,
    env.ref.pack,
    env.ref.template,
    true,
  ).refetch;
  const [initial] = useState(() =>
    formOf(entry.scenario, env.ref.version, entry.id),
  );
  const [form, setForm] = useState<ScenarioForm>(initial);
  const [nameEmpty, setNameEmpty] = useState(false);
  const base = useId();
  const writable = !env.released;
  const dirty = !sameForm(form, initial);
  const failure = actions.failure;

  return (
    <section className="sp-ck-section" aria-labelledby={`${base}-h`}>
      <h3 className="sp-ck-h3" id={`${base}-h`}>
        {t("check.case.properties")}
      </h3>
      {failure && (
        <Notice
          tone="error"
          title={failureText(failure)}
          actions={
            failure.kind === "stale" || failure.kind === "missing" ? (
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  actions.clearFailure();
                  void refresh();
                }}
              >
                {t("check.case.refresh")}
              </button>
            ) : null
          }
        />
      )}
      <div className="sp-ck-fields">
        {SCENARIO_LANGS.map((lang) => (
          <label key={lang} className="sp-ck-field" htmlFor={`${base}-${lang}`}>
            <span className="sp-ck-note">{t(`check.case.name_${lang}`)}</span>
            <input
              id={`${base}-${lang}`}
              className="input"
              value={form.name[lang]}
              disabled={!writable || actions.pending}
              aria-invalid={nameEmpty || undefined}
              onChange={(event) => {
                setNameEmpty(false);
                setForm({
                  ...form,
                  name: { ...form.name, [lang]: event.target.value },
                });
              }}
            />
          </label>
        ))}
        {nameEmpty && (
          <p className="sp-ck-note" role="alert">
            {t("check.case.nameRequired")}
          </p>
        )}
      </div>
      <h4 className="sp-ck-h4">{t("check.expect.title")}</h4>
      <p className="sp-ck-note">{t("check.expect.lead")}</p>
      <ExpectEditor
        value={form.assertions}
        onChange={(assertions) => {
          setForm({ ...form, assertions });
        }}
        outcome={outcome}
        names={names}
        disabled={!writable || actions.pending}
      />
      {writable && (
        <div className="sp-ck-actions">
          <button
            type="button"
            className="btn primary"
            disabled={!dirty || actions.pending}
            data-testid="case-save"
            onClick={() => {
              if (nameProblem(form)) {
                setNameEmpty(true);
                return;
              }
              void actions.save(entry, form);
            }}
          >
            {t("check.case.save")}
          </button>
        </div>
      )}
    </section>
  );
};

/**
 * Окно готового случая («Открыть случай» из строки или клетки таблицы): итог проверки, чем результат
 * отличается от ожидаемого, «Принять текущий результат как ожидаемый», название и ожидания словами,
 * «Посмотреть как студент» и «Удалить случай» с подтверждением. В выпущенной версии только чтение
 * и «Править копию».
 */
export const CaseDialog = ({
  env: screenEnv,
  caseId,
  onClose,
  onStudent,
  onShow,
}: {
  env: CheckEnv;
  caseId: string;
  onClose: () => void;
  onStudent: () => void;
  onShow: () => void;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const list = usePackScenarios(
    screenEnv.workspaceId,
    screenEnv.ref.pack,
    screenEnv.ref.template,
    true,
  );
  const run = usePackScenarioRun(
    screenEnv.workspaceId,
    screenEnv.ref,
    "work_tree",
    screenEnv.inputs.data?.revision,
    screenEnv.inputs.data !== undefined,
  );
  const outcome = usePackOutcome(screenEnv.workspaceId, screenEnv.ref, {
    state: "work_tree",
    scenario: caseId,
  });
  // Названия документов и точек сдачи берутся ещё и из результата случая.
  const naming = useNaming(
    screenEnv.workspaceId,
    screenEnv.ref,
    screenEnv.inputs.data?.inputs,
    outcome.data,
  );
  const env = useMemo<CheckEnv>(
    () => ({ ...screenEnv, naming }),
    [screenEnv, naming],
  );
  const actions = useCaseActions(env.workspaceId, env.ref);
  const copy = useCopyVersion({ toastOnError: true });
  const [confirm, setConfirm] = useState(false);
  const [accepting, setAccepting] = useState(false);

  const entry = list.data?.scenarios.find((item) => item.id === caseId);
  const results = useMemo(() => resultsById(run.data), [run.data]);
  const runState = run.data ? "ready" : run.isError ? "failed" : "loading";
  const badge: ScenarioBadge = entry
    ? badgeOf(entry, results, runState)
    : "unknown";
  const result = results.get(caseId);
  const names = useMemo(
    () => expectNamesOf(outcome.data, i18n.language, env.naming, t),
    [outcome.data, i18n.language, env.naming, t],
  );
  const name = entry ? scenarioName(entry, i18n.language) : "";
  const writable = !env.released;
  const hasSnapshot = entry?.scenario?.snapshot != null;
  const Icon = BADGE_ICON[badge];

  return (
    <Modal
      isOpen
      onClose={onClose}
      width={680}
      title={name === "" ? t("check.case.title") : name}
      description={t("check.case.lead")}
    >
      <div className="sp-ck-case" data-testid="case-dialog">
        {!entry ? (
          <Notice title={t("check.case.failure.missing")} />
        ) : (
          <>
            <section aria-labelledby="sp-ck-case-run">
              <h3 className="sp-ck-h3" id="sp-ck-case-run">
                {t("check.case.result")}
              </h3>
              <p className="sp-ck-sev" data-case-badge={badge}>
                <Icon size="0.875rem" aria-hidden="true" />
                {t(`check.case.badge.${badge}`)}
              </p>
              {badge === "error" && result?.message && (
                <details className="sp-ck-tech">
                  <summary>{t("check.tech")}</summary>
                  <p>{result.message}</p>
                </details>
              )}
              {badge === "broken" && entry.error && (
                <details className="sp-ck-tech">
                  <summary>{t("check.tech")}</summary>
                  <p>{entry.error}</p>
                </details>
              )}
              {result && badge === "failed" && (
                <CaseDiff
                  entry={entry}
                  result={result}
                  env={env}
                  names={names}
                />
              )}
              <div className="sp-ck-actions">
                <button
                  type="button"
                  className="btn sm"
                  disabled={run.isFetching}
                  onClick={() => void run.refetch()}
                >
                  <RefreshCw
                    size="0.8125rem"
                    aria-hidden="true"
                    className={run.isFetching ? "sp-ck-spin" : undefined}
                  />
                  {t("check.cases.rerun")}
                </button>
                {writable && entry.scenario && badge !== "broken" && (
                  <button
                    type="button"
                    className={badge === "failed" ? "btn sm primary" : "btn sm"}
                    disabled={accepting || actions.pending}
                    data-testid="case-accept"
                    onClick={() => {
                      setAccepting(true);
                      void actions.accept(entry).finally(() => {
                        setAccepting(false);
                      });
                    }}
                  >
                    {t(hasSnapshot ? "check.case.accept" : "check.case.record")}
                  </button>
                )}
                <button
                  type="button"
                  className="btn sm"
                  data-testid="case-show"
                  onClick={onShow}
                >
                  {t("check.cases.show")}
                </button>
                {entry.scenario && (
                  <button
                    type="button"
                    className="btn sm"
                    data-testid="case-student-open"
                    onClick={onStudent}
                  >
                    <Eye size="0.8125rem" aria-hidden="true" />
                    {t("check.cases.student")}
                  </button>
                )}
              </div>
              {writable &&
                entry.scenario &&
                hasSnapshot &&
                badge === "failed" && (
                  <p className="sp-ck-note">{t("check.case.acceptHint")}</p>
                )}
            </section>

            {!writable && (
              <Notice
                title={t("check.case.released")}
                actions={
                  <button
                    type="button"
                    className="btn sm primary"
                    disabled={copy.pending}
                    data-testid="case-copy"
                    onClick={() => void copy.run()}
                  >
                    {t("check.case.copy")}
                  </button>
                }
              />
            )}

            {entry.scenario && (
              <EditForm
                key={entry.etag}
                entry={entry}
                env={env}
                names={names}
                outcome={outcome.data}
                actions={actions}
              />
            )}

            <div className="sp-ck-actions sp-ck-foot">
              {writable && !confirm && (
                <button
                  type="button"
                  className="btn sm danger"
                  data-testid="case-delete"
                  onClick={() => {
                    setConfirm(true);
                  }}
                >
                  <Trash2 size="0.8125rem" aria-hidden="true" />
                  {t("check.case.delete")}
                </button>
              )}
              {writable && confirm && (
                <span
                  className="sp-ck-confirm"
                  role="alertdialog"
                  aria-label={t("check.case.confirmTitle", { name })}
                  data-testid="case-delete-confirm"
                >
                  <span>{t("check.case.confirmTitle", { name })}</span>
                  <button
                    type="button"
                    className="btn sm danger"
                    disabled={actions.pending}
                    data-testid="case-delete-yes"
                    onClick={() => {
                      void actions.remove(entry).then((done) => {
                        if (done) onClose();
                        else setConfirm(false);
                      });
                    }}
                  >
                    {t("check.case.confirmYes")}
                  </button>
                  <button
                    type="button"
                    className="btn sm"
                    onClick={() => {
                      setConfirm(false);
                    }}
                  >
                    {t("check.case.confirmNo")}
                  </button>
                </span>
              )}
              <button type="button" className="btn sm" onClick={onClose}>
                {t("check.case.close")}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};

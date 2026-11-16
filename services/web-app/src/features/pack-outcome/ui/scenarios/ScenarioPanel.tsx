import { useState } from "react";
import { Copy, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  packWorkspacePath,
  type PackScenarioEntry,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui";
import {
  formOf,
  nameProblem,
  requestOf,
  scenarioName,
  badgeOf,
  type ScenarioForm,
} from "../../lib/scenarios";
import { useOutcomeModel } from "../../model";
import { Notice } from "../Notice";
import { FailureNotice } from "./FailureNotice";
import { RunDiff } from "./RunDiff";
import { ScenarioFields, type FieldErrors } from "./ScenarioFields";
import { ScenarioStatus } from "./ScenarioStatus";
import { useScenarioUi } from "./context";
import { useScenarioOutcome } from "./useScenarioOutcome";
import { useScenarioWrite } from "./useScenarioWrite";

type ScenarioPanelProps = {
  id: string;
  onClose: () => void;
};

const sameForm = (a: ScenarioForm, b: ScenarioForm) =>
  JSON.stringify(a) === JSON.stringify(b);

type EditFormProps = {
  entry: PackScenarioEntry;
  writable: boolean;
};

/** Форма правки: переименовать, описание, версии, ожидания. Пересоздаётся с новым ETag записи. */
const EditForm = ({ entry, writable }: EditFormProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { ref, workspaceId, url } = model;
  const scenario = entry.scenario;
  const outcome = useScenarioOutcome(entry.id, undefined);
  const write = useScenarioWrite(workspaceId, ref);
  const [initial] = useState(() => formOf(scenario, ref.version, entry.id));
  const [form, setForm] = useState<ScenarioForm>(initial);
  const [errors, setErrors] = useState<FieldErrors>({});
  if (!scenario) return null;

  const dirty = !sameForm(form, initial);
  const submit = async (ifMatch: string) => {
    if (nameProblem(form)) {
      setErrors({ name: t("scenarios.fields.nameRequired") });
      return;
    }
    setErrors({});
    const saved = await write.submit({
      scenario: entry.id,
      ifMatch,
      body: requestOf(form, {
        base: scenario,
        inputs: scenario.inputs,
        example: scenario.example ?? null,
        version: ref.version,
        state: url.state.state,
      }),
    });
    if (saved) {
      toast.success(
        t("scenarios.saved", { name: scenarioName(saved, i18n.language) }),
      );
    }
  };

  const failure = write.failure;
  const serverErrors: FieldErrors = {};
  if (failure?.kind === "invalid") {
    if (failure.field === "name") serverErrors.name = failure.reason;
    else if (failure.field === "versions")
      serverErrors.versions = failure.reason;
  }
  return (
    <section className="po-sc-section" aria-labelledby="po-sc-edit-h">
      <h3 className="po-sc-h" id="po-sc-edit-h">
        {t("scenarios.panel.properties")}
      </h3>
      {failure && (
        <FailureNotice
          failure={failure}
          onRetry={() => void submit(entry.etag)}
          onRefresh={() => {
            write.clear();
            void model.scenarios.refetch();
          }}
          onOverwrite={
            failure.kind === "stale" && failure.diskEtag
              ? () => void submit(failure.diskEtag ?? entry.etag)
              : undefined
          }
        />
      )}
      <ScenarioFields
        form={form}
        onChange={(next) => {
          setForm(next);
          setErrors({});
        }}
        mode="edit"
        version={ref.version}
        taken={new Set()}
        outcome={outcome}
        hadSnapshot={scenario.snapshot != null}
        errors={{ ...errors, ...serverErrors }}
        disabled={!writable || write.pending}
      />
      {writable && (
        <div className="po-sc-save">
          <button
            type="button"
            className="btn primary"
            disabled={!dirty || write.pending}
            data-testid="scenario-panel-save"
            onClick={() => void submit(entry.etag)}
          >
            {write.pending ? t("scenarios.saving") : t("scenarios.save")}
          </button>
        </div>
      )}
    </section>
  );
};

/**
 * Панель выбранного сценария: статус и расхождение с ожиданиями (разделы и элементы со знаками
 * плюс, тильда, минус), «Принять текущий результат как ожидаемый», правка названия, описания,
 * версий и утверждений, «Дублировать» и «Удалить» (с «Отменить» на десять секунд).
 */
export const ScenarioPanel = ({ id, onClose }: ScenarioPanelProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const [accepting, setAccepting] = useState(false);
  if (!ui) return null;
  const entry = ui.entries.find((item) => item.id === id);
  const writable = ui.canWrite;
  const badge = entry ? badgeOf(entry, ui.results, ui.runState) : "unknown";
  const result = ui.results.get(id);
  const own = model.url.state.scenario === id;
  const overridden = own && Object.keys(model.url.state.inputs).length > 0;
  const hasSnapshot = entry?.scenario?.snapshot != null;

  const title = entry ? scenarioName(entry, i18n.language) : id;

  return (
    <Modal
      isOpen
      onClose={onClose}
      width={640}
      title={title}
      description={entry?.path}
    >
      <div className="po-sc-panel" data-testid="scenario-panel">
        {!entry ? (
          <Notice
            tone="info"
            title={t("scenarios.failure.missingTitle")}
            testId="scenario-panel-missing"
          >
            {t("scenarios.failure.missingLead")}
          </Notice>
        ) : (
          <>
            <section className="po-sc-section" aria-labelledby="po-sc-run-h">
              <h3 className="po-sc-h" id="po-sc-run-h">
                {t("scenarios.panel.result")}
              </h3>
              <p className="po-sc-line">
                <ScenarioStatus status={badge} />
                {ui.running && (
                  <span className="po-in-hint">{t("scenarios.running")}</span>
                )}
              </p>
              {badge === "broken" && (
                <Notice
                  tone="error"
                  title={t("scenarios.panel.brokenTitle")}
                  testId="scenario-panel-broken"
                  actions={
                    <Link
                      className="btn sm"
                      to={packWorkspacePath(model.workspaceId, entry.path)}
                      data-testid="scenario-open-file"
                    >
                      {t("scenarios.panel.openFile")}
                    </Link>
                  }
                >
                  {entry.error}
                </Notice>
              )}
              {badge === "passed" && (
                <p className="po-in-hint">{t("scenarios.panel.passed")}</p>
              )}
              {badge === "unchecked" && (
                <p className="po-in-hint">
                  {result?.message ?? t("scenarios.panel.unchecked")}
                </p>
              )}
              {badge === "error" && (
                <Notice
                  tone="error"
                  title={t("scenarios.panel.errorTitle")}
                  testId="scenario-panel-error"
                >
                  {result?.message ?? t("scenarios.panel.errorLead")}
                </Notice>
              )}
              {result && badge === "failed" && <RunDiff result={result} />}
              {(badge === "pending" || badge === "unknown") && (
                <p className="po-in-hint">{t("scenarios.panel.noRun")}</p>
              )}
              {overridden && (
                <p className="po-in-hint" data-testid="scenario-overridden">
                  {t("scenarios.panel.overridden")}
                </p>
              )}
              <div className="po-sc-actions-row">
                <button
                  type="button"
                  className="btn sm"
                  disabled={ui.running}
                  data-testid="scenario-panel-run"
                  onClick={ui.rerun}
                >
                  {t("scenarios.runAll")}
                </button>
                {writable && entry.scenario && badge !== "broken" && (
                  <button
                    type="button"
                    className={badge === "failed" ? "btn sm primary" : "btn sm"}
                    disabled={accepting}
                    data-testid="scenario-accept"
                    onClick={() => {
                      setAccepting(true);
                      void ui.accept(entry).finally(() => {
                        setAccepting(false);
                      });
                    }}
                  >
                    {t(
                      hasSnapshot
                        ? "scenarios.panel.accept"
                        : "scenarios.panel.record",
                    )}
                  </button>
                )}
              </div>
              {writable &&
                entry.scenario &&
                hasSnapshot &&
                badge === "failed" && (
                  <p className="po-in-hint">
                    {t("scenarios.panel.acceptHint")}
                  </p>
                )}
            </section>
            {entry.scenario && (
              <EditForm key={entry.etag} entry={entry} writable={writable} />
            )}
            <div className="po-sc-actions-row po-sc-foot">
              {writable && entry.scenario && (
                <button
                  type="button"
                  className="btn sm"
                  data-testid="scenario-duplicate"
                  onClick={() => {
                    ui.open({ kind: "duplicate", id: entry.id });
                  }}
                >
                  <Copy size="0.8125rem" aria-hidden="true" />
                  {t("scenarios.panel.duplicate")}
                </button>
              )}
              {writable && (
                <button
                  type="button"
                  className="btn sm danger"
                  data-testid="scenario-delete"
                  onClick={() => {
                    void ui.remove(entry).then((done) => {
                      if (done) onClose();
                    });
                  }}
                >
                  <Trash2 size="0.8125rem" aria-hidden="true" />
                  {t("scenarios.panel.delete")}
                </button>
              )}
              <button
                type="button"
                className="btn sm"
                data-testid="scenario-panel-close"
                onClick={onClose}
              >
                {t("scenarios.close")}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};

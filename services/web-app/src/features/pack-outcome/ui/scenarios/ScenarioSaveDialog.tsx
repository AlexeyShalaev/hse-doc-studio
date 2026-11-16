import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PackScenarioEntry } from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui";
import {
  SCENARIO_LANGS,
  formOf,
  freeId,
  idProblem,
  mergedInputs,
  nameProblem,
  requestOf,
  scenarioName,
  type ScenarioForm,
} from "../../lib/scenarios";
import { useOutcomeModel } from "../../model";
import { FailureNotice } from "./FailureNotice";
import { ScenarioFields, type FieldErrors } from "./ScenarioFields";
import { useScenarioUi } from "./context";
import { useScenarioOutcome } from "./useScenarioOutcome";
import { useScenarioWrite } from "./useScenarioWrite";

type ScenarioSaveDialogProps = {
  /** `create`: из текущих вводных и набора данных; `duplicate`: копия `source`. */
  mode: "create" | "duplicate";
  source?: PackScenarioEntry | undefined;
  onClose: () => void;
};

/**
 * «Сохранить как сценарий»: имя, описание, версии и что запомнить как ожидаемый результат.
 * Вводные берутся с экрана (выбранный сценарий и изменения поверх него), набор данных тоже.
 */
export const ScenarioSaveDialog = ({
  mode,
  source,
  onClose,
}: ScenarioSaveDialogProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const { url, ref, workspaceId, scenarios, shown } = model;
  const taken = new Set((ui?.entries ?? []).map((entry) => entry.id));
  const outcome = useScenarioOutcome(
    mode === "duplicate" ? (source?.id ?? null) : null,
    shown,
  );
  const write = useScenarioWrite(workspaceId, ref);

  const [form, setForm] = useState<ScenarioForm>(() => {
    if (mode === "duplicate" && source?.scenario) {
      const copy = formOf(source.scenario, ref.version, "");
      const suffix = t("scenarios.copySuffix");
      for (const lang of SCENARIO_LANGS) {
        if (copy.name[lang] !== "") copy.name[lang] += ` ${suffix}`;
      }
      copy.id = freeId(`${source.id}-copy`, taken);
      return copy;
    }
    return formOf(null, ref.version, "");
  });
  const [errors, setErrors] = useState<FieldErrors>({});

  const picked = url.state.scenario;
  const inputs =
    mode === "duplicate"
      ? (source?.scenario?.inputs ?? {})
      : mergedInputs(scenarios.data, picked, url.state.inputs);
  const example =
    mode === "duplicate"
      ? (source?.scenario?.example ?? null)
      : (url.state.example ??
        scenarios.data?.scenarios.find((entry) => entry.id === picked)?.scenario
          ?.example ??
        null);

  const submit = async (id = form.id, current = form) => {
    const next: FieldErrors = {};
    if (nameProblem(current)) next.name = t("scenarios.fields.nameRequired");
    const problem = idProblem(id);
    if (problem === "empty") next.id = t("scenarios.fields.idRequired");
    else if (problem === "format") next.id = t("scenarios.fields.idFormat");
    else if (taken.has(id)) next.id = t("scenarios.fields.idTaken");
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const entry = await write.submit({
      scenario: id,
      ifMatch: null,
      body: requestOf(current, {
        base: mode === "duplicate" ? (source?.scenario ?? null) : null,
        inputs,
        example,
        version: ref.version,
        state: url.state.state,
      }),
    });
    if (!entry) return;
    toast.success(
      t("scenarios.saved", { name: scenarioName(entry, i18n.language) }),
    );
    // Вводные теперь в файле: изменения на экране больше не «поверх», выбор переходит к сценарию.
    url.update({ scenario: entry.id, inputs: {}, example: null });
    onClose();
  };

  const failure = write.failure;
  const serverErrors: FieldErrors = {};
  if (failure?.kind === "invalid") {
    if (failure.field === "id") serverErrors.id = failure.reason;
    else if (failure.field === "name") serverErrors.name = failure.reason;
    else if (failure.field === "versions")
      serverErrors.versions = failure.reason;
  }
  const freeName = freeId(
    form.id === "" ? "scenario" : form.id,
    new Set([...taken, form.id]),
  );

  return (
    <Modal
      isOpen
      onClose={onClose}
      width={600}
      title={t(
        mode === "create"
          ? "scenarios.dialog.createTitle"
          : "scenarios.dialog.duplicateTitle",
      )}
      description={t(
        mode === "create"
          ? "scenarios.dialog.createLead"
          : "scenarios.dialog.duplicateLead",
      )}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            {t("scenarios.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={write.pending}
            data-testid="scenario-submit"
            onClick={() => void submit()}
          >
            {write.pending ? t("scenarios.saving") : t("scenarios.save")}
          </button>
        </>
      }
    >
      <div className="po-sc-dialog" data-testid="scenario-save-dialog">
        {mode === "create" && Object.keys(inputs).length > 0 && (
          <p className="po-in-hint" data-testid="scenario-inputs-note">
            {t("scenarios.dialog.inputsNote", {
              count: Object.keys(inputs).length,
            })}
          </p>
        )}
        {failure && (
          <FailureNotice
            failure={failure}
            onRetry={() => void submit()}
            onRefresh={() => {
              write.clear();
              void model.scenarios.refetch();
            }}
          />
        )}
        {failure?.kind === "taken" && (
          <p className="po-sc-take">
            <button
              type="button"
              className="btn sm"
              data-testid="scenario-take-free"
              onClick={() => {
                const next = { ...form, id: freeName };
                setForm(next);
                write.clear();
                void submit(freeName, next);
              }}
            >
              {t("scenarios.failure.takeFree", { id: freeName })}
            </button>
          </p>
        )}
        <ScenarioFields
          form={form}
          onChange={(next) => {
            setForm(next);
            setErrors({});
          }}
          mode={mode}
          version={ref.version}
          taken={taken}
          outcome={outcome}
          hadSnapshot={false}
          errors={{ ...errors, ...serverErrors }}
          disabled={write.pending}
        />
      </div>
    </Modal>
  );
};

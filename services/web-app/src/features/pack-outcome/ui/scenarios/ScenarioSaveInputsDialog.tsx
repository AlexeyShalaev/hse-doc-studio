import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { Modal } from "@shared/ui";
import { inputChanges, mergedInputs, scenarioName } from "../../lib/scenarios";
import { useOutcomeModel } from "../../model";
import { useInputLabels } from "../inputs/useLabels";
import { FailureNotice } from "./FailureNotice";
import { useScenarioUi } from "./context";
import { useScenarioWrite } from "./useScenarioWrite";

type ScenarioSaveInputsDialogProps = {
  id: string;
  onClose: () => void;
};

/**
 * «Сохранить в сценарий»: вводные, изменённые на экране относительно сценария, записываются в
 * его файл. Окно показывает, что именно поменяется; снимок по желанию обновляется сразу.
 */
export const ScenarioSaveInputsDialog = ({
  id,
  onClose,
}: ScenarioSaveInputsDialogProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const { url, ref, workspaceId, scenarios, inputs } = model;
  const { inputLabel, valueLabel } = useInputLabels();
  const write = useScenarioWrite(workspaceId, ref);
  const entry = ui?.entries.find((item) => item.id === id);
  const scenario = entry?.scenario ?? null;
  const [refresh, setRefresh] = useState(scenario?.snapshot != null);
  if (!ui || !entry || !scenario) return null;

  const after = mergedInputs(scenarios.data, id, url.state.inputs);
  const changes = inputChanges(scenario.inputs, after);
  const example = url.state.example;
  const exampleChanged = example !== null && example !== scenario.example;
  const defs = new Map((inputs.data?.inputs ?? []).map((i) => [i.id, i]));
  const name = scenarioName(entry, i18n.language);

  const submit = async (ifMatch: string) => {
    const saved = await write.submit({
      scenario: id,
      ifMatch,
      body: {
        scenario: {
          ...scenario,
          inputs: after,
          ...(exampleChanged ? { example } : {}),
        },
        ...(refresh && scenario.snapshot != null
          ? { record_snapshot: url.state.state, version: ref.version }
          : {}),
      },
    });
    if (!saved) return;
    toast.success(t("scenarios.inputsSaved", { name }));
    url.update({ inputs: {}, example: null });
    onClose();
  };

  const failure = write.failure;
  return (
    <Modal
      isOpen
      onClose={onClose}
      width={520}
      className="po-sheet"
      title={t("scenarios.saveInputs.title", { name })}
      description={t("scenarios.saveInputs.lead")}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            {t("scenarios.cancel")}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={
              write.pending || (changes.length === 0 && !exampleChanged)
            }
            data-testid="scenario-save-inputs-submit"
            onClick={() => void submit(entry.etag)}
          >
            {write.pending ? t("scenarios.saving") : t("scenarios.save")}
          </button>
        </>
      }
    >
      <div className="po-sc-dialog" data-testid="scenario-save-inputs">
        {failure && (
          <FailureNotice
            failure={failure}
            onRetry={() => void submit(entry.etag)}
            onRefresh={() => {
              write.clear();
              void scenarios.refetch();
            }}
            onOverwrite={
              failure.kind === "stale" && failure.diskEtag
                ? () => void submit(failure.diskEtag ?? entry.etag)
                : undefined
            }
          />
        )}
        <ul
          className="po-sc-changes"
          aria-label={t("scenarios.saveInputs.list")}
        >
          {changes.map((change) => {
            const def = defs.get(change.id);
            const label = def ? inputLabel(def) : change.id;
            const show = (value: string) =>
              def ? valueLabel(def, value) : value;
            return (
              <li
                key={change.id}
                data-symbol={change.before === null ? "added" : "changed"}
              >
                <span className="po-sc-sign" aria-hidden="true">
                  {change.before === null ? "+" : "~"}
                </span>
                <span className="po-sc-change-text">
                  {change.before === null
                    ? t("scenarios.saveInputs.added", {
                        input: label,
                        value: show(change.after),
                      })
                    : t("scenarios.saveInputs.changed", {
                        input: label,
                        before: show(change.before),
                        after: show(change.after),
                      })}
                </span>
              </li>
            );
          })}
          {exampleChanged && (
            <li data-symbol="changed">
              <span className="po-sc-sign" aria-hidden="true">
                ~
              </span>
              <span className="po-sc-change-text">
                {t("scenarios.saveInputs.example", { value: example })}
              </span>
            </li>
          )}
        </ul>
        {scenario.snapshot != null && (
          <label className="po-check">
            <input
              type="checkbox"
              checked={refresh}
              data-testid="scenario-save-inputs-refresh"
              onChange={(event) => {
                setRefresh(event.target.checked);
              }}
            />
            <span>{t("scenarios.saveInputs.refresh")}</span>
          </label>
        )}
        {(scenario.assertions?.length ?? 0) > 0 && (
          <p className="po-in-hint">{t("scenarios.saveInputs.assertions")}</p>
        )}
      </div>
    </Modal>
  );
};

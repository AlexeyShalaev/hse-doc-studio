import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useDeletePackScenario,
  usePackScenarioRun,
  useWritePackScenario,
  type PackScenarioEntry,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import {
  classifyFailure,
  resultsById,
  scenarioName,
  tallyOf,
} from "../../lib/scenarios";
import { useSheetHistory } from "../../lib/useSheetHistory";
import { useOutcomeModel } from "../../model";
import {
  ScenarioUiContext,
  type ScenarioDialog,
  type ScenarioUi,
} from "./context";
import { ScenarioPanel } from "./ScenarioPanel";
import { ScenarioSaveDialog } from "./ScenarioSaveDialog";
import { ScenarioSaveInputsDialog } from "./ScenarioSaveInputsDialog";

/** Сколько живёт кнопка «Отменить» после удаления сценария. */
export const UNDO_MS = 10_000;
const EMPTY: readonly PackScenarioEntry[] = [];

type ScenariosHostProps = {
  children: ReactNode;
  /** Окно, открытое сразу (галерея состояний). */
  initialDialog?: ScenarioDialog | null;
};

/**
 * Сценарии экрана «Результат»: прогон всех сценариев, действия (удалить с «Отменить», принять
 * результат как ожидаемый) и окна. Статусы и расхождения считает сервер, здесь они только
 * раскладываются по значкам. Всё отдаётся в контекст, поэтому панели не перерисовываются зря.
 */
export const ScenariosHost = ({
  children,
  initialDialog = null,
}: ScenariosHostProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { workspaceId, ref, url, scenarios, inputs, student } = {
    ...model,
    student: model.url.state.mode === "student",
  };
  const [dialog, setDialog] = useState<ScenarioDialog | null>(initialDialog);
  // Телефон: окна и список сценариев закрываются кнопкой «Назад» браузера.
  useSheetHistory("scenarios", model.phone && dialog !== null, () => {
    setDialog(null);
  });

  const entries = scenarios.data?.scenarios ?? EMPTY;
  const runnable = entries.some((entry) => entry.error === null);
  const run = usePackScenarioRun(
    workspaceId,
    ref,
    url.state.state,
    inputs.data?.revision,
    runnable,
  );
  const results = useMemo(() => resultsById(run.data), [run.data]);
  const tally = useMemo(() => tallyOf(entries, run.data), [entries, run.data]);
  const runState: ScenarioUi["runState"] = !runnable
    ? "ready"
    : run.data !== undefined
      ? "ready"
      : run.isError
        ? "failed"
        : "loading";

  const write = useWritePackScenario(workspaceId, ref.pack, ref.template);
  const del = useDeletePackScenario(workspaceId, ref.pack, ref.template);
  const { mutateAsync: putScenario } = write;
  const { mutateAsync: deleteScenario } = del;
  const { update, state: urlState } = url;
  const refetchScenarios = scenarios.refetch;
  const refetchRun = run.refetch;

  const canWrite = !student && urlState.state === "work_tree";
  const readOnlyReason: ScenarioUi["readOnlyReason"] = student
    ? "student"
    : urlState.state !== "work_tree"
      ? "state"
      : null;

  const failureToast = useCallback(
    (error: unknown) => {
      const failure = classifyFailure(error);
      if (failure.kind === "stale" || failure.kind === "missing") {
        toast.warning(t("scenarios.failure.staleLead"), {
          title: t("scenarios.failure.staleTitle"),
          action: {
            label: t("scenarios.failure.refresh"),
            onClick: () => {
              void refetchScenarios();
            },
          },
        });
      } else {
        toast.error(packErrorText(error), t("scenarios.failure.title"));
      }
    },
    [refetchScenarios, t],
  );

  const remove = useCallback(
    async (entry: PackScenarioEntry): Promise<boolean> => {
      const scenario = entry.scenario;
      const name = scenarioName(entry, i18n.language);
      const wasSelected = urlState.scenario === entry.id;
      try {
        await deleteScenario({ scenario: entry.id, ifMatch: entry.etag });
      } catch (error) {
        failureToast(error);
        return false;
      }
      if (wasSelected) update({ scenario: null });
      toast.info(t("scenarios.deleted", { name }), {
        action: {
          label: t("scenarios.undo"),
          onClick: () => {
            if (!scenario) return;
            // «Отменить» пишет сценарий заново без If-Match: сервер вернёт те же байты.
            putScenario({
              scenario: entry.id,
              ifMatch: null,
              body: { scenario },
            })
              .then(() => {
                if (wasSelected) update({ scenario: entry.id });
                toast.success(t("scenarios.restored", { name }));
              })
              .catch(failureToast);
          },
        },
        duration: UNDO_MS,
      });
      return true;
    },
    [
      deleteScenario,
      failureToast,
      i18n.language,
      putScenario,
      t,
      update,
      urlState.scenario,
    ],
  );

  const accept = useCallback(
    async (entry: PackScenarioEntry): Promise<boolean> => {
      const before = entry.scenario;
      if (!before) return false;
      const name = scenarioName(entry, i18n.language);
      try {
        const saved = await putScenario({
          scenario: entry.id,
          ifMatch: entry.etag,
          body: {
            scenario: before,
            record_snapshot: urlState.state,
            version: ref.version,
          },
        });
        toast.success(t("scenarios.accepted", { name }), {
          action: {
            label: t("scenarios.undo"),
            onClick: () => {
              putScenario({
                scenario: entry.id,
                ifMatch: saved.etag,
                body: { scenario: before },
              })
                .then(() => {
                  toast.info(t("scenarios.acceptUndone", { name }));
                })
                .catch(failureToast);
            },
          },
          duration: UNDO_MS,
        });
        return true;
      } catch (error) {
        failureToast(error);
        return false;
      }
    },
    [failureToast, i18n.language, putScenario, ref.version, t, urlState.state],
  );

  const rerun = useCallback(() => {
    void refetchRun();
  }, [refetchRun]);
  const reload = useCallback(() => {
    void refetchScenarios();
  }, [refetchScenarios]);

  const ui = useMemo<ScenarioUi>(
    () => ({
      entries,
      loading: scenarios.isPending,
      loadFailed: scenarios.isError ? scenarios.error : null,
      reload,
      run: run.data,
      runState,
      runError: run.isError ? run.error : null,
      running: runnable && run.isFetching,
      results,
      tally,
      rerun,
      canWrite,
      readOnlyReason,
      dialog,
      open: setDialog,
      remove,
      accept,
    }),
    [
      entries,
      scenarios.isPending,
      scenarios.isError,
      scenarios.error,
      reload,
      run.data,
      runState,
      run.isError,
      run.error,
      run.isFetching,
      runnable,
      results,
      tally,
      rerun,
      canWrite,
      readOnlyReason,
      dialog,
      remove,
      accept,
      setDialog,
    ],
  );

  const close = useCallback(() => {
    setDialog(null);
  }, [setDialog]);
  const source = dialog && "id" in dialog ? dialog.id : null;
  const sourceEntry = source
    ? entries.find((entry) => entry.id === source)
    : undefined;

  return (
    <ScenarioUiContext.Provider value={ui}>
      {children}
      {dialog?.kind === "create" && (
        <ScenarioSaveDialog mode="create" onClose={close} />
      )}
      {dialog?.kind === "duplicate" && sourceEntry && (
        <ScenarioSaveDialog
          mode="duplicate"
          source={sourceEntry}
          onClose={close}
        />
      )}
      {dialog?.kind === "panel" && (
        <ScenarioPanel id={dialog.id} onClose={close} />
      )}
      {dialog?.kind === "saveInputs" && (
        <ScenarioSaveInputsDialog id={dialog.id} onClose={close} />
      )}
    </ScenarioUiContext.Provider>
  );
};

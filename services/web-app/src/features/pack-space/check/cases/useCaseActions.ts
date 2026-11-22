import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useDeletePackScenario,
  useWritePackScenario,
  type PackScenarioEntry,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  classifyFailure,
  requestOf,
  scenarioName,
  type ScenarioFailure,
  type ScenarioForm,
} from "@entities/pack-studio/outcome/scenarios";
import { toast } from "@shared/lib";

/** Сколько живёт кнопка «Вернуть» после удаления и «Отменить» после «Принять». */
export const UNDO_MS = 10_000;

/** Отказ записи словами; для незнакомого отказа берётся общий перевод кода. */
export const useFailureText = () => {
  const { t } = useTranslation("packSpace");
  return useCallback(
    (failure: ScenarioFailure): string => {
      switch (failure.kind) {
        case "stale":
          return t("check.case.failure.stale");
        case "missing":
          return t("check.case.failure.missing");
        case "taken":
          return t("check.case.failure.taken");
        case "invalid":
          return t("check.case.failure.invalid");
        case "offline":
          return t("check.case.failure.offline");
        case "busy":
          return t("check.case.failure.busy");
        case "server":
          return t("check.case.failure.server");
        case "other":
          return packErrorText(failure.error);
      }
    },
    [t],
  );
};

/**
 * Действия над готовым случаем: принять текущий результат как ожидаемый, удалить (с возвратом на
 * десять секунд), сохранить название, описание и ожидания. Запись идёт в файл случая в моих
 * правках с `If-Match`; отказ приходит разобранным, окно показывает его словами.
 */
export const useCaseActions = (workspaceId: string, ref: PackVersionRef) => {
  const { t, i18n } = useTranslation("packSpace");
  const failureText = useFailureText();
  const write = useWritePackScenario(workspaceId, ref.pack, ref.template);
  const del = useDeletePackScenario(workspaceId, ref.pack, ref.template);
  const { mutateAsync: put } = write;
  const { mutateAsync: drop } = del;
  const [failure, setFailure] = useState<ScenarioFailure | null>(null);

  const fail = useCallback(
    (error: unknown) => {
      const classified = classifyFailure(error);
      setFailure(classified);
      toast.error(failureText(classified), t("check.case.failure.title"));
    },
    [failureText, t],
  );

  /** Записать текущий результат случая как ожидаемый; `true`, если записано. */
  const accept = useCallback(
    async (entry: PackScenarioEntry): Promise<boolean> => {
      const before = entry.scenario;
      if (!before) return false;
      const name = scenarioName(entry, i18n.language);
      try {
        const saved = await put({
          scenario: entry.id,
          ifMatch: entry.etag,
          body: {
            scenario: before,
            record_snapshot: "work_tree",
            version: ref.version,
          },
        });
        setFailure(null);
        toast.success(t("check.case.accepted", { name }), {
          action: {
            label: t("check.case.undo"),
            onClick: () => {
              put({
                scenario: entry.id,
                ifMatch: saved.etag,
                body: { scenario: before },
              })
                .then(() => {
                  toast.info(t("check.case.acceptUndone", { name }));
                })
                .catch(fail);
            },
          },
          duration: UNDO_MS,
        });
        return true;
      } catch (error) {
        fail(error);
        return false;
      }
    },
    [fail, i18n.language, put, ref.version, t],
  );

  /** Удалить случай; «Вернуть» пишет его заново без `If-Match`. `true`, если удалён. */
  const remove = useCallback(
    async (entry: PackScenarioEntry): Promise<boolean> => {
      const scenario = entry.scenario;
      const name = scenarioName(entry, i18n.language);
      try {
        await drop({ scenario: entry.id, ifMatch: entry.etag });
      } catch (error) {
        fail(error);
        return false;
      }
      setFailure(null);
      toast.info(t("check.case.deleted", { name }), {
        action: {
          label: t("check.case.restore"),
          onClick: () => {
            if (!scenario) return;
            put({ scenario: entry.id, ifMatch: null, body: { scenario } })
              .then(() => {
                toast.success(t("check.case.restored", { name }));
              })
              .catch(fail);
          },
        },
        duration: UNDO_MS,
      });
      return true;
    },
    [drop, fail, i18n.language, put, t],
  );

  /** Сохранить правку формы; `true`, если записано. */
  const save = useCallback(
    async (entry: PackScenarioEntry, form: ScenarioForm): Promise<boolean> => {
      const base = entry.scenario;
      if (!base) return false;
      try {
        const saved = await put({
          scenario: entry.id,
          ifMatch: entry.etag,
          body: requestOf(form, {
            base,
            inputs: base.inputs,
            example: base.example ?? null,
            version: ref.version,
            state: "work_tree",
          }),
        });
        setFailure(null);
        toast.success(
          t("check.case.saved", { name: scenarioName(saved, i18n.language) }),
        );
        return true;
      } catch (error) {
        const classified = classifyFailure(error);
        setFailure(classified);
        return false;
      }
    },
    [i18n.language, put, ref.version, t],
  );

  return {
    accept,
    remove,
    save,
    failure,
    clearFailure: () => {
      setFailure(null);
    },
    pending: write.isPending || del.isPending,
  };
};

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, failureCode } from "@shared/api";
import { Button, ErrorState, Modal, TableSkeleton } from "@shared/ui";
import type { RunnerDiskScope } from "../api/runnerDiskApi";
import {
  useCancelRunnerDiskCleanup,
  useRefreshRunnerDisk,
  useRunnerDisk,
  useSetRunnerDiskAuto,
  useStartRunnerDiskCleanup,
} from "../api/runnerDiskQueries";
import type { RunnerDiskCommand } from "../model/runnerDisk.schema";
import { RunnerDiskPanel } from "./RunnerDiskPanel";

// Окно «Диск» раннера (docs/design/storage-cleanup.md, 4.1, 4.2): тот же размер, что «Как
// развёрнут». Одно на админку («Раннеры», «Личные раннеры», «Хранилище») и «Мои раннеры»:
// различает их только scope.

export type RunnerDiskDialogRunner = {
  id: string;
  name: string;
  /** Для заглушки «Обновите раннер». */
  version?: string | null | undefined;
};

export type RunnerDiskDialogProps = {
  /** admin: /api/admin/runners/{id}/disk*, account: свой раннер в «Моих раннерах». */
  scope: RunnerDiskScope;
  /** null: окно закрыто, запросов нет. */
  runner: RunnerDiskDialogRunner | null;
  onClose: () => void;
  /** Раннер установлен из админки: «Обновить раннер» у заглушки старой версии. */
  onUpgrade?: (() => void) | undefined;
  /** Очистка закрылась на глазах: фича перечитывает свои списки. */
  onCommandSettled?: ((command: RunnerDiskCommand) => void) | undefined;
};

/** Текст отказа по коду каталога ошибок (errors:code.*), иначе общий. */
const useFailureText = () => {
  const { t, i18n } = useTranslation("runnerDisk");
  return (error: unknown): string => {
    const code = failureCode(error);
    if (code === "network") return t("failure.network");
    const key = `errors:code.${code}`;
    return i18n.exists(key) ? t(key) : t("failure.unknown");
  };
};

export const RunnerDiskDialog = ({
  scope,
  runner,
  onClose,
  onUpgrade,
  onCommandSettled,
}: RunnerDiskDialogProps) => {
  const { t } = useTranslation("runnerDisk");
  return (
    <Modal
      isOpen={runner !== null}
      onClose={onClose}
      width={640}
      title={t("title", { name: runner?.name ?? "" })}
      footer={
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("close")}
        </Button>
      }
    >
      {runner && (
        <RunnerDiskDialogBody
          key={runner.id}
          scope={scope}
          runner={runner}
          onUpgrade={onUpgrade}
          onCommandSettled={onCommandSettled}
        />
      )}
    </Modal>
  );
};

const RunnerDiskDialogBody = ({
  scope,
  runner,
  onUpgrade,
  onCommandSettled,
}: {
  scope: RunnerDiskScope;
  runner: RunnerDiskDialogRunner;
  onUpgrade?: (() => void) | undefined;
  onCommandSettled?: ((command: RunnerDiskCommand) => void) | undefined;
}) => {
  const { t } = useTranslation("runnerDisk");
  const failureText = useFailureText();
  const query = useRunnerDisk(scope, runner.id, { onCommandSettled });
  const refresh = useRefreshRunnerDisk(scope, runner.id);
  const clean = useStartRunnerDiskCleanup(scope, runner.id);
  const cancel = useCancelRunnerDiskCleanup(scope, runner.id);
  const setAuto = useSetRunnerDiskAuto(runner.id);
  const [failure, setFailure] = useState<string | null>(null);
  const onError = (error: unknown) => {
    setFailure(failureText(error));
    // Отказ по состоянию (раннер ушёл, уже чистится): вид устарел, перечитать.
    void query.refetch();
  };

  if (!query.data) {
    if (query.isError) {
      const notFound =
        query.error instanceof ApiError && query.error.status === 404;
      return (
        <ErrorState
          compact
          title={notFound ? t("notFound") : t("loadFailed")}
          onRetry={
            notFound
              ? undefined
              : () => {
                  void query.refetch();
                }
          }
          retrying={query.isFetching}
          testId="runner-disk-error"
        />
      );
    }
    return <TableSkeleton rows={5} columns={2} testId="runner-disk-loading" />;
  }

  return (
    <RunnerDiskPanel
      view={query.data}
      runnerName={runner.name}
      runnerVersion={runner.version ?? null}
      onUpgrade={onUpgrade}
      error={failure}
      pending={{
        refresh: refresh.isPending,
        clean: clean.isPending,
        cancel: cancel.isPending,
        auto: setAuto.isPending,
      }}
      onRefresh={() => {
        setFailure(null);
        refresh.mutate(undefined, { onError });
      }}
      onClean={(request) => {
        setFailure(null);
        clean.mutate(request, { onError });
      }}
      onCancel={(commandId) => {
        setFailure(null);
        cancel.mutate(commandId, { onError });
      }}
      onSaveAuto={
        scope === "admin"
          ? (request) => {
              setFailure(null);
              setAuto.mutate(request, { onError });
            }
          : undefined
      }
    />
  );
};

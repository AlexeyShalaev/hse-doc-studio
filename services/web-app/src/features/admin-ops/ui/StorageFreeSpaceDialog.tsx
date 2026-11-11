import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Modal } from "@shared/ui";
import type { LifecycleSweep } from "@entities/session";
import {
  useCancelSweep,
  useStartSweep,
  useSweepPreview,
} from "../api/lifecycleQueries";
import {
  FreeSpacePanel,
  type FreeSpacePanelProps,
  type FreeSpacePreviewState,
} from "./StorageFreeSpace";

// Окно «Освободить место» (docs/design/storage-cleanup.md, 4.3): предпросмотр считается по
// открытию, подтверждение запускает прогон на сервере, дальше на месте подтверждения ход и итог.
// Окно можно закрыть: прогон идёт на сервере, ход виден в плашке под шапкой.

export type FreeSpaceMode = FreeSpacePanelProps["mode"];

/** Текст отказа: сообщение каталога ошибок (errors:code.*), иначе общий текст админки. */
const useFailureText = () => {
  const { t, i18n } = useTranslation("adminStorage");
  return (error: unknown): string => {
    const code = failureCode(error);
    if (code === "network") return t("adminOps:failure.network");
    const key = `errors:code.${code}`;
    return i18n.exists(key) ? t(key) : t("adminOps:failure.unknown");
  };
};

export type StorageFreeSpaceDialogProps = {
  open: boolean;
  /** С чего начать: предпросмотр или ход и итог прогона (идёт или открыт из плашки). */
  mode: FreeSpaceMode;
  /** Идущий или последний прогон из `useLifecycleSweep` страницы. */
  sweep: LifecycleSweep | null;
  now: number;
  onClose: () => void;
  /** Отказ по состоянию (уже идёт другой прогон): перечитать прогон. */
  onSweepStale?: () => void;
};

export const StorageFreeSpaceDialog = ({
  open,
  mode,
  sweep,
  now,
  onClose,
  onSweepStale,
}: StorageFreeSpaceDialogProps) => {
  const { t } = useTranslation("adminStorage");
  // Каждое открытие начинается заново: свой режим, свежий предпросмотр, без старых отказов.
  const [session, setSession] = useState({ open, count: 0, mode });
  if (session.open !== open) {
    setSession({
      open,
      count: open ? session.count + 1 : session.count,
      mode: open ? mode : session.mode,
    });
  }
  const current = session.open === open ? session.mode : mode;
  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      width={640}
      title={
        current === "preview"
          ? t("storage.free.confirm.title")
          : t("storage.free.title")
      }
    >
      {open && (
        <FreeSpaceDialogBody
          key={session.count}
          mode={current}
          onModeChange={(next) => {
            setSession((s) => ({ ...s, mode: next }));
          }}
          sweep={sweep}
          now={now}
          onClose={onClose}
          onSweepStale={onSweepStale}
        />
      )}
    </Modal>
  );
};

const FreeSpaceDialogBody = ({
  mode,
  onModeChange,
  sweep,
  now,
  onClose,
  onSweepStale,
}: {
  mode: FreeSpaceMode;
  onModeChange: (mode: FreeSpaceMode) => void;
  sweep: LifecycleSweep | null;
  now: number;
  onClose: () => void;
  onSweepStale?: (() => void) | undefined;
}) => {
  const failureText = useFailureText();
  const [failure, setFailure] = useState<string | null>(null);
  const preview = useSweepPreview({ enabled: mode === "preview" });
  const start = useStartSweep();
  const cancel = useCancelSweep();

  const previewState: FreeSpacePreviewState = preview.data
    ? { status: "ready", preview: preview.data }
    : preview.isError
      ? {
          status: "error",
          onRetry: () => {
            void preview.refetch();
          },
        }
      : { status: "loading" };

  return (
    <FreeSpacePanel
      mode={mode}
      preview={previewState}
      sweep={sweep}
      now={now}
      error={failure}
      starting={start.isPending}
      stopping={cancel.isPending || sweep?.status === "cancelling"}
      onClose={onClose}
      onConfirm={() => {
        setFailure(null);
        start.mutate(undefined, {
          onSuccess: () => {
            onModeChange("sweep");
          },
          onError: (error) => {
            setFailure(failureText(error));
            // Прогон уже идёт (запустил другой админ): показать его ход.
            if (failureCode(error) === "lifecycle_sweep_busy") {
              onModeChange("sweep");
              onSweepStale?.();
            }
          },
        });
      }}
      onStop={(id) => {
        setFailure(null);
        cancel.mutate(id, {
          onError: (error) => {
            setFailure(failureText(error));
            onSweepStale?.();
          },
        });
      }}
    />
  );
};

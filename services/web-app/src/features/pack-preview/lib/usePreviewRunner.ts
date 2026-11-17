import { useCallback, useState } from "react";
import {
  useCancelPackPreview,
  usePackPreviewBuild,
  useStartPackPreview,
  type PackPreviewBuild,
  type PackVersionRef,
  type StartPackPreviewRequest,
} from "@entities/pack-studio";

// Сборка предпросмотра как управляемое действие (срез F12): запуск, опрос, отмена и память о том,
// для какого запроса сборка стартовала. Запуск и опрос те же хуки сущности, что у вкладки
// «Предпросмотр» в «Файлах»; здесь только то, что нужно экрану с автосборкой. Новый запуск прежнюю
// сборку не трогает: сервер сам отменяет сборку того же слота (человек, версия, документ, вариант).

export type PreviewRunnerSeed = {
  buildId: string;
  /** Ключ запроса, для которого сборка стартовала. */
  key: string;
};

export type PreviewRunner = {
  /** Сборка, которую показываем; опрашивается, пока в очереди или идёт. */
  build: PackPreviewBuild | undefined;
  /** Опрос сборки не удался (сеть, 404 после очистки). */
  buildError: unknown;
  buildId: string | null;
  /** Ключ запроса, для которого стартовала показанная сборка. */
  builtKey: string | null;
  /** Ключ последнего запуска, в том числе неудачного: по нему автосборка не повторяет себя. */
  attemptedKey: string | null;
  /** Сколько запусков было: меняется с каждым, в том числе неудачным. */
  attempts: number;
  /** Запрос на запуск ушёл, сборки ещё нет. */
  starting: boolean;
  startError: unknown;
  /** Сборка в очереди или идёт. */
  running: boolean;
  start: (body: StartPackPreviewRequest, key: string) => void;
  cancel: () => void;
  cancelling: boolean;
  cancelError: unknown;
};

export const usePreviewRunner = (
  workspaceId: string,
  versionRef: PackVersionRef,
  seed?: PreviewRunnerSeed | null,
): PreviewRunner => {
  const [current, setCurrent] = useState<{
    id: string | null;
    key: string | null;
  }>({ id: seed?.buildId ?? null, key: seed?.key ?? null });
  const [attemptedKey, setAttemptedKey] = useState<string | null>(
    seed?.key ?? null,
  );
  const [attempts, setAttempts] = useState(0);
  const startMutation = useStartPackPreview(workspaceId);
  const cancelMutation = useCancelPackPreview(workspaceId);
  const build = usePackPreviewBuild(workspaceId, current.id);
  const { mutate: startBuild } = startMutation;
  const { mutate: cancelBuild } = cancelMutation;

  const start = useCallback(
    (body: StartPackPreviewRequest, key: string) => {
      setAttemptedKey(key);
      setAttempts((n) => n + 1);
      // Колбэк последнего запуска: ответ прежнего запуска наблюдатель отбрасывает сам.
      startBuild(
        { ref: versionRef, body },
        {
          onSuccess: (builds) => {
            const first = builds[0];
            if (first) setCurrent({ id: first.id, key });
          },
        },
      );
    },
    [startBuild, versionRef],
  );

  const cancel = useCallback(() => {
    if (current.id !== null) cancelBuild(current.id);
  }, [cancelBuild, current.id]);

  return {
    build: build.data,
    buildError: build.error,
    buildId: current.id,
    builtKey: current.key,
    attemptedKey,
    attempts,
    starting: startMutation.isPending,
    startError: startMutation.error,
    running:
      build.data?.status === "queued" || build.data?.status === "running",
    start,
    cancel,
    cancelling: cancelMutation.isPending,
    cancelError: cancelMutation.error,
  };
};

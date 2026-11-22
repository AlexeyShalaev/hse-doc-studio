import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router";
import { PACK_STUDIO_PATH } from "@entities/pack-studio";
import { reportIfChunkError } from "@shared/lib";
import { loadPackSpaceNamespace } from "@shared/lib/i18n/packSpaceNamespace";
import { ErrorState, Spinner } from "@shared/ui";
import { SpaceEntry } from "./SpaceEntry";
import { SpaceRoute } from "./SpaceRoute";

/** Словарь нового интерфейса до первого кадра: ключи не мигают, провал загрузки даёт повтор. */
const WithSpaceLocale = ({ children }: { children: React.ReactNode }) => {
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    loadPackSpaceNamespace().then(
      () => {
        if (live) setState("ready");
      },
      (error: unknown) => {
        reportIfChunkError(error);
        if (live) setState("failed");
      },
    );
    return () => {
      live = false;
    };
  }, [attempt]);
  if (state === "loading") {
    return (
      <div className="ps-page flex justify-center">
        <Spinner size="lg" />
      </div>
    );
  }
  if (state === "failed") {
    return (
      <ErrorState
        onRetry={() => {
          setState("loading");
          setAttempt((n) => n + 1);
        }}
      />
    );
  }
  return <>{children}</>;
};

/**
 * Маршруты пространства, всё под `/pack-studio/w/:workspaceId/`.
 * Таблица адресов: docs/design/pack-studio-ux.md, раздел 4.2. Свой чанк и свой словарь.
 */
export const SpaceApp = () => (
  <WithSpaceLocale>
    <Routes>
      <Route index element={<SpaceEntry />} />
      <Route path="result/*" element={<SpaceEntry />} />
      <Route path="t/:pack/:template/:version/:tab?" element={<SpaceRoute />} />
      <Route path="*" element={<Navigate to={PACK_STUDIO_PATH} replace />} />
    </Routes>
  </WithSpaceLocale>
);

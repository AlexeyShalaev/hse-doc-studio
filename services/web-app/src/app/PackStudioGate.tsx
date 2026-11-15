import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useCapabilities } from "@entities/session";
import { ErrorPage } from "@pages/ErrorPage";
import { reportIfChunkError } from "@shared/lib";
import { loadPackStudioNamespace } from "@shared/lib/i18n/packStudioNamespace";
import { ErrorState, Spinner } from "@shared/ui";

// Чанк Студии шаблонов запрашивается только когда охранник пустил: без
// capabilities.pack_studio import() не вызывается, а ссылка на чанк есть только здесь.
const PackStudioApp = lazy(() =>
  import("@pages/PackStudioPage").then((m) => ({ default: m.PackStudioApp })),
);

const Loading = () => (
  <div
    className="flex flex-1 items-center justify-center"
    data-testid="pack-studio-gate-loading"
  >
    <Spinner size="lg" />
  </div>
);

/** Словарь раздела до первого кадра: ключи не мигают; провал загрузки даёт повтор. */
const WithLocale = ({ children }: { children: React.ReactNode }) => {
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    loadPackStudioNamespace().then(
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
  if (state === "loading") return <Loading />;
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
 * Охранник /pack-studio/* (template-studio.md, раздел 3): решает
 * capabilities.pack_studio из bootstrap (раздел включён и есть право «Автор
 * шаблонов»). Без возможности та же страница «не найдено», что на
 * несуществующем адресе (сервер так же отвечает 404), и код раздела не скачивается.
 */
export const PackStudioGate = () => {
  const { t } = useTranslation("uiPrimitives");
  const { isLoading, has } = useCapabilities();
  if (isLoading) return <Loading />;
  if (!has("pack_studio")) {
    return <ErrorPage status={404} message={t("router.notFoundMessage")} />;
  }
  return (
    <WithLocale>
      <Suspense fallback={<Loading />}>
        <PackStudioApp />
      </Suspense>
    </WithLocale>
  );
};

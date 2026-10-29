import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { useCapabilities } from "@entities/session";
import { ErrorPage } from "@pages/ErrorPage";
import { Spinner } from "@shared/ui";

// Чанк админки запрашивается только когда охранник пустил: у не-админа
// import() не вызывается вовсе, а ссылка на чанк есть только в этом файле.
const AdminApp = lazy(() =>
  import("@pages/AdminPage").then((m) => ({ default: m.AdminApp })),
);

const Loading = () => (
  <div
    className="flex flex-1 items-center justify-center"
    data-testid="admin-gate-loading"
  >
    <Spinner size="lg" />
  </div>
);

/**
 * Охранник маршрутов /admin/*. Решает capabilities.admin из bootstrap, а не
 * режим: не-админ видит ту же страницу «не найдено», что и на несуществующем
 * адресе (сервер так же отвечает 404), и не скачивает код админки.
 */
export const AdminGate = () => {
  const { t } = useTranslation("uiPrimitives");
  const { isLoading, has } = useCapabilities();
  if (isLoading) return <Loading />;
  if (!has("admin")) {
    return <ErrorPage status={404} message={t("router.notFoundMessage")} />;
  }
  return (
    <Suspense fallback={<Loading />}>
      <AdminApp />
    </Suspense>
  );
};

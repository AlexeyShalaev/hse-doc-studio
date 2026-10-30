import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router";
import { loadAdminLocales } from "./adminLocales";
import { AdminChunkError } from "./AdminChunkError";
import { AdminChunkLoading } from "./AdminChunkLoading";
import { AdminLayout } from "./AdminLayout";
import { AdminOverview } from "./AdminSections";

// Настройки входа тяжелее остальной оболочки: свой чанк, чтобы admin-*.js оставался лёгким.
const AdminSettingsPage = lazy(() =>
  import("./AdminSettingsPage").then((m) => ({ default: m.AdminSettingsPage })),
);

// Организации, участники и группы тоже в своём чанке.
const AdminOrgsPage = lazy(() =>
  import("./AdminOrgsPage").then((m) => ({ default: m.AdminOrgsPage })),
);

// Раннеры, очередь, квоты, сервисы и хранилище: один общий lazy-чанк.
const AdminOpsPage = lazy(() =>
  import("./AdminOpsPage").then((m) => ({ default: m.AdminOpsPage })),
);

// Пользователи, приглашения, одобрения и журнал аудита.
const AdminPeoplePage = lazy(() =>
  import("./AdminPeoplePage").then((m) => ({ default: m.AdminPeoplePage })),
);

// Настройки установки: название и сборка, ключи подписи, общие ИИ-провайдеры.
const AdminInstallPage = lazy(() =>
  import("./AdminInstallPage").then((m) => ({ default: m.AdminInstallPage })),
);

const INSTALL_PARTS = ["instance", "signing", "ai-providers"] as const;

const PEOPLE_PARTS = ["users", "audit"] as const;

const OPS_PARTS = ["runners", "quotas", "services", "storage"] as const;

// Метка для verify:admin-chunk: этой строки не должно быть ни в entry, ни в
// auth-чанках. Она лежит в коде чанка, а не в словарях.
export const ADMIN_CHUNK_MARKER = "hse-admin-chunk-marker";

/** Короткий адрес организации /admin/org/:slug ведёт на её страницу. */
const OrgRedirect = () => {
  const { slug = "" } = useParams<{ slug: string }>();
  return <Navigate to={`/admin/orgs/${encodeURIComponent(slug)}`} replace />;
};

/**
 * Корень админки (маршрут /admin/*). Единственная точка входа lazy-чанка:
 * подключает словари admin/ и рисует разделы. Права проверяет охранник
 * снаружи, чанк запрашивается только после него.
 */
export const AdminApp = () => {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    loadAdminLocales().then(
      () => {
        if (live) setReady(true);
      },
      () => {
        if (live) setFailed(true);
      },
    );
    return () => {
      live = false;
    };
  }, [attempt]);

  if (failed) {
    return (
      <AdminChunkError
        onRetry={() => {
          setFailed(false);
          setAttempt((n) => n + 1);
        }}
      />
    );
  }
  if (!ready) {
    return <AdminChunkLoading size="lg" testId={ADMIN_CHUNK_MARKER} />;
  }
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<AdminOverview />} />
        <Route
          path="settings"
          element={
            <Suspense fallback={<AdminChunkLoading />}>
              <AdminSettingsPage />
            </Suspense>
          }
        />
        <Route
          path="orgs/*"
          element={
            <Suspense fallback={<AdminChunkLoading />}>
              <AdminOrgsPage />
            </Suspense>
          }
        />
        {OPS_PARTS.map((part) => (
          <Route
            key={part}
            path={part}
            element={
              <Suspense fallback={<AdminChunkLoading />}>
                <AdminOpsPage part={part} />
              </Suspense>
            }
          />
        ))}
        {PEOPLE_PARTS.map((part) => (
          <Route
            key={part}
            path={part}
            element={
              <Suspense fallback={<AdminChunkLoading />}>
                <AdminPeoplePage part={part} />
              </Suspense>
            }
          />
        ))}
        {INSTALL_PARTS.map((part) => (
          <Route
            key={part}
            path={part}
            element={
              <Suspense fallback={<AdminChunkLoading />}>
                <AdminInstallPage part={part} />
              </Suspense>
            }
          />
        ))}
        <Route path="org/:slug" element={<OrgRedirect />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Route>
    </Routes>
  );
};

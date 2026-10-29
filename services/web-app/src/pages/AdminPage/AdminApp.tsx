import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router";
import { Spinner } from "@shared/ui";
import { loadAdminLocales } from "./adminLocales";
import { AdminLayout } from "./AdminLayout";
import { AdminOverview, AdminSectionSoon } from "./AdminSections";

// Настройки входа тяжелее остальной оболочки: свой чанк, чтобы admin-*.js оставался лёгким.
const AdminSettingsPage = lazy(() =>
  import("./AdminSettingsPage").then((m) => ({ default: m.AdminSettingsPage })),
);

// Организации, участники и группы тоже в своём чанке.
const AdminOrgsPage = lazy(() =>
  import("./AdminOrgsPage").then((m) => ({ default: m.AdminOrgsPage })),
);

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

  useEffect(() => {
    let live = true;
    void loadAdminLocales().then(() => {
      if (live) setReady(true);
    });
    return () => {
      live = false;
    };
  }, []);

  if (!ready) {
    return (
      <div
        className="flex flex-1 items-center justify-center"
        data-testid={ADMIN_CHUNK_MARKER}
        role="status"
        aria-label="admin"
      >
        <Spinner size="lg" />
      </div>
    );
  }
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<AdminOverview />} />
        <Route
          path="settings"
          element={
            <Suspense
              fallback={
                <div className="flex items-center justify-center" role="status">
                  <Spinner size="md" />
                </div>
              }
            >
              <AdminSettingsPage />
            </Suspense>
          }
        />
        <Route
          path="orgs/*"
          element={
            <Suspense
              fallback={
                <div className="flex items-center justify-center" role="status">
                  <Spinner size="md" />
                </div>
              }
            >
              <AdminOrgsPage />
            </Suspense>
          }
        />
        <Route path="org/:slug" element={<OrgRedirect />} />
        <Route path=":section" element={<AdminSectionSoon />} />
      </Route>
    </Routes>
  );
};

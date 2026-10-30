import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import {
  Navigate,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from "react-router";
import { PageContainer, Spinner, type PageWidth } from "@shared/ui";
import { loadAdminLocales } from "./adminLocales";
import { AdminLayout } from "./AdminLayout";

// Сводка тянет запросы всех разделов: свой чанк, чтобы admin-*.js оставался лёгким.
const AdminOverview = lazy(() =>
  import("./AdminSections").then((m) => ({ default: m.AdminOverview })),
);

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

// Ширина содержимого по разделу: формы настроек узкие, таблицы и сводки широкие.
const INSTALL_PARTS = [
  ["instance", "narrow"],
  ["signing", "narrow"],
  ["ai-providers", "narrow"],
] as const;

const PEOPLE_PARTS = [
  ["users", "wide"],
  ["audit", "wide"],
] as const;

const OPS_PARTS = [
  ["runners", "wide"],
  ["quotas", "narrow"],
  ["services", "wide"],
  ["storage", "wide"],
] as const;

// Метка для verify:admin-chunk: этой строки не должно быть ни в entry, ни в
// auth-чанках. Она лежит в коде чанка, а не в словарях.
export const ADMIN_CHUNK_MARKER = "hse-admin-chunk-marker";

/** Короткий адрес организации /admin/org/:slug ведёт на её страницу. */
const OrgRedirect = () => {
  const { slug = "" } = useParams<{ slug: string }>();
  return <Navigate to={`/admin/orgs/${encodeURIComponent(slug)}`} replace />;
};

const Loading = () => (
  <div
    className="flex flex-1 items-center justify-center"
    role="status"
    style={{ minHeight: 240 }}
  >
    <Spinner size="md" />
  </div>
);

/** Раздел в общих полях страницы; пока чанк грузится, на его месте крутилка. */
const Page = ({
  width = "wide",
  children,
}: {
  width?: PageWidth;
  children: ReactNode;
}) => (
  <PageContainer width={width}>
    <Suspense fallback={<Loading />}>{children}</Suspense>
  </PageContainer>
);

/** /admin/users?tab=invitations открывает нужную вкладку (ссылки со сводки). */
const PeopleRoute = ({ part }: { part: "users" | "audit" }) => {
  const [params] = useSearchParams();
  const tab = params.get("tab");
  return (
    <AdminPeoplePage
      part={part}
      initialTab={
        tab === "invitations" || tab === "approvals" ? tab : undefined
      }
    />
  );
};

/** /admin/runners?create=token сразу открывает создание токена регистрации. */
const OpsRoute = ({ part }: { part: (typeof OPS_PARTS)[number][0] }) => {
  const [params] = useSearchParams();
  return (
    <AdminOpsPage
      part={part}
      initialCreateToken={params.get("create") === "token"}
    />
  );
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
        <Route
          index
          element={
            <Suspense fallback={<Loading />}>
              <AdminOverview />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Page width="narrow">
              <AdminSettingsPage />
            </Page>
          }
        />
        <Route
          path="orgs/*"
          element={
            <Page>
              <AdminOrgsPage />
            </Page>
          }
        />
        {OPS_PARTS.map(([part, width]) => (
          <Route
            key={part}
            path={part}
            element={
              <Page width={width}>
                <OpsRoute part={part} />
              </Page>
            }
          />
        ))}
        {PEOPLE_PARTS.map(([part, width]) => (
          <Route
            key={part}
            path={part}
            element={
              <Page width={width}>
                <PeopleRoute part={part} />
              </Page>
            }
          />
        ))}
        {INSTALL_PARTS.map(([part, width]) => (
          <Route
            key={part}
            path={part}
            element={
              <Page width={width}>
                <AdminInstallPage part={part} />
              </Page>
            }
          />
        ))}
        <Route path="org/:slug" element={<OrgRedirect />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Route>
    </Routes>
  );
};

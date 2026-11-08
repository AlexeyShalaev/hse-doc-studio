import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import {
  Navigate,
  Route,
  Routes,
  useParams,
  useSearchParams,
} from "react-router";
import {
  loadAdminNamespaces,
  reportIfChunkError,
  type AdminNamespace,
} from "@shared/lib";
import { PageContainer, type PageWidth } from "@shared/ui";
import { AdminChunkError } from "./AdminChunkError";
import { AdminChunkLoading } from "./AdminChunkLoading";
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

// Бэкапы сервера: назначения, расписание, история.
const AdminBackupsPage = lazy(() =>
  import("@features/admin-backups").then((m) => ({ default: m.BackupsPage })),
);

// Самодиагностика: проверки состояния, подсказки и пороги.
const AdminDiagnosticsPage = lazy(() =>
  import("@features/admin-diagnostics").then((m) => ({
    default: m.DiagnosticsPage,
  })),
);

// Автообновление сервера: версия, политика и окно, история, откат.
const AdminUpdatesPage = lazy(() =>
  import("@features/admin-updates").then((m) => ({ default: m.UpdatesPage })),
);

// Серверы ИИ-моделей: установка Ollama, vLLM и SGLang.
const AdminModelServersPage = lazy(() =>
  import("@features/admin-model-servers").then((m) => ({
    default: m.ModelServersPage,
  })),
);

// MCP-сервер установки: включение, инструменты, журнал вызовов.
const AdminMcpPage = lazy(() =>
  import("@features/mcp-server").then((m) => ({ default: m.AdminMcpPage })),
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
  ["data", "wide"],
] as const;

// Метка для verify:admin-chunk: этой строки не должно быть ни в entry, ни в
// auth-чанках. Она лежит в коде чанка, а не в словарях.
export const ADMIN_CHUNK_MARKER = "hse-admin-chunk-marker";

/** Короткий адрес организации /admin/org/:slug ведёт на её страницу. */
const OrgRedirect = () => {
  const { slug = "" } = useParams<{ slug: string }>();
  return <Navigate to={`/admin/orgs/${encodeURIComponent(slug)}`} replace />;
};

/** Ожидание чанка раздела: та же крутилка, что у корня админки, по центру поля страницы. */
const Loading = () => (
  <div
    className="flex flex-1 flex-col justify-center"
    style={{ minHeight: "15rem" }}
  >
    <AdminChunkLoading />
  </div>
);

/**
 * Показывает раздел, когда подключены его словари. Пока они грузятся, на месте
 * раздела крутилка, поэтому ключи не мигают; провал загрузки даёт ошибку с
 * повтором. Повторное открытие раздела идёт мгновенно (общий кэш загрузчика).
 */
const WithLocales = ({
  ns,
  children,
}: {
  ns: readonly AdminNamespace[];
  children: ReactNode;
}) => {
  const key = ns.join(",");
  const [attempt, setAttempt] = useState(0);
  const [done, setDone] = useState<{
    token: string;
    ok: boolean;
  } | null>(null);
  const token = `${key}#${attempt}`;
  useEffect(() => {
    let live = true;
    loadAdminNamespaces(key.split(",") as AdminNamespace[]).then(
      () => {
        if (live) setDone({ token, ok: true });
      },
      (error: unknown) => {
        reportIfChunkError(error);
        if (live) setDone({ token, ok: false });
      },
    );
    return () => {
      live = false;
    };
  }, [key, token]);
  if (done?.token !== token) return <Loading />;
  if (!done.ok) {
    return <AdminChunkError onRetry={() => setAttempt((n) => n + 1)} />;
  }
  return <>{children}</>;
};

/** Раздел в общих полях страницы; пока чанк грузится, на его месте крутилка. */
const Page = ({
  width = "wide",
  ns,
  children,
}: {
  width?: PageWidth;
  /** Словари раздела (admin/<name>.json): грузятся при первом открытии. */
  ns: readonly AdminNamespace[];
  children: ReactNode;
}) => (
  <PageContainer width={width}>
    <Suspense fallback={<Loading />}>
      <WithLocales ns={ns}>{children}</WithLocales>
    </Suspense>
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
 * подключает словарь оболочки (admin/shell.json) и рисует разделы; словари
 * разделов грузит Page при первом открытии. Права проверяет охранник
 * снаружи, чанк запрашивается только после него.
 */
export const AdminApp = () => {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    loadAdminNamespaces(["shell"]).then(
      () => {
        if (live) setReady(true);
      },
      (error: unknown) => {
        reportIfChunkError(error);
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
        <Route
          index
          element={
            <Suspense fallback={<Loading />}>
              <WithLocales ns={["audit"]}>
                <AdminOverview />
              </WithLocales>
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Page width="narrow" ns={["settings"]}>
              <AdminSettingsPage />
            </Page>
          }
        />
        <Route
          path="orgs/*"
          element={
            <Page ns={["orgs"]}>
              <AdminOrgsPage />
            </Page>
          }
        />
        {OPS_PARTS.map(([part, width]) => (
          <Route
            key={part}
            path={part}
            element={
              <Page
                width={width}
                ns={
                  part === "runners"
                    ? ["ops", part, "runnerInstall", "runnerIsolation"]
                    : ["ops", part]
                }
              >
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
              <Page
                width={width}
                ns={part === "users" ? ["users", "orgs"] : ["audit"]}
              >
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
              <Page width={width} ns={["install"]}>
                <AdminInstallPage part={part} />
              </Page>
            }
          />
        ))}
        <Route
          path="backups"
          element={
            <Page width="wide" ns={["backups", "diagnostics"]}>
              <AdminBackupsPage />
            </Page>
          }
        />
        <Route
          path="updates"
          element={
            <Page width="wide" ns={["updates", "diagnostics"]}>
              <AdminUpdatesPage />
            </Page>
          }
        />
        <Route
          path="diagnostics"
          element={
            <Page width="wide" ns={["diagnostics"]}>
              <AdminDiagnosticsPage />
            </Page>
          }
        />
        <Route
          path="model-servers"
          element={
            <Page width="wide" ns={["modelServers"]}>
              <AdminModelServersPage />
            </Page>
          }
        />
        <Route
          path="mcp"
          element={
            <Page width="narrow" ns={["mcp"]}>
              <AdminMcpPage />
            </Page>
          }
        />
        <Route path="org/:slug" element={<OrgRedirect />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Route>
    </Routes>
  );
};

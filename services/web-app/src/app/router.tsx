import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { i18n } from "@shared/lib";
import { ErrorPage } from "@pages/ErrorPage";
import { SettingsPage } from "@pages/SettingsPage";
import { WelcomePage } from "@pages/WelcomePage";
import { WizardPage } from "@pages/WizardPage";
import { WorkspacePage } from "@pages/WorkspacePage";
import { ProjectIndexRedirect } from "./ProjectIndexRedirect";
import { RootLayout } from "./RootLayout";

// Галерея состояний синхронизации: страница разработчика. Условие вычисляется
// при сборке, поэтому в рабочем бандле нет ни страницы, ни ссылки на неё.
const devRoutes: RouteObject[] = import.meta.env.DEV
  ? [
      {
        path: "/dev/sync-states",
        lazy: async () => {
          const [{ DevSyncStatesPage }, demo] = await Promise.all([
            import("@pages/DevSyncStates"),
            import("./demo"),
          ]);
          // Живым записям нужен демо-транспорт, даже если приложение запущено без него.
          demo.installGitDemo();
          const gallery = { activate: demo.activateDemoScenario };
          return {
            Component: () => <DevSyncStatesPage demo={gallery} />,
          };
        },
      },
      {
        path: "/dev/server-screens",
        lazy: async () => {
          const [{ DevServerScreensPage }, demo] = await Promise.all([
            import("@pages/DevServerScreens"),
            import("./demo"),
          ]);
          // Серверные записи ходят в демо-мир, даже если приложение запущено без него.
          demo.installServerDemo();
          const gallery = { activate: demo.activateServerScenario };
          return {
            Component: () => <DevServerScreensPage demo={gallery} />,
          };
        },
      },
    ]
  : [];

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      {
        path: "/",
        element: <WelcomePage />,
      },
      {
        path: "/wizard",
        element: <WizardPage />,
      },
      {
        path: "/settings",
        element: <Navigate to="/settings/appearance" replace />,
      },
      {
        path: "/settings/:section",
        element: <SettingsPage />,
      },
      {
        path: "/projects/:projectId",
        element: <ProjectIndexRedirect />,
      },
      // Инструменты выехали из слота :docId в собственные маршруты. Адрес
      // документа НЕ ТРОГАЕМ — на него ссылаются RecentActivity, палитра
      // команд, ссылки агента doc:<id> и закладки пользователей.
      {
        path: "/projects/:projectId/documents",
        element: <WorkspacePage canvas="overview" />,
      },
      {
        path: "/projects/:projectId/documents/:docId",
        element: <WorkspacePage canvas="document" />,
      },
      {
        path: "/projects/:projectId/files",
        element: <WorkspacePage canvas="files" />,
      },
      {
        path: "/projects/:projectId/versions",
        element: <WorkspacePage canvas="versions" />,
      },
      // Настройки проекта разложены по секциям, как и системные /settings/:section.
      // Голый адрес и незнакомая секция не редиректят, а показывают первую
      // секцию: подмена считается в самой странице, поэтому сохранённая ссылка
      // на «Метаданные» переживает загрузку каталога версии.
      {
        path: "/projects/:projectId/project-settings",
        element: <WorkspacePage canvas="project-settings" />,
      },
      {
        path: "/projects/:projectId/project-settings/:section",
        element: <WorkspacePage canvas="project-settings" />,
      },
      // Разбор конфликтов синхронизации: полноэкранная страница, как «Версии».
      {
        path: "/projects/:projectId/sync/conflicts",
        element: <WorkspacePage canvas="sync-conflicts" />,
      },
      {
        path: "/projects/:projectId/submit",
        element: <WorkspacePage canvas="submit-pack" />,
      },
      {
        path: "/projects/:projectId/submit/cp/:profileId",
        element: <WorkspacePage canvas="submit-checkpoint" />,
      },
      {
        path: "/projects/:projectId/submit/signatures",
        element: <WorkspacePage canvas="submit-signatures" />,
      },
      {
        path: "/projects/:projectId/submit/requirements",
        element: <WorkspacePage canvas="submit-requirements" />,
      },
      {
        path: "/projects/:projectId/submit/form/:formId",
        element: <WorkspacePage canvas="submit-form" />,
      },
      ...devRoutes,
      {
        path: "*",
        element: (
          <ErrorPage
            status={404}
            message={i18n.t("uiPrimitives:router.notFoundMessage")}
          />
        ),
      },
    ],
  },
]);

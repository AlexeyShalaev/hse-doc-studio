import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { i18n } from "@shared/lib";
import { AuthErrorPage } from "@pages/AuthErrorPage";
import { ErrorPage } from "@pages/ErrorPage";
import { FirstRunPage } from "@pages/FirstRunPage";
import { ForgotPage } from "@pages/ForgotPage";
import { InboxPage } from "@pages/InboxPage";
import { InvitePage } from "@pages/InvitePage";
import { LoginPage } from "@pages/LoginPage";
import { ProjectInvitePage } from "@pages/ProjectInvitePage";
import { RegisterPage } from "@pages/RegisterPage";
import { ResetPage } from "@pages/ResetPage";
import { RunnerPairPage } from "@pages/RunnerPairPage";
import { ShareLinkPage } from "@pages/ShareLinkPage";
import { GuestViewPage } from "@pages/GuestViewPage";
import { SettingsPage } from "@pages/SettingsPage";
import { VerifyPage } from "@pages/VerifyPage";
import { WelcomePage } from "@pages/WelcomePage";
import { WizardPage } from "@pages/WizardPage";
import { WorkspacePage } from "@pages/WorkspacePage";
import { AuthLayout } from "@widgets/AuthLayout";
import { AdminGate } from "./AdminGate";
import { ProjectAccessGate } from "./ProjectAccessGate";
import { HomeRoute } from "./HomeRoute";
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
          const [
            { DevServerScreensPage },
            { getProjectsGallery },
            { getRunnerPairGallery },
            { getShareLinkPageGallery },
            { getGuestViewGallery },
            demo,
          ] = await Promise.all([
            import("@pages/DevServerScreens"),
            import("@pages/WelcomePage"),
            import("@pages/RunnerPairPage"),
            import("@pages/ShareLinkPage"),
            import("@pages/GuestViewPage"),
            import("./demo"),
          ]);
          const extraSections = [
            {
              id: "projects",
              title: "Проекты и доступ",
              groups: getProjectsGallery(),
            },
            {
              id: "runner-pair",
              title: "Подтверждение сопряжения раннера",
              groups: getRunnerPairGallery(),
            },
            {
              id: "share-link-page",
              title: "Ссылка доступа и просмотр PDF",
              groups: [...getShareLinkPageGallery(), ...getGuestViewGallery()],
            },
          ];
          // Серверные записи ходят в демо-мир, даже если приложение запущено без него.
          demo.installServerDemo();
          const gallery = { activate: demo.activateServerScenario };
          return {
            Component: () => (
              <DevServerScreensPage
                demo={gallery}
                extraSections={extraSections}
              />
            ),
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
      // Экраны без сессии. В локальном режиме шлюз их не пропускает дальше
      // обычного приложения: они нужны серверному режиму.
      {
        element: <AuthLayout />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/register", element: <RegisterPage /> },
          { path: "/invite/:token", element: <InvitePage /> },
          { path: "/verify/:token", element: <VerifyPage /> },
          { path: "/forgot", element: <ForgotPage /> },
          { path: "/reset/:token", element: <ResetPage /> },
          { path: "/first-run", element: <FirstRunPage /> },
          { path: "/auth/error", element: <AuthErrorPage /> },
          // links: страница ссылки доступа (без входа, токен уходит из адреса после открытия).
          { path: "/s/:token", element: <ShareLinkPage /> },
          // invites: ссылка из письма-приглашения в проект (открывается и без входа).
          { path: "/project-invite/:token", element: <ProjectInvitePage /> },
        ],
      },
      {
        path: "/",
        // links: гость по ссылке видит свои проекты по ссылкам вместо списка проектов.
        element: <HomeRoute welcome={<WelcomePage />} />,
      },
      // invites: «Входящие» вошедшего.
      {
        path: "/inbox",
        element: <InboxPage />,
      },
      {
        path: "/wizard",
        element: <WizardPage />,
      },
      {
        path: "/settings",
        element: <Navigate to="/settings/appearance" replace />,
      },
      // Подтверждение кода из Студии: своя страница, а не раздел настроек.
      // Гостя шлюз отправит на вход и вернёт сюда с тем же кодом.
      {
        path: "/settings/runners/pair",
        element: <RunnerPairPage />,
      },
      {
        path: "/settings/:section",
        element: <SettingsPage />,
      },
      // Проекты за охранником: 404 сервера на чужой проект даёт одну страницу
      // «не найден или нет доступа», а не пустую рабочую область.
      {
        element: <ProjectAccessGate />,
        children: [
          {
            path: "/projects/:projectId",
            element: <ProjectIndexRedirect />,
          },
          // Инструменты выехали из слота :docId в собственные маршруты. Адрес
          // документа НЕ ТРОГАЕМ — на него ссылаются RecentActivity, палитра
          // команд, ссылки агента doc:<id> и закладки пользователей.
          // links: просмотр PDF для читателя без исходников (гость или вошедший по ссылке).
          {
            path: "/projects/:projectId/view",
            element: <GuestViewPage />,
          },
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
        ],
      },
      // Админка: отдельный lazy-чанк за охранником по capabilities.admin.
      { path: "/admin/*", element: <AdminGate /> },
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

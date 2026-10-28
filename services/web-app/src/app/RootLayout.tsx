import { Suspense, lazy } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { SystemChatPanel } from "@features/agent-chat";
import { ServerUnavailable, useBootstrap } from "@entities/session";
import { useSetupStatus } from "@entities/setup";
import { SetupPage } from "@pages/SetupPage";
import { CommandPalette } from "@widgets/CommandPalette";
import { DockerStatusBanner } from "@widgets/DockerStatusBanner";
import { StartupChecks } from "@widgets/StartupChecks";
import { useWorkspaceStore } from "@shared/lib";
import { Spinner } from "@shared/ui";
import { Toaster } from "@shared/ui/Toaster";
import { isPublicPath, resolveGateRedirect } from "./gateRedirect";

// Переключатель демо-сценариев: только в сборке с VITE_GIT_DEMO=1. Условие
// вычисляется при сборке, и в обычном бандле этого кода и его чанка нет.
const DemoScenarioPicker =
  import.meta.env.VITE_GIT_DEMO === "1"
    ? lazy(() =>
        import("./demo").then((m) => ({ default: m.DemoScenarioPicker })),
      )
    : null;

// Переключатель сценариев серверного демо: так же, только при VITE_SERVER_DEMO=1.
const ServerDemoPicker =
  import.meta.env.VITE_SERVER_DEMO === "1"
    ? lazy(() =>
        import("./demo").then((m) => ({ default: m.ServerDemoPicker })),
      )
    : null;

// Routes that dock the one agent inside their own layout (between the title and
// status bars): Welcome, the project wizard, and any project workspace. On the
// remaining routes (settings, errors) it has no docked slot, so RootLayout
// renders it as the overlay drawer below instead.
const routeDocksAgent = (pathname: string): boolean =>
  pathname === "/" ||
  pathname.startsWith("/wizard") ||
  pathname.startsWith("/projects/");

export const RootLayout = () => {
  const location = useLocation();
  const systemChatOpen = useWorkspaceStore((state) => state.systemChatOpen);
  const setSystemChatOpen = useWorkspaceStore(
    (state) => state.setSystemChatOpen,
  );
  const agentDocked = routeDocksAgent(location.pathname);
  const bootstrap = useBootstrap();
  const session = bootstrap.data;
  // Ручки установки и Docker существуют только там, где есть docker_ui. Пока
  // bootstrap не пришёл, их не спрашиваем: аноним на сервере не должен получить
  // каскад 401 и 404 на старте.
  const hasDocker = session?.capabilities.docker_ui === true;
  const setup = useSetupStatus({ enabled: hasDocker });

  // Сначала узнаём, кто мы и в каком режиме: до ответа не показываем ни
  // приветствие, ни мастер, чтобы локальные кнопки не мигали и не пропадали.
  if (!session) {
    if (bootstrap.isError) {
      return (
        <div className="flex flex-col h-screen">
          <ServerUnavailable
            onRetry={() => {
              void bootstrap.refetch();
            }}
            retrying={bootstrap.isFetching}
          />
          <Toaster />
        </div>
      );
    }
    return (
      <div
        className="flex flex-col h-screen items-center justify-center"
        data-testid="server-gate-loading"
      >
        <Spinner size="lg" />
      </div>
    );
  }

  const redirect = resolveGateRedirect(session, location);
  if (redirect !== null) {
    return <Navigate to={redirect} replace />;
  }

  // Экраны без сессии (вход, регистрация, мастер): без титлбара, баннера Docker,
  // проверок запуска и агента, их рисует AuthLayout внутри Outlet.
  if (session.mode === "server" && isPublicPath(location.pathname)) {
    return (
      <div className="flex flex-col h-screen">
        <Outlet />
        <Toaster />
        {ServerDemoPicker && (
          <Suspense fallback={null}>
            <ServerDemoPicker />
          </Suspense>
        )}
      </div>
    );
  }

  // Пока установка не настроена, работать не с чем: файлы пользователя лежали
  // бы внутри контейнера и исчезли при первом же обновлении версии. Показываем
  // мастер ВМЕСТО приложения, а не поверх — не для строгости, а чтобы человек
  // не начал работу, которую потом потеряет.
  //
  // Ответа ещё нет (первый запрос) или ручка неизвестна (старый бэкенд без
  // перезапуска) — пропускаем дальше: запирать интерфейс на догадке нельзя.
  if (hasDocker && setup.data && !setup.data.is_ready) {
    return (
      <div className="flex flex-col h-screen">
        <SetupPage />
        <Toaster />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      {session.capabilities.docker_ui && <DockerStatusBanner />}
      {(session.capabilities.docker_ui || session.capabilities.self_update) && (
        <StartupChecks />
      )}
      <Outlet />
      <CommandPalette />
      <Toaster />
      {DemoScenarioPicker && (
        <Suspense fallback={null}>
          <DemoScenarioPicker />
        </Suspense>
      )}

      {ServerDemoPicker && (
        <Suspense fallback={null}>
          <ServerDemoPicker />
        </Suspense>
      )}

      {/* The one unified agent. On routes that dock it into their own layout
          (Welcome, wizard, project workspace) the panel pushes content between
          the title and status bars, so we skip this overlay there to avoid a
          double mount. Elsewhere (settings, errors) it appears as this drawer. */}
      {systemChatOpen && !agentDocked && (
        <div
          style={{
            position: "fixed",
            top: 0,
            right: 0,
            bottom: 0,
            zIndex: 50,
            display: "flex",
            boxShadow: "-8px 0 24px rgba(0,0,0,0.25)",
          }}
        >
          <SystemChatPanel
            width={400}
            onClose={() => {
              setSystemChatOpen(false);
            }}
          />
        </div>
      )}
    </div>
  );
};

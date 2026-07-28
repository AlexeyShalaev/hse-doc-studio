import { Outlet, useLocation } from "react-router";
import { SystemChatPanel } from "@features/agent-chat";
import { useSetupStatus } from "@entities/setup";
import { SetupPage } from "@pages/SetupPage";
import { CommandPalette } from "@widgets/CommandPalette";
import { DockerStatusBanner } from "@widgets/DockerStatusBanner";
import { StartupChecks } from "@widgets/StartupChecks";
import { useWorkspaceStore } from "@shared/lib";
import { Toaster } from "@shared/ui/Toaster";

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
  const setup = useSetupStatus();

  // Пока установка не настроена, работать не с чем: файлы пользователя лежали
  // бы внутри контейнера и исчезли при первом же обновлении версии. Показываем
  // мастер ВМЕСТО приложения, а не поверх — не для строгости, а чтобы человек
  // не начал работу, которую потом потеряет.
  //
  // Ответа ещё нет (первый запрос) или ручка неизвестна (старый бэкенд без
  // перезапуска) — пропускаем дальше: запирать интерфейс на догадке нельзя.
  if (setup.data && !setup.data.is_ready) {
    return (
      <div className="flex flex-col h-screen">
        <SetupPage />
        <Toaster />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      <DockerStatusBanner />
      <StartupChecks />
      <Outlet />
      <CommandPalette />
      <Toaster />

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

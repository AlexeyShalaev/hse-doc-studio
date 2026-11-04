import { useNavigate } from "react-router";
import { openHelp } from "@entities/help";
import { LOCAL_STUDIO_PATH } from "@entities/local-studio";
import { useUIStore, useWorkspaceStore } from "@shared/lib";
import { useBootstrap, useCapabilities } from "@entities/session";
import { useLogout } from "../model/useLogout";
import { AccountMenuView } from "./AccountMenuView";

/**
 * Меню аккаунта в заголовке. В локальном режиме пользователя нет, и меню не
 * рисуется вовсе: интерфейс остаётся прежним.
 */
export const AccountMenu = () => {
  const { data } = useBootstrap();
  const navigate = useNavigate();
  const { logout, pending } = useLogout();
  const { has } = useCapabilities();
  const toggleSystemChat = useWorkspaceStore((state) => state.toggleSystemChat);
  const togglePalette = useUIStore((state) => state.togglePaletteOpen);
  if (data?.mode !== "server" || data.user === null) return null;
  return (
    <AccountMenuView
      user={data.user}
      pending={pending}
      onOpenSettings={() => {
        void navigate("/settings");
      }}
      onOpenLocalStudio={() => {
        void navigate(LOCAL_STUDIO_PATH);
      }}
      {...(has("admin")
        ? {
            onOpenAdmin: () => {
              void navigate("/admin");
            },
          }
        : {})}
      onOpenAgent={() => {
        toggleSystemChat();
      }}
      onOpenHelp={() => {
        openHelp();
      }}
      onOpenCommands={() => {
        togglePalette();
      }}
      onLogout={() => {
        void logout();
      }}
    />
  );
};

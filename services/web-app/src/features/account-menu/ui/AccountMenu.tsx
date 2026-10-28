import { useNavigate } from "react-router";
import { useBootstrap } from "@entities/session";
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
  if (data?.mode !== "server" || data.user === null) return null;
  return (
    <AccountMenuView
      user={data.user}
      pending={pending}
      onOpenSettings={() => {
        void navigate("/settings");
      }}
      onLogout={() => {
        void logout();
      }}
    />
  );
};

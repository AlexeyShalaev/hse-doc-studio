import { AdminUsers, AuditLog } from "@features/admin-users";

/** Разделы «Пользователи» и «Аудит» админки. */
export const AdminPeoplePage = ({
  part,
  initialTab,
}: {
  part: "users" | "audit";
  initialTab?: "invitations" | "approvals" | undefined;
}) =>
  part === "users" ? (
    <AdminUsers {...(initialTab ? { initialTab } : {})} />
  ) : (
    <AuditLog />
  );

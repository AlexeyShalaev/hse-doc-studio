import { AdminUsers, AuditLog } from "@features/admin-users";

/** Разделы «Пользователи» и «Аудит» админки. */
export const AdminPeoplePage = ({ part }: { part: "users" | "audit" }) =>
  part === "users" ? <AdminUsers /> : <AuditLog />;

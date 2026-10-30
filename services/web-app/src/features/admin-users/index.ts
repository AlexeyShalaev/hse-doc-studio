export { AdminUsers } from "./ui/AdminUsers";
export { AuditLog } from "./ui/AuditLog";
export { adminUsersKeys } from "./api/adminUsersQueries";
export { ensureAdminUsersLocales } from "./lib/locales";
// Для сводки и счётчиков оболочки админки: те же запросы, что у разделов.
export { useApprovals, useAudit, useUsers } from "./api/adminUsersQueries";
export { useAuditActionLabel } from "./lib/auditLabel";

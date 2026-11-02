import { adminClient, parseResp } from "@shared/api";
import {
  AdminDiagnosticsSchema,
  type AdminDiagnostics,
  type UpdateDiagnosticsThresholdsRequest,
} from "@entities/session";

// Ошибки форм показывает сам экран: тост не нужен.
const quiet = { silentError: true } as const;

export const diagnosticsApi = {
  overview: (): Promise<AdminDiagnostics> =>
    adminClient
      .get("/diagnostics", quiet)
      .then(parseResp(AdminDiagnosticsSchema)),
  /** `check: null` проверяет всё; ручной прогон уведомлений не рассылает. */
  run: (check: string | null): Promise<AdminDiagnostics> =>
    adminClient
      .post("/diagnostics/run", { check }, quiet)
      .then(parseResp(AdminDiagnosticsSchema)),
  saveThresholds: (
    body: UpdateDiagnosticsThresholdsRequest,
  ): Promise<AdminDiagnostics> =>
    adminClient
      .put("/diagnostics/thresholds", body, quiet)
      .then(parseResp(AdminDiagnosticsSchema)),
};

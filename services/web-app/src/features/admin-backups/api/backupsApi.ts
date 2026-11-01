import { adminClient, parseResp } from "@shared/api";
import {
  BackupDestinationListSchema,
  BackupDestinationSchema,
  BackupRunPageSchema,
  BackupRunSchema,
  BackupStatusSchema,
  CheckResultSchema,
  StoredBackupListSchema,
  type BackupDestination,
  type BackupRun,
  type BackupRunPage,
  type BackupStatus,
  type CheckResult,
  type DestinationBody,
  type SettingsBody,
  type StoredBackup,
} from "./schemas";

// Ошибки форм показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

export const backupsApi = {
  status: (): Promise<BackupStatus> =>
    adminClient
      .get("/backups/status", quiet)
      .then(parseResp(BackupStatusSchema)),
  saveSettings: (body: SettingsBody): Promise<BackupStatus> =>
    adminClient
      .put("/backups/settings", body, quiet)
      .then(parseResp(BackupStatusSchema)),

  destinations: (): Promise<BackupDestination[]> =>
    adminClient
      .get("/backups/destinations", quiet)
      .then(parseResp(BackupDestinationListSchema)),
  createDestination: (body: DestinationBody): Promise<BackupDestination> =>
    adminClient
      .post("/backups/destinations", body, quiet)
      .then(parseResp(BackupDestinationSchema)),
  updateDestination: (
    id: string,
    body: DestinationBody,
  ): Promise<BackupDestination> =>
    adminClient
      .put(`/backups/destinations/${enc(id)}`, body, quiet)
      .then(parseResp(BackupDestinationSchema)),
  deleteDestination: async (id: string): Promise<void> => {
    await adminClient.delete(`/backups/destinations/${enc(id)}`, quiet);
  },
  testSaved: (id: string): Promise<CheckResult> =>
    adminClient
      .post(`/backups/destinations/${enc(id)}/test`, {}, quiet)
      .then(parseResp(CheckResultSchema)),
  testForm: (
    body: DestinationBody,
    destinationId: string | null,
  ): Promise<CheckResult> =>
    adminClient
      .post(
        "/backups/destinations/test",
        { destination_id: destinationId, destination: body },
        quiet,
      )
      .then(parseResp(CheckResultSchema)),

  stored: (id: string): Promise<StoredBackup[]> =>
    adminClient
      .get(`/backups/destinations/${enc(id)}/backups`, quiet)
      .then(parseResp(StoredBackupListSchema)),
  deleteStored: async (id: string, backupId: string): Promise<void> => {
    await adminClient.delete(
      `/backups/destinations/${enc(id)}/backups/${enc(backupId)}`,
      quiet,
    );
  },

  start: (destinationId: string | null): Promise<BackupRun> =>
    adminClient
      .post("/backups/runs", { destination_id: destinationId }, quiet)
      .then(parseResp(BackupRunSchema)),
  runs: (limit: number, offset: number): Promise<BackupRunPage> =>
    adminClient
      .get("/backups/runs", { ...quiet, params: { limit, offset } })
      .then(parseResp(BackupRunPageSchema)),
};

export { RunnersPage } from "./ui/RunnersPage";
export { Quotas as QuotasPage } from "./ui/Quotas";
export { Services as ServicesPage } from "./ui/Services";
export { Storage as StoragePage } from "./ui/Storage";
export { getAdminOpsGallery } from "./ui/opsGallery";
export { opsKeys } from "./api/opsQueries";
// Для сводки и счётчиков оболочки админки: те же запросы, что у разделов.
// Раннеры там только счётчиками сервера: список целиком не читается нигде.
export {
  useQueueSummary,
  useRunnerSummary,
  useServices,
  useStorage,
} from "./api/opsQueries";
export { liveRunners, quietRunners } from "./lib/runnerStatus";
export type { RunnerStatus } from "./lib/runnerStatus";
export { diskTone, isLowSpace } from "./lib/storage";
export {
  HEALTH_TONE,
  serviceHealth,
  summarizeHealth,
} from "./lib/serviceHealth";
export type { ServiceHealth } from "./lib/serviceHealth";
export { useNow } from "./lib/useNow";

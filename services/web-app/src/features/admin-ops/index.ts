export { RunnersPage } from "./ui/RunnersPage";
export { Quotas as QuotasPage } from "./ui/Quotas";
export { Services as ServicesPage } from "./ui/Services";
export { Storage as StoragePage } from "./ui/Storage";
export { getAdminOpsGallery } from "./ui/opsGallery";
export { opsKeys } from "./api/opsQueries";
// Для сводки и счётчиков оболочки админки: те же запросы, что у разделов.
export {
  useQueueSummary,
  useRunners,
  useServices,
  useStorage,
} from "./api/opsQueries";
export { countOnline, runnerStatus } from "./lib/runnerStatus";
export type { RunnerStatus } from "./lib/runnerStatus";
export { isLowSpace } from "./lib/storage";
export { useNow } from "./lib/useNow";

import {
  QuotasPage,
  RunnersPage,
  ServicesPage,
  StoragePage,
} from "@features/admin-ops";

export type AdminOpsPart = "runners" | "quotas" | "services" | "storage";

/** Операционные разделы админки: раннеры и очередь, квоты, сервисы, хранилище. */
export const AdminOpsPage = ({ part }: { part: AdminOpsPart }) => {
  switch (part) {
    case "runners":
      return <RunnersPage />;
    case "quotas":
      return <QuotasPage />;
    case "services":
      return <ServicesPage />;
    case "storage":
      return <StoragePage />;
  }
};

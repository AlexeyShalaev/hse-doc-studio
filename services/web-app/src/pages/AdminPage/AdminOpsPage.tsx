import {
  QuotasPage,
  RunnersPage,
  ServicesPage,
  StoragePage,
} from "@features/admin-ops";

export type AdminOpsPart = "runners" | "quotas" | "services" | "storage";

/** Операционные разделы админки: раннеры и очередь, квоты, сервисы, хранилище. */
export const AdminOpsPage = ({
  part,
  initialCreateToken = false,
}: {
  part: AdminOpsPart;
  /** Сразу открыть создание токена регистрации раннера. */
  initialCreateToken?: boolean;
}) => {
  switch (part) {
    case "runners":
      return <RunnersPage initialCreateToken={initialCreateToken} />;
    case "quotas":
      return <QuotasPage />;
    case "services":
      return <ServicesPage />;
    case "storage":
      return <StoragePage />;
  }
};

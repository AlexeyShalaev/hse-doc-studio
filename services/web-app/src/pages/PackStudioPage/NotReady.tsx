import { useTranslation } from "react-i18next";
import {
  useRefreshPackWorkspace,
  workspaceErrorText,
  type PackWorkspace,
} from "@entities/pack-studio";
import { EmptyState, ErrorState, Spinner } from "@shared/ui";

/** Пространство не готово: клон идёт или не удался. */
export const NotReady = ({ workspace }: { workspace: PackWorkspace }) => {
  const { t } = useTranslation("packStudio");
  const refresh = useRefreshPackWorkspace();
  if (workspace.state === "cloning") {
    return (
      <EmptyState
        framed
        icon={<Spinner size="md" />}
        title={t("workspace.cloningTitle")}
        description={t("workspace.cloningLead")}
        testId="ws-cloning"
      />
    );
  }
  return (
    <ErrorState
      framed
      title={t("workspace.failedTitle")}
      description={
        workspace.error
          ? workspaceErrorText(workspace.error)
          : t("workspace.failedLead")
      }
      onRetry={() => {
        refresh.mutate(workspace.id);
      }}
      retrying={refresh.isPending}
      testId="ws-failed"
    />
  );
};

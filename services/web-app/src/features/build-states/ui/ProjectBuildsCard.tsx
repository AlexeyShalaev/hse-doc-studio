import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { i18n, toast } from "@shared/lib";
import {
  useProjectBuildRunners,
  useUpdateProjectBuildRunners,
} from "@entities/runner";
import { ProjectBuildsView } from "./ProjectBuildsView";

/** «Сборки» в настройках серверного проекта: выбор сохраняется сразу, без панели сохранения. */
export const ProjectBuildsCard = ({ projectId }: { projectId: string }) => {
  const { t } = useTranslation("workspace");
  const info = useProjectBuildRunners(projectId);
  const update = useUpdateProjectBuildRunners(projectId);
  return (
    <ProjectBuildsView
      status={info.data ? "ready" : info.isError ? "error" : "loading"}
      info={info.data ?? null}
      saving={update.isPending}
      onRetry={() => void info.refetch()}
      onChange={(policy) => {
        if (policy === info.data?.policy) return;
        update.mutate(policy, {
          onSuccess: () => {
            toast.success(t("projectSettings.builds.saved"));
          },
          onError: (error) => {
            const key = `errors:code.${failureCode(error)}`;
            toast.error(
              i18n.exists(key)
                ? i18n.t(key)
                : i18n.t("runners:failure.unknown"),
            );
          },
        });
      }}
    />
  );
};

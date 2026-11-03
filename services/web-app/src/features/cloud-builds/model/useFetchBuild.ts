import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import {
  useFetchCloudBuild,
  type FetchBuildResponse,
  type FetchStatus,
} from "@entities/project-build";

const OK: ReadonlySet<FetchStatus> = new Set<FetchStatus>([
  "downloaded",
  "unchanged",
]);

/** «Получить сборку»: запрос и понятный тост по итогу каждого документа. `force` заменяет и более свежую локальную. */
export const useFetchBuild = (projectId: string) => {
  const { t } = useTranslation("devices");
  const fetchBuild = useFetchCloudBuild(projectId);
  const report = (result: FetchBuildResponse): void => {
    for (const item of result.items) {
      const text = t(`builds.result.${item.status}`);
      if (OK.has(item.status)) toast.success(text);
      else toast.error(text);
    }
  };
  return {
    isPending: fetchBuild.isPending,
    run: (docId: string | null, force = false): void => {
      fetchBuild.mutate(
        { doc_id: docId, force, auto: false },
        {
          onSuccess: report,
          onError: () => {
            toast.error(t("builds.result.failed"));
          },
        },
      );
    },
  };
};

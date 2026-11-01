import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import {
  useBuildSettings,
  useInstanceSettings,
  useUpdateBuild,
  useUpdateInstance,
} from "../api/installQueries";
import { AdminSharingSettingsSection } from "./AdminSharingSettings";
import { InstanceForm } from "./InstanceForm";
import { LoadState, PageHead } from "./parts";
import { Ready } from "./Ready";

/** Раздел «Установка»: название, публичный адрес, ссылка на документацию и параметры сборки. */
export const InstancePage = () => (
  <Ready>
    <InstanceBody />
  </Ready>
);

const InstanceBody = () => {
  const { t } = useTranslation("adminInstall");
  const instance = useInstanceSettings();
  const build = useBuildSettings();
  const saveInstance = useUpdateInstance();
  const saveBuild = useUpdateBuild();

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20, flex: 1 }}
      data-testid="admin-install"
    >
      <PageHead
        title={t("instance.page.title")}
        lead={t("instance.page.lead")}
      />
      {instance.data && build.data ? (
        <InstanceForm
          instance={instance.data}
          build={build.data}
          saveInstance={(patch) => saveInstance.mutateAsync(patch)}
          saveBuild={(patch) => saveBuild.mutateAsync(patch)}
          onSaved={() => {
            toast.success(t("savedToast"));
          }}
        />
      ) : (
        <LoadState
          failed={instance.isError || build.isError}
          onRetry={() => {
            if (instance.isError) void instance.refetch();
            if (build.isError) void build.refetch();
          }}
        />
      )}
      {/* links: раздел «Общий доступ» (ссылки на проекты). */}
      <AdminSharingSettingsSection />
    </div>
  );
};

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import {
  useBuildSettings,
  useInstanceSettings,
  useUpdateBuild,
  useUpdateInstance,
} from "../api/installQueries";
import { BuildCard } from "./BuildCard";
import { InstanceCard } from "./InstanceCard";
import { LoadState } from "./LoadState";
import { PageHead } from "./parts";
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
  const [saved, setSaved] = useState({ instance: false, build: false });
  // Каждое сохранение пересоздаёт форму: черновик возвращается к ответу сервера.
  const [rounds, setRounds] = useState({ instance: 0, build: 0 });
  const done = (key: "instance" | "build") => {
    setSaved((s) => ({ ...s, [key]: true }));
    setRounds((r) => ({ ...r, [key]: r[key] + 1 }));
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20 }}
      data-testid="admin-install"
    >
      <PageHead
        title={t("instance.page.title")}
        lead={t("instance.page.lead")}
      />
      <div className="flex flex-col" style={{ gap: 14 }}>
        {!instance.data && (
          <LoadState
            failed={instance.isError}
            onRetry={() => {
              void instance.refetch();
            }}
          />
        )}
        {instance.data && (
          <InstanceCard
            key={`${JSON.stringify(instance.data)}:${String(rounds.instance)}`}
            settings={instance.data}
            pending={saveInstance.isPending}
            failure={
              saveInstance.isError
                ? { code: failureCode(saveInstance.error) }
                : null
            }
            saved={saved.instance}
            onSave={(patch) => {
              setSaved((s) => ({ ...s, instance: false }));
              saveInstance.mutate(patch, {
                onSuccess: () => {
                  done("instance");
                  toast.success(t("instance.toast"));
                },
              });
            }}
          />
        )}
        {build.data && (
          <BuildCard
            key={`${JSON.stringify(build.data)}:${String(rounds.build)}`}
            settings={build.data}
            pending={saveBuild.isPending}
            failure={
              saveBuild.isError ? { code: failureCode(saveBuild.error) } : null
            }
            saved={saved.build}
            onSave={(patch) => {
              setSaved((s) => ({ ...s, build: false }));
              saveBuild.mutate(patch, {
                onSuccess: () => {
                  done("build");
                },
              });
            }}
          />
        )}
        {instance.data && !build.data && (
          <LoadState
            failed={build.isError}
            onRetry={() => {
              void build.refetch();
            }}
          />
        )}
      </div>
    </div>
  );
};

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Cpu, HardDriveDownload, Play, Power, Server } from "lucide-react";
import {
  aiRuntimeApi,
  useHardwareInfo,
  useModelCatalog,
  useOllamaRuntimeStatus,
  useStartRuntime,
  useStopRuntime,
  useStartPull,
  useDeleteModel,
} from "@entities/ai-runtime";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import { useInvalidateLocalRuntime } from "../lib/useInvalidateLocalRuntime";
import { DownloadsSection } from "./DownloadsSection";
import { HardwareCard } from "./HardwareCard";
import { InstallProgressModal } from "./InstallProgressModal";
import { LoadedModelsSection } from "./LoadedModelsSection";
import { ModelCatalogSection } from "./ModelCatalogSection";

type ModalState = { title: string; target: string; url: string };

export const LocalRuntimePanel = () => {
  const { t } = useTranslation("localRuntime");
  const hardwareQuery = useHardwareInfo();
  const catalogQuery = useModelCatalog();
  const statusQuery = useOllamaRuntimeStatus();
  const startRuntime = useStartRuntime();
  const stopRuntime = useStopRuntime();
  const startPull = useStartPull();
  const deleteModel = useDeleteModel();
  const invalidate = useInvalidateLocalRuntime();

  const [modal, setModal] = useState<ModalState | null>(null);

  const status = statusQuery.data;
  const mode = status?.mode ?? "none";
  const dockerAvailable = status?.docker_available ?? false;
  const engineInstalled = status?.engine_image_installed ?? false;
  const running = mode === "native" || mode === "docker";
  const canInstallModels = running || (dockerAvailable && engineInstalled);
  const busy =
    deleteModel.isPending || startRuntime.isPending || stopRuntime.isPending;

  const openEngineInstall = () => {
    setModal({
      title: t("panel.engineInstallTitle"),
      target: "ollama/ollama",
      url: aiRuntimeApi.installEngineStreamUrl(),
    });
  };

  const handleInstall = (name: string) => {
    // Fire-and-forget: the pull runs in the background (survives closing the
    // modal/tab). Progress shows up in the "Загрузки" section below.
    startPull.mutate(name, {
      onSuccess: () => toast.success(t("toast.pullStarted", { name })),
      onError: () => toast.error(t("toast.pullStartFailed", { name })),
    });
  };

  const handleStart = () => {
    startRuntime.mutate(undefined, {
      onSuccess: (res) => {
        invalidate();
        if (!res.started) toast.error(t("toast.startRuntimeFailed"));
      },
      onError: () => toast.error(t("toast.startError")),
    });
  };

  const handleStop = () => {
    stopRuntime.mutate(undefined, { onSuccess: invalidate });
  };

  const handleDelete = (name: string) => {
    if (!window.confirm(t("confirm.deleteModel", { name }))) return;
    deleteModel.mutate(name, {
      onSuccess: () => toast.success(t("toast.modelDeleted", { name })),
      onError: () => toast.error(t("toast.deleteFailed")),
    });
  };

  return (
    <div className="flex flex-col" style={{ gap: "0.75rem" }}>
      <div className="flex flex-col" style={{ gap: "0.25rem" }}>
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          <Server size="0.8125rem" style={{ color: "var(--fg-2)" }} />
          <span style={{ fontSize: "0.78125rem", fontWeight: 600 }}>
            {t("panel.title")}
          </span>
        </div>
        <span className="dim" style={{ fontSize: "0.6875rem" }}>
          {t("panel.description")}
        </span>
      </div>

      {hardwareQuery.data && <HardwareCard hardware={hardwareQuery.data} />}

      {/* Runtime control bar */}
      <div
        className="flex items-center justify-between"
        style={{
          gap: "0.75rem",
          padding: "0.625rem 0.75rem",
          borderRadius: "0.375rem",
          border: "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", minWidth: 0, fontSize: "0.75rem" }}
        >
          {statusQuery.isLoading ? (
            <Spinner size="sm" />
          ) : (
            <span
              style={{
                width: "0.5rem",
                height: "0.5rem",
                borderRadius: "50%",
                background: running ? "var(--c-ok)" : "var(--fg-3)",
                flexShrink: 0,
              }}
            />
          )}
          <span style={{ fontWeight: 500 }}>{t(`mode.${mode}`)}</span>
          {status?.version && (
            <span className="mono dim" style={{ fontSize: "0.65625rem" }}>
              v{status.version}
            </span>
          )}
        </div>

        <div
          className="flex items-center"
          style={{ gap: "0.375rem", flexShrink: 0 }}
        >
          {mode === "docker" && (
            <button
              type="button"
              className="btn xs"
              onClick={handleStop}
              disabled={busy}
              title={t("controls.stopTitle")}
            >
              <Power size="0.6875rem" />
              {t("controls.stop")}
            </button>
          )}
          {mode === "none" && dockerAvailable && !engineInstalled && (
            <button
              type="button"
              className="btn xs"
              onClick={openEngineInstall}
            >
              <HardDriveDownload size="0.6875rem" />
              {t("controls.downloadEngine")}
            </button>
          )}
          {mode === "none" && dockerAvailable && engineInstalled && (
            <button
              type="button"
              className="btn xs"
              onClick={handleStart}
              disabled={busy}
            >
              <Play size="0.6875rem" />
              {t("controls.start")}
            </button>
          )}
        </div>
      </div>

      {mode === "none" && !dockerAvailable && (
        <div
          className="flex items-start"
          style={{
            gap: "0.375rem",
            fontSize: "0.6875rem",
            color: "var(--c-warn)",
          }}
        >
          <Cpu size="0.75rem" style={{ marginTop: 1, flexShrink: 0 }} />
          <span>{t("panel.dockerUnavailable")}</span>
        </div>
      )}

      {!canInstallModels && (
        <span className="dim" style={{ fontSize: "0.6875rem" }}>
          {dockerAvailable && !engineInstalled
            ? t("panel.downloadEngineFirst")
            : t("panel.startRuntimeFirst")}
        </span>
      )}

      <LoadedModelsSection />

      <DownloadsSection />

      <ModelCatalogSection
        catalog={catalogQuery.data}
        isLoading={catalogQuery.isLoading}
        installedModels={status?.installed_models ?? []}
        canInstall={canInstallModels}
        busy={busy}
        onInstall={handleInstall}
        onDelete={handleDelete}
      />

      <InstallProgressModal
        title={modal?.title ?? ""}
        target={modal?.target ?? null}
        url={modal?.url ?? null}
        onClose={() => {
          setModal(null);
        }}
        onSuccess={invalidate}
      />
    </div>
  );
};

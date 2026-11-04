import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import {
  AlertTriangle,
  Check,
  FileX,
  FolderOpen,
  FolderPlus,
  Layers,
  Loader2,
  Plug,
} from "lucide-react";
import { useConnectProject } from "@entities/project";
import { FolderPickerModal, useInspectFolder } from "@features/folder-picker";
import { ApiError } from "@shared/api/client";
import type { InspectResponse } from "@shared/api/types";

export const ProjectConnectWizard = () => {
  const { t } = useTranslation("projectConnect");
  const navigate = useNavigate();
  const { mutateAsync: connectProject, isPending } = useConnectProject();
  const [folder, setFolder] = useState<string>("");
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  const trimmed = folder.trim();
  const {
    data: inspectData,
    isFetching: isInspecting,
    error: inspectError,
  } = useInspectFolder(trimmed, trimmed.length > 0);

  const inspectErrorMsg =
    inspectError instanceof ApiError
      ? inspectError.detail
      : inspectError instanceof Error
        ? inspectError.message
        : null;

  const handleConnect = async () => {
    setConnectError(null);
    try {
      const project = await connectProject({ folder: trimmed });
      void navigate(`/projects/${project.id}/documents`);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message
            : t("actions.connectFailed");
      setConnectError(msg);
    }
  };

  const goCreateHere = () => {
    void navigate(`/wizard?mode=create&folder=${encodeURIComponent(trimmed)}`);
  };

  return (
    <div className="flex h-full" style={{ background: "var(--bg-0)" }}>
      <div
        className="flex-1 flex flex-col items-center"
        style={{ minWidth: 0, overflow: "auto" }}
      >
        <div
          className="flex flex-col"
          style={{
            width: "100%",
            maxWidth: "40rem",
            padding: "2rem 1.5rem 1.5rem",
            gap: "1.25rem",
          }}
        >
          {/* Header */}
          <div>
            <div
              className="flex items-center gap-2"
              style={{ marginBottom: "0.375rem" }}
            >
              <FolderOpen size="0.875rem" style={{ color: "var(--accent)" }} />
              <span
                className="mono"
                style={{
                  fontSize: "0.625rem",
                  color: "var(--accent)",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                }}
              >
                {t("header.eyebrow")}
              </span>
            </div>
            <h2
              style={{
                margin: "0 0 0.25rem",
                fontSize: "1.25rem",
                fontWeight: 600,
                letterSpacing: "-0.01em",
              }}
            >
              {t("header.title")}
            </h2>
            <p className="dim" style={{ margin: 0, fontSize: "0.78125rem" }}>
              <Trans
                i18nKey="header.description"
                ns="projectConnect"
                components={[<span className="mono" key="path" />]}
              />
            </p>
          </div>

          {/* Folder input */}
          <div className="field">
            <label>{t("folder.label")}</label>
            <div className="flex gap-2">
              <input
                type="text"
                className="input mono"
                style={{ flex: 1, minWidth: 0 }}
                placeholder={t("folder.placeholder")}
                value={folder}
                onChange={(e) => {
                  setFolder(e.target.value);
                  setConnectError(null);
                }}
                autoFocus
              />
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setIsPickerOpen(true);
                }}
              >
                <FolderOpen size="0.8125rem" />
                {t("folder.browse")}
              </button>
            </div>
            <div className="hint">{t("folder.hint")}</div>
          </div>

          {/* Inspection result */}
          <InspectionPanel
            path={trimmed}
            data={inspectData}
            isFetching={isInspecting}
            errorMsg={inspectErrorMsg}
          />

          {/* Actions */}
          {connectError && (
            <div
              className="card flex items-start gap-2"
              style={{
                padding: "0.625rem",
                borderColor: "var(--c-err)",
                background: "var(--c-err-soft)",
                color: "var(--c-err)",
                fontSize: "0.75rem",
              }}
            >
              <AlertTriangle
                size="0.8125rem"
                style={{ flexShrink: 0, marginTop: 1 }}
              />
              <span>{connectError}</span>
            </div>
          )}

          <div
            className="flex items-center justify-between"
            style={{ gap: "0.5rem" }}
          >
            <button
              type="button"
              className="btn ghost"
              onClick={() => {
                void navigate("/");
              }}
            >
              {t("actions.cancel")}
            </button>

            <div className="flex gap-2">
              {inspectData?.has_project && (
                <button
                  type="button"
                  className="btn primary"
                  onClick={() => void handleConnect()}
                  disabled={isPending}
                >
                  {isPending ? (
                    <Loader2 size="0.75rem" className="spin" />
                  ) : (
                    <Plug size="0.75rem" />
                  )}
                  {t("actions.connect")}
                </button>
              )}
              {inspectData &&
                inspectData.exists &&
                inspectData.is_dir &&
                !inspectData.has_project && (
                  <button
                    type="button"
                    className="btn primary"
                    onClick={goCreateHere}
                  >
                    <FolderPlus size="0.75rem" />
                    {t("actions.createHere")}
                  </button>
                )}
            </div>
          </div>
        </div>
      </div>

      <FolderPickerModal
        isOpen={isPickerOpen}
        onClose={() => {
          setIsPickerOpen(false);
        }}
        onSelect={(path) => {
          setFolder(path);
          setConnectError(null);
        }}
        initialPath={folder || null}
      />
    </div>
  );
};

const InspectionPanel = ({
  path,
  data,
  isFetching,
  errorMsg,
}: {
  path: string;
  data: InspectResponse | undefined;
  isFetching: boolean;
  errorMsg: string | null;
}) => {
  const { t } = useTranslation("projectConnect");
  if (path === "") {
    return (
      <div
        className="card flex items-center gap-2"
        style={{
          padding: "0.75rem",
          borderStyle: "dashed",
          background: "var(--bg-0)",
          color: "var(--fg-3)",
          fontSize: "0.75rem",
        }}
      >
        <FolderOpen size="0.8125rem" style={{ flexShrink: 0 }} />
        <span>{t("inspection.empty")}</span>
      </div>
    );
  }

  if (isFetching && !data) {
    return (
      <div
        className="card flex items-center gap-2"
        style={{
          padding: "0.75rem",
          background: "var(--bg-1)",
          fontSize: "0.75rem",
          color: "var(--fg-2)",
        }}
      >
        <Loader2 size="0.8125rem" className="spin" style={{ flexShrink: 0 }} />
        <span>{t("inspection.checking")}</span>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div
        className="card flex items-start gap-2"
        style={{
          padding: "0.75rem",
          borderColor: "var(--c-err)",
          background: "var(--c-err-soft)",
          color: "var(--c-err)",
          fontSize: "0.75rem",
        }}
      >
        <AlertTriangle
          size="0.8125rem"
          style={{ flexShrink: 0, marginTop: 1 }}
        />
        <span>{errorMsg}</span>
      </div>
    );
  }

  if (!data) return null;

  if (!data.exists) {
    return (
      <div
        className="card flex items-start gap-2"
        style={{
          padding: "0.75rem",
          borderColor: "var(--c-err)",
          background: "var(--c-err-soft)",
          color: "var(--c-err)",
          fontSize: "0.75rem",
        }}
      >
        <FileX size="0.875rem" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <div style={{ fontWeight: 600, marginBottom: "0.125rem" }}>
            {t("inspection.notExists")}
          </div>
          <div className="mono" style={{ fontSize: "0.6875rem" }}>
            {data.path}
          </div>
        </div>
      </div>
    );
  }

  if (!data.is_dir) {
    return (
      <div
        className="card flex items-start gap-2"
        style={{
          padding: "0.75rem",
          borderColor: "var(--c-warn)",
          background: "var(--c-warn-soft)",
          color: "var(--c-warn)",
          fontSize: "0.75rem",
        }}
      >
        <AlertTriangle
          size="0.875rem"
          style={{ flexShrink: 0, marginTop: 1 }}
        />
        <div>
          <div style={{ fontWeight: 600, marginBottom: "0.125rem" }}>
            {t("inspection.notDir")}
          </div>
          <div className="mono" style={{ fontSize: "0.6875rem" }}>
            {data.path}
          </div>
        </div>
      </div>
    );
  }

  if (data.has_project && data.project) {
    const proj = data.project;
    return (
      <div
        className="card"
        style={{
          padding: "0.875rem",
          borderColor: "var(--c-ok)",
          background: "var(--c-ok-soft)",
        }}
      >
        <div
          className="flex items-center gap-2"
          style={{
            color: "var(--c-ok)",
            fontWeight: 600,
            fontSize: "0.78125rem",
            marginBottom: "0.5rem",
          }}
        >
          <Check size="0.875rem" />
          {t("inspection.found")}
        </div>
        <div
          className="mono dim"
          style={{ fontSize: "0.6875rem", marginBottom: "0.625rem" }}
        >
          {data.path}
        </div>
        <div
          className="flex flex-col"
          style={{ gap: "0.25rem", fontSize: "0.78125rem" }}
        >
          <div>
            <span className="dim" style={{ marginRight: "0.5rem" }}>
              {t("inspection.fieldName")}
            </span>
            <span style={{ fontWeight: 600 }}>{proj.name}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="dim">{t("inspection.fieldPack")}</span>
            <Layers size="0.6875rem" style={{ color: "var(--accent)" }} />
            <span className="mono" style={{ fontSize: "0.71875rem" }}>
              {proj.pack_id} / {proj.template_id}
            </span>
            <span className="chip">{proj.version}</span>
          </div>
          <div>
            <span className="dim" style={{ marginRight: "0.5rem" }}>
              {t("inspection.fieldEngine")}
            </span>
            <span className="mono" style={{ fontSize: "0.71875rem" }}>
              {proj.engine}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Folder exists but no .hse-studio
  return (
    <div
      className="card"
      style={{
        padding: "0.875rem",
        borderColor: "var(--c-warn)",
        background: "var(--c-warn-soft)",
      }}
    >
      <div
        className="flex items-center gap-2"
        style={{
          color: "var(--c-warn)",
          fontWeight: 600,
          fontSize: "0.78125rem",
          marginBottom: "0.375rem",
        }}
      >
        <AlertTriangle size="0.875rem" />
        {t("inspection.noProject")}
      </div>
      <div
        className="mono dim"
        style={{ fontSize: "0.6875rem", marginBottom: "0.5rem" }}
      >
        {data.path}
      </div>
      <div className="dim" style={{ fontSize: "0.75rem", lineHeight: 1.5 }}>
        <Trans
          i18nKey="inspection.noProjectHint"
          ns="projectConnect"
          components={[<span className="mono" key="path" />]}
        />
      </div>
    </div>
  );
};

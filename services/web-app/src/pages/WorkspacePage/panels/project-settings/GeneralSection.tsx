import { FolderInput, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { OpenFolderInEditor } from "@entities/system";
import { toast } from "@shared/lib";
import { SectionCard } from "../SectionCard";
import type { Project } from "./types";

export type GeneralSectionProps = {
  project: Project;
  // Черновое значение имени (effective.name) — владелец держит его в автосейве.
  name: string;
  isTeam: boolean;
  // Локализованная подпись шаблона (useTemplateMeta().label).
  templateLabel: string;
  isMoving: boolean;
  onNameChange: (name: string) => void;
  onRequestMove: () => void;
};

export const GeneralSection = ({
  project,
  name,
  isTeam,
  templateLabel,
  isMoving,
  onNameChange,
  onRequestMove,
}: GeneralSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionGeneral")}>
      <div className="field">
        {/* In a team the project name is the shared system being built;
            each author's own topic lives on their author card. */}
        <label>
          {isTeam ? t("projectSettings.systemName") : t("projectSettings.name")}
        </label>
        <input
          className="input"
          value={name}
          onChange={(e) => {
            onNameChange(e.target.value);
          }}
        />
      </div>
      <div className="field">
        <label>{t("projectSettings.template")}</label>
        {/* minWidth инлайном: утилиты min-w-0 в сборке Tailwind нет. */}
        <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
          <span
            className="chip"
            title={templateLabel}
            style={{
              minWidth: 0,
              background: "var(--accent-soft)",
              color: "var(--accent)",
              borderColor: "var(--accent-line)",
            }}
          >
            <span className="truncate">{templateLabel}</span>
          </span>
          <span className="dim mono shrink-0" style={{ fontSize: 11 }}>
            {project.lock.pack_id}/{project.lock.template_id}@
            {project.lock.version}
          </span>
        </div>
      </div>
      <div className="field">
        <label>{t("projectSettings.workLanguage")}</label>
        <div className="flex items-center gap-2">
          <span
            className="chip"
            style={{ background: "var(--bg-2)", color: "var(--fg-1)" }}
          >
            {project.lang === "en"
              ? t("projectSettings.languageEn")
              : t("projectSettings.languageRu")}
          </span>
          <span className="dim" style={{ fontSize: 11 }}>
            {t("projectSettings.workLanguageHint")}
          </span>
        </div>
      </div>
      <div className="field">
        <label>{t("projectSettings.localFolder")}</label>
        <div className="flex gap-2">
          <input className="input mono" value={project.folder} readOnly />
          <button
            type="button"
            className="btn tt"
            data-tt={t("projectSettings.copyPath")}
            onClick={() => {
              navigator.clipboard
                .writeText(project.folder)
                .then(() => {
                  toast.info(t("projectSettings.pathCopied"));
                })
                .catch(() => {
                  toast.error(t("projectSettings.copyFailed"));
                });
            }}
          >
            <FolderOpen size={12} />
          </button>
          <OpenFolderInEditor path={project.folder} />
        </div>
        <button
          type="button"
          className="btn ghost self-start"
          style={{ marginTop: 8 }}
          disabled={isMoving}
          onClick={onRequestMove}
        >
          <FolderInput size={11} />
          {isMoving
            ? t("projectSettings.moving")
            : t("projectSettings.moveToAnotherFolder")}
        </button>
      </div>
    </SectionCard>
  );
};

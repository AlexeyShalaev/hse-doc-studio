import { useTranslation } from "react-i18next";
import type { ConflictFile } from "@entities/git-sync";
import { Spinner } from "@shared/ui/Spinner";
import { Notice, ViewTabs, type ViewTab } from "@shared/ui/ConflictKit";
import {
  composeText,
  isBinaryDetail,
  isDeleteConflict,
  isGroupConflict,
  isJsonDetail,
  isTextDetail,
  needsDecision,
} from "../model/conflictModel";
import type {
  ConflictView,
  ConflictWorkspace,
} from "../model/useConflictWorkspace";
import { AutoFileInfo } from "./AutoFileInfo";
import { BinaryResolver } from "./BinaryResolver";
import { ConflictFileDiff } from "./ConflictFileDiff";
import { DeleteModifyResolver } from "./DeleteModifyResolver";
import { GroupChoiceResolver } from "./GroupChoiceResolver";
import { JsonFieldResolver } from "./JsonFieldResolver";
import { ManualEditor } from "./ManualEditor";
import { SideFacts } from "./SideFacts";
import { TextHunkResolver } from "./TextHunkResolver";
import { WholeFileChoice } from "./WholeFileChoice";

export type ConflictFilePaneProps = {
  projectId: string;
  workspace: ConflictWorkspace;
};

const viewsFor = (file: ConflictFile): ConflictView[] => {
  // Подписи и имена, различающиеся регистром, решаются только выбором стороны.
  if (isGroupConflict(file)) return ["parts"];
  // При удалении против правки полезно увидеть, что именно изменили.
  if (isDeleteConflict(file)) return ["parts", "mine", "theirs"];
  if (file.kind === "binary" || file.kind === "delete") return ["parts"];
  if (file.hunks > 0) return ["parts", "mine", "theirs", "result", "manual"];
  if (file.kind === "json") return ["parts", "mine", "theirs", "result"];
  return ["parts", "mine", "theirs"];
};

const isDeletedBy = (value: string): value is "ours" | "theirs" =>
  value === "ours" || value === "theirs";

const PaneHeader = ({
  file,
  theirsAuthor,
}: {
  file: ConflictFile;
  theirsAuthor: string | null;
}) => {
  const { t } = useTranslation("gitConflicts");
  const type = file.conflict_type;
  return (
    <div className="flex flex-col" style={{ gap: 6 }}>
      <div className="flex items-center" style={{ gap: 8, minWidth: 0 }}>
        <h3
          className="mono truncate"
          style={{ margin: 0, fontSize: 13, fontWeight: 600 }}
          title={file.path}
        >
          {file.path}
        </h3>
        <span className="chip subtle">
          {needsDecision(file)
            ? t(
                `kind.${
                  type === "deleted_by_us" || type === "deleted_by_them"
                    ? "delete"
                    : file.kind
                }`,
                { defaultValue: file.kind },
              )
            : t(`auto.action.${file.action}`, { defaultValue: file.action })}
        </span>
      </div>
      {type && needsDecision(file) && (
        <p className="dim" style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>
          {t(`conflictType.${type}`, { defaultValue: "" })}
        </p>
      )}
      <dl className="side-facts">
        <dt>{t("side.mine")}</dt>
        <dd>
          <SideFacts side={file.sides.ours} />
        </dd>
        <dt>
          {t("side.theirs", { author: theirsAuthor ?? t("side.unknown") })}
        </dt>
        <dd>
          <SideFacts side={file.sides.theirs} />
        </dd>
      </dl>
    </div>
  );
};

/**
 * Правая часть экрана: что за файл, вкладки видов и сам разбор. Для текста
 * это карточки по местам, для остальных видов выбор версии целиком.
 */
export const ConflictFilePane = ({
  projectId,
  workspace,
}: ConflictFilePaneProps) => {
  const { t } = useTranslation("gitConflicts");
  const { selected: file, session, view, setView, detail, drafts } = workspace;

  if (!file) {
    return (
      <div
        className="dim flex items-center justify-center"
        style={{ flex: 1, fontSize: 12.5, padding: 24 }}
      >
        {t("pane.select")}
      </div>
    );
  }

  const theirsAuthor =
    file.sides.theirs.author ?? session.theirs.author ?? null;
  const resolution = drafts.drafts[file.path];

  if (!needsDecision(file)) {
    return (
      <div className="flex flex-col" style={{ gap: 14 }}>
        <PaneHeader file={file} theirsAuthor={theirsAuthor} />
        <AutoFileInfo file={file} theirsAuthor={theirsAuthor} />
      </div>
    );
  }

  const views = viewsFor(file);
  const activeView = views.includes(view) ? view : "parts";
  const tabs: ViewTab<ConflictView>[] = views.map((value) => ({
    value,
    label:
      value === "parts" && file.hunks === 0
        ? t("view.choose")
        : t(`view.${value}`),
  }));
  const theirsLabel = theirsAuthor
    ? t("hunk.theirs", { author: theirsAuthor })
    : t("hunk.theirsPlain");

  const body = ((): React.ReactNode => {
    if (activeView === "mine" || activeView === "theirs") {
      return (
        <ConflictFileDiff
          projectId={projectId}
          path={file.path}
          view={activeView === "mine" ? "ours" : "theirs"}
          revision={0}
          isSaving={false}
        />
      );
    }
    if (activeView === "result") {
      return (
        <ConflictFileDiff
          projectId={projectId}
          path={file.path}
          view="result"
          revision={drafts.savedRevision}
          isSaving={
            drafts.saveState === "dirty" || drafts.saveState === "saving"
          }
        />
      );
    }

    // Эти конфликты понятны по типу, подробности файла им не нужны.
    if (isGroupConflict(file)) {
      return (
        <GroupChoiceResolver
          file={file}
          resolution={resolution}
          theirsAuthor={theirsAuthor}
          onChoose={workspace.chooseFile}
        />
      );
    }
    if (isDeleteConflict(file)) {
      return (
        <DeleteModifyResolver
          file={file}
          resolution={resolution}
          theirsAuthor={theirsAuthor}
          deletedBy={
            detail?.kind === "delete" && isDeletedBy(detail.deleted_by)
              ? detail.deleted_by
              : null
          }
          onChoose={workspace.chooseFile}
        />
      );
    }

    if (workspace.detailLoading) {
      return (
        <div
          className="flex items-center justify-center"
          style={{ gap: 8, padding: 24 }}
        >
          <Spinner size="sm" />
          <span className="dim" style={{ fontSize: 12 }}>
            {t("pane.loading")}
          </span>
        </div>
      );
    }
    if (workspace.detailError || !detail) {
      return (
        <Notice
          tone="err"
          role="alert"
          text={t("pane.error")}
          action={
            <button
              type="button"
              className="btn xs"
              onClick={workspace.reloadDetail}
            >
              {t("pane.retry")}
            </button>
          }
        />
      );
    }

    if (activeView === "manual") {
      if (!isTextDetail(detail)) return null;
      if (detail.truncated) {
        return (
          <Notice tone="warn" role="status" text={t("manual.truncated")} />
        );
      }
      return (
        <ManualEditor
          // Другой файл или другой план: редактор начинается заново.
          key={`${file.path}:${session.fingerprint}`}
          path={file.path}
          initialText={composeText(detail, resolution)}
          appliedText={resolution?.kind === "text" ? resolution.content : null}
          disabled={false}
          onApply={workspace.applyManual}
        />
      );
    }

    if (isJsonDetail(detail) && detail.fields.length > 0) {
      return (
        <JsonFieldResolver
          detail={detail}
          resolution={resolution}
          theirsLabel={theirsLabel}
          onChoose={workspace.chooseField}
          onClear={workspace.clearField}
          onChooseAll={workspace.chooseAllFields}
          onNextFile={workspace.goNextOpenFile}
          hasNextFile={workspace.progress.open > 0}
        />
      );
    }

    if (isBinaryDetail(detail) || file.kind === "binary") {
      return (
        <BinaryResolver
          projectId={projectId}
          file={file}
          detail={isBinaryDetail(detail) ? detail : undefined}
          resolution={resolution}
          theirsAuthor={theirsAuthor}
          onChoose={workspace.chooseFile}
        />
      );
    }

    if (isTextDetail(detail) && file.hunks > 0) {
      return (
        <TextHunkResolver
          detail={detail}
          resolution={resolution}
          theirsLabel={theirsLabel}
          focusRequest={workspace.focusRequest}
          onFocusHandled={workspace.clearFocusRequest}
          onActivateHunk={workspace.setActiveHunk}
          onChoose={workspace.chooseHunk}
          onClear={workspace.clearHunk}
          onChooseAll={workspace.chooseAll}
          onJump={workspace.jumpHunk}
          onNextFile={workspace.goNextOpenFile}
          hasNextFile={workspace.progress.open > 0}
          onRevertManual={workspace.revertManual}
        />
      );
    }

    return (
      <WholeFileChoice
        file={file}
        resolution={resolution}
        theirsAuthor={theirsAuthor}
        onChoose={workspace.chooseFile}
      />
    );
  })();

  return (
    <div className="flex flex-col" style={{ gap: 14, minWidth: 0 }}>
      <PaneHeader file={file} theirsAuthor={theirsAuthor} />
      {tabs.length > 1 && (
        <ViewTabs views={tabs} value={activeView} onChange={setView} />
      )}
      {body}
    </div>
  );
};

import { useIsMutating } from "@tanstack/react-query";
import { useMemo, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  PackErrorText,
  mergeConflictFiles,
  notifyPackFilesSaved,
  packStudioKeys,
  useMergePackBase,
  usePackVersionModel,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  BranchDialog,
  ChecksDialog,
  CommitDialog,
  DiffDialog,
  ImpactSlot,
  MergeConflictDialog,
  RepoAccessDialog,
  StartOverDialog,
  impactVersions,
  type ImpactReport,
} from "@features/pack-git";
import { pickLocalized, toast } from "@shared/lib";
import { Button } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { SubmitPrimary } from "../next-step/SubmitPrimary";
import { SubmitSection } from "../next-step/SubmitSection";
import { useSubmit } from "../next-step/useSubmit";
import { ChangesPanel, type ChangesAction } from "./ChangesPanel";
import { describePath } from "./describeChanges";
import { useChangesData } from "./useChangesStatus";
import "./space-changes.css";

type Dialog = "commit" | "branch" | "diff" | "checks" | "access" | "reset";

/** Блок «до и после» не загрузился: отправку он не держит и ничего не требует. */
const NO_IMPACT: ImpactReport = {
  pending: false,
  needsAck: false,
  summary: "",
};

/** Название документа из данных его манифеста (`name: {ru, en}`); нет: пусто. */
const docName = (data: unknown, lang: string): string => {
  const name =
    data !== null && typeof data === "object"
      ? (data as { name?: unknown }).name
      : undefined;
  return name !== null && typeof name === "object"
    ? pickLocalized(name, lang, "")
    : "";
};

/**
 * Панель «Изменения» (слот `changes`): данные и действия. Показывает `ChangesPanel`, держит окна
 * прежнего интерфейса (построчное сравнение, точка, ветка, доступ, сброс, проверки хостинга,
 * конфликт слияния) и операцию «Забрать новое». Отправка (заметки, выпуск версии, запрос) это
 * область «Главная кнопка и отправка» (S4): её состояние `useSubmit` общее у раздела отправки и
 * кнопки подвала.
 */
export const ChangesDrawer = () => {
  const { t, i18n } = useTranslation("packSpace");
  const { workspace, tree, versionRef } = useSpace();
  const nav = useSpaceNav();
  const data = useChangesData();
  const { status, raw } = data;
  const git = raw.git;
  const id = workspace.id;
  const merge = useMergePackBase(id);
  const running = useIsMutating({ mutationKey: packStudioKeys.gitOp(id) }) > 0;
  const busy = running || (git?.workspace.busy ?? workspace.busy);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [conflict, setConflict] = useState<string[] | null>(null);
  const [impact, setImpact] = useState<ImpactReport | null>(null);

  // Та же модель версии, что читает статус (заметки): запрос один на двоих.
  const model = usePackVersionModel(
    id,
    !status.released && status.changedInVersion > 0 ? versionRef : null,
  );
  const docNames = useMemo(() => {
    const names: Record<string, string> = {};
    for (const doc of model.data?.documents ?? []) {
      const name = docName(doc.data ?? doc.manifest?.data, i18n.language);
      if (name) names[doc.id] = name;
    }
    return names;
  }, [model.data, i18n.language]);
  const templateName = (ref: PackVersionRef): string => {
    const template = tree.packs
      .find((pack) => pack.id === ref.pack)
      ?.templates.find((item) => item.id === ref.template);
    return pickLocalized(
      template?.name ?? undefined,
      i18n.language,
      ref.template,
    );
  };

  const versions = useMemo(
    () => impactVersions(git?.changed ?? [], versionRef).versions,
    [git, versionRef],
  );

  const submit = useSubmit({ data, impact, hasImpact: versions.length > 0 });

  const close = () => {
    setDialog(null);
  };
  const closePanel = () => {
    nav.go({ changes: false });
  };
  const openFile = (ref: PackVersionRef | null, path: string) => {
    nav.go({
      tab: "content",
      part: "files",
      file: path,
      ...(ref ? { ref } : {}),
    });
  };
  const runMerge = () => {
    if (!git) return;
    merge.mutate(undefined, {
      onSuccess: (next) => {
        toast.success(
          next.behind === 0 && git.behind === 0
            ? t("changes.behind.upToDate")
            : t("changes.behind.done"),
        );
        notifyPackFilesSaved(id);
      },
      onError: (error) => {
        const files = mergeConflictFiles(error);
        if (files) {
          merge.reset();
          setConflict(files);
        }
      },
    });
  };
  const onAction = (action: ChangesAction) => {
    if (action === "take") runMerge();
    else setDialog(action === "save" ? "commit" : action);
  };
  // Esc во всплывшем окне или меню закрывает их, а не панель: такое событие приходит из портала,
  // то есть из элемента вне этого блока.
  const guardEscape = (event: KeyboardEvent<HTMLDivElement>) => {
    if (
      event.key === "Escape" &&
      !event.currentTarget.contains(event.target as Node)
    ) {
      event.stopPropagation();
    }
  };

  return (
    <div onKeyDown={guardEscape} className="sp-ch-root">
      <ChangesPanel
        data={data}
        docNames={docNames}
        templateName={templateName}
        busy={busy}
        onClose={closePanel}
        onOpenFile={openFile}
        onGoCheck={() => {
          nav.go({ tab: "check", part: "issues" });
        }}
        onAction={onAction}
        notesAction={
          <Button size="xs" variant="ghost" onClick={submit.focusNotes}>
            {t("changes.submit.notes.write")}
          </Button>
        }
        submit={
          <SubmitSection
            c={submit}
            data={data}
            onAccess={() => {
              setDialog("access");
            }}
            onOpenFile={(path) => {
              openFile(describePath(path).version, path);
            }}
          />
        }
        primary={
          submit.available ? (
            <SubmitPrimary c={submit} errors={status.errors} />
          ) : null
        }
        notice={
          merge.isError ? (
            <Notice
              tone="err"
              role="alert"
              text={<PackErrorText error={merge.error} />}
              action={
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => {
                    merge.reset();
                  }}
                >
                  {t("changes.footer.close")}
                </Button>
              }
            />
          ) : null
        }
        impact={
          versions.length > 0 ? (
            <ImpactSlot
              workspaceId={id}
              versions={versions}
              onReport={setImpact}
              onFail={() => {
                setImpact(NO_IMPACT);
              }}
              onLeave={closePanel}
            />
          ) : null
        }
      />
      {git && (
        <>
          <CommitDialog
            git={git}
            isOpen={dialog === "commit"}
            onClose={close}
            editorDirty={false}
          />
          <BranchDialog
            git={git}
            isOpen={dialog === "branch"}
            onClose={close}
            onSwitched={() => {
              notifyPackFilesSaved(id);
            }}
          />
          <StartOverDialog
            git={git}
            isOpen={dialog === "reset"}
            onClose={close}
            onDone={() => {
              notifyPackFilesSaved(id);
            }}
          />
          <DiffDialog
            workspaceId={id}
            baseBranch={git.base_branch}
            isOpen={dialog === "diff"}
            onClose={close}
          />
          <ChecksDialog
            workspaceId={id}
            pushedSha={git.workspace.pushed_sha}
            isOpen={dialog === "checks"}
            onClose={close}
          />
          <RepoAccessDialog
            workspace={git.workspace}
            isOpen={dialog === "access"}
            onClose={close}
          />
          <MergeConflictDialog
            files={conflict}
            baseBranch={git.base_branch}
            onClose={() => {
              setConflict(null);
            }}
            onOpen={(path) => {
              openFile(null, path);
            }}
          />
        </>
      )}
    </div>
  );
};

export default ChangesDrawer;

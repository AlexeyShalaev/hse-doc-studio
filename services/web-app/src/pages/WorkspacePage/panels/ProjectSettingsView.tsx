import { Fragment, useState } from "react";
import { Settings } from "lucide-react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  useDeleteNdaFiles,
  useInstantiateNda,
  useMoveProject,
  useNdaStatus,
  useRemoveProject,
  useTemplateMeta,
  useUpdateTeamSet,
} from "@entities/project";
import { useDocuments, useUpdateDocument } from "@entities/document";
import { useVersionDetail } from "@entities/template-catalog";
import { FolderPickerModal } from "@features/folder-picker";
import { i18n, pickLocalized, toast } from "@shared/lib";
import { Modal } from "@shared/ui";
import { PageHead } from "./PageHead";
import { ProjectChecksSection } from "./ProjectChecksSection";
import { useProjectAutosave } from "./useProjectAutosave";
import {
  AuthorsSection,
  buildMetaBlocks,
  buildMetaGroupCards,
  collectManagedTeamAuthors,
  collectMetaFields,
  collectVariantRows,
  ConfidentialitySection,
  DangerZoneSection,
  DocFormatsSection,
  filterMetaFieldsBySection,
  FontsSection,
  GeneralSection,
  groupVariantRows,
  MetaSection,
  SHARED_META_BLOCK_KEY,
  SharedDocsSection,
  SupervisorSection,
  resolveProjectSettingsGroup,
  groupSections,
} from "./project-settings";
import type {
  AuthorEntry,
  Person,
  Project,
  ProjectSettingsSectionId,
} from "./project-settings";

export type ProjectSettingsViewProps = {
  project: Project;
  /**
   * Секция из адреса. Недоступная в этом проекте (пак не объявил метаполей,
   * проект не командный…) молча заменяется на «Общую информацию» — иначе
   * сохранённая ссылка открывала бы пустой канвас.
   */
  /** Сырой параметр маршрута: id группы, id раздела или мусор. */
  section: string;
  /**
   * Активный блок «Метаданных». Поднят на страницу: тот же выбор показывает
   * оглавление в панели, а панель живёт в другой ветке дерева.
   */
  metaBlock: string;
  onSelectMetaBlock: (key: string) => void;
};

// Единственный владелец черновика настроек проекта: здесь живут состояние
// автосейва, все мутации и производные значения, а секции — презентационные и
// получают value+onChange. Второй автосейв на секцию гонялся бы с этим и
// затирал поля, поэтому хук остаётся ровно один.
export const ProjectSettingsView = ({
  project,
  section,
  metaBlock,
  onSelectMetaBlock,
}: ProjectSettingsViewProps) => {
  const { t } = useTranslation("workspace");
  const navigate = useNavigate();
  // Smart autosave: edits are overlaid locally (instant inputs) and written to
  // the backend on a debounce, so typing no longer fires a request per key.
  const { effective, patch, saveNow, flush } = useProjectAutosave(project);
  const { mutate: removeProject, isPending: isRemoving } = useRemoveProject();
  const meta = useTemplateMeta(project);
  const { data: versionDetail } = useVersionDetail(
    project.lock.pack_id,
    project.lock.template_id,
    project.lock.version,
  );
  // Variant switching (e.g. the pres beamer/pptx/reveal formats) lives here,
  // not in the creation wizard: PATCH {chosen_variant} materialises missing
  // variant files losslessly and resets the document to draft.
  const { data: projectDocuments } = useDocuments(project.id);
  const updateDocument = useUpdateDocument();
  // Team projects get extra author fields (topic, slug, managed toggle), the
  // shared-docs indicator, the «Название системы» wording and the per-block
  // metadata switcher; solo keeps the old look untouched.
  const isTeam = project.staffing === "team";
  const isNda = effective.meta?.nda === true;
  const { data: ndaStatus } = useNdaStatus(project.id);
  const { mutate: instantiateNda } = useInstantiateNda();
  const { mutate: deleteNdaFiles } = useDeleteNdaFiles();
  const { mutate: moveProject, isPending: isMoving } = useMoveProject();
  const updateTeamSet = useUpdateTeamSet();
  const [ndaConfirmOpen, setNdaConfirmOpen] = useState(false);
  const [movePickerOpen, setMovePickerOpen] = useState(false);

  // Move the project into a new subfolder under the picked location, named like
  // the current folder. The backend validates emptiness + blocks while a build
  // is running; errors surface via the axios toast.
  const moveToParent = (parent: string) => {
    setMovePickerOpen(false);
    // Persist any pending field edits before the folder changes underneath us.
    flush();
    const sep = project.folder.includes("\\") ? "\\" : "/";
    const base =
      project.folder
        .replace(/[/\\]+$/, "")
        .split(/[/\\]/)
        .pop() ?? "project";
    const dest = `${parent.replace(/[/\\]+$/, "")}${sep}${base}`;
    moveProject(
      { id: project.id, folder: dest },
      {
        onSuccess: (moved) => {
          toast.success(
            t("projectSettings.projectMoved", { folder: moved.folder }),
          );
        },
      },
    );
  };

  // Enabling NDA: flip the flag, THEN materialise the template's NDA files
  // (instantiate is gated on meta.nda, so it must run after the save lands).
  // Saved immediately (not debounced) so the chained instantiate sees the flag.
  const handleEnableNda = () => {
    saveNow(
      { meta: { ...effective.meta, nda: true } },
      {
        onSuccess: () => {
          instantiateNda(project.id, {
            onSuccess: (status) => {
              if (!status.available) {
                toast.info(t("projectSettings.ndaNoTemplateDocs"));
              } else if (status.present) {
                toast.success(t("projectSettings.ndaDocsAdded"));
              }
            },
          });
        },
      },
    );
  };

  const disableNda = (deleteFiles: boolean) => {
    saveNow({ meta: { ...effective.meta, nda: false } });
    if (deleteFiles) {
      deleteNdaFiles(project.id, {
        onSuccess: () => {
          toast.info(t("projectSettings.ndaRemovedFilesDeleted"));
        },
      });
    } else {
      toast.info(t("projectSettings.ndaRemovedFilesKept"));
    }
  };

  const handleToggleNda = () => {
    if (!isNda) {
      handleEnableNda();
      return;
    }
    // Disabling: if the project has NDA files, ask whether to keep or delete.
    if (ndaStatus?.present) {
      setNdaConfirmOpen(true);
    } else {
      saveNow({ meta: { ...effective.meta, nda: false } });
    }
  };

  // Typing into name/title is debounced; flipping the role is a deliberate
  // click, so persist it immediately.
  const updateSupervisor = (patchValue: Partial<Person>) => {
    const current = effective.supervisor ?? {
      name: "",
      role: "university" as const,
    };
    const data = { supervisor: { ...current, ...patchValue } as Person };
    if ("role" in patchValue) saveNow(data);
    else patch(data);
  };

  const updateCoSupervisor = (patchValue: Partial<Person>) => {
    const current = effective.co_supervisor ?? {
      name: "",
      role: "university" as const,
    };
    const data = { co_supervisor: { ...current, ...patchValue } as Person };
    if ("role" in patchValue) saveNow(data);
    else patch(data);
  };

  // Академический руководитель ОП всегда «университетский» — роль не
  // редактируется, правки только текстовые → всегда дебаунс.
  const updateAcademicSupervisor = (patchValue: Partial<Person>) => {
    const current = effective.academic_supervisor ?? {
      name: "",
      role: "university" as const,
    };
    patch({
      academic_supervisor: { ...current, ...patchValue } as Person,
    });
  };

  // Authors are a plain editable list (Tier-2 data). The first author is kept
  // (the title page reads authors[0]); only extra authors are removable.
  const authors: AuthorEntry[] = effective.authors ?? [];
  // Normalise `group` to a string: the request DTO's `group?: string` rejects
  // an explicit `undefined` under exactOptionalPropertyTypes. The team fields
  // (slug/topic/managed/meta) MUST round-trip too — PATCH replaces the whole
  // authors array, so omitting them would wipe the backend state. `immediate`
  // covers add/remove clicks; typing into a row stays debounced.
  const commitAuthors = (next: AuthorEntry[], immediate: boolean) => {
    const data = {
      authors: next.map((a) => ({
        name: a.name,
        group: a.group ?? "",
        slug: a.slug ?? null,
        topic: a.topic ?? null,
        managed: a.managed,
        meta: a.meta,
      })),
    };
    if (immediate) saveNow(data);
    else patch(data);
  };
  const updateAuthor = (
    index: number,
    patchValue: Partial<AuthorEntry>,
    immediate = false,
  ) => {
    commitAuthors(
      authors.map((a, i) => (i === index ? { ...a, ...patchValue } : a)),
      immediate,
    );
  };

  // Пак вправе увести группу мета-полей на другую страницу настроек: «Состав
  // документов» живёт в «Документах», рядом с форматами шаблонов. В карточку
  // «Метаданных» попадает только то, что за ней осталось.
  const allMetaFields = collectMetaFields(versionDetail, project.kind);
  const metaGroups = versionDetail?.meta_groups ?? [];
  const metaFields = filterMetaFieldsBySection(
    allMetaFields,
    metaGroups,
    "meta",
  );
  const docSetCards = buildMetaGroupCards(
    allMetaFields,
    metaGroups,
    "documents",
  );
  const setMetaField = (key: string, value: string, immediate: boolean) => {
    const data = { meta: { ...effective.meta, [key]: value } };
    if (immediate) saveNow(data);
    else patch(data);
  };

  // ── Метаданные по блокам раскладки ──
  // Team: у каждого блока документов свои значения — «Общие документы»
  // (project.meta: общее ТЗ + значения по умолчанию) и комплект каждого
  // ведомого автора (author.meta перекрывает системные ключи в его базе;
  // пустое поле = наследование). Solo: единственный блок, переключателя нет.
  const managedTeamAuthors = collectManagedTeamAuthors(authors, isTeam);
  const metaBlocks = buildMetaBlocks(
    managedTeamAuthors,
    t("projectSettings.metaBlockShared"),
  );
  const activeMetaBlock = metaBlocks.some((b) => b.key === metaBlock)
    ? metaBlock
    : SHARED_META_BLOCK_KEY;
  const metaAuthor =
    activeMetaBlock === SHARED_META_BLOCK_KEY
      ? null
      : (managedTeamAuthors.find(
          (entry) => entry.author.slug === activeMetaBlock,
        ) ?? null);

  // Авторское перекрытие пишется в author.meta, общее — в project.meta; ветка
  // должна оставаться у владельца, иначе секция начнёт трогать список авторов.
  const setMetaValue = (key: string, value: string, immediate: boolean) => {
    if (metaAuthor) {
      updateAuthor(
        metaAuthor.index,
        { meta: { ...metaAuthor.author.meta, [key]: value } },
        immediate,
      );
    } else {
      setMetaField(key, value, immediate);
    }
  };

  // ── Форматы документов (варианты) ──
  const variantRows = collectVariantRows(
    versionDetail,
    projectDocuments,
    project.lang,
  );
  const variantGroups = groupVariantRows(
    variantRows,
    effective.authors ?? [],
    isTeam ? t("projectSettings.docFormatsSharedGroup") : null,
  );

  // Условия показа секций считаются из тех же производных, что и содержимое
  // карточек, — оглавление в панели строится по ним же и разойтись не может.
  // Пока каталог версии не загружен, условные секции ещё «недоступны», поэтому
  // подмена считается в рендере, а не через navigate: адрес трогать нельзя,
  // иначе ссылка на «Метаданные» превратилась бы в ссылку на «Общее».
  // Навигация идёт по ГРУППАМ: страница показывает один-три родственных
  // раздела. Параметр маршрута принимает и id группы, и id раздела — ссылки на
  // конкретный раздел продолжают работать и открывают его группу.
  const sectionCtx = {
    isTeam,
    hasDocFormats: variantRows.length > 0,
    hasDocSetMeta: docSetCards.length > 0,
    hasMetaFields: metaFields.length > 0,
  };
  const activeGroup = resolveProjectSettingsGroup(section, sectionCtx);
  const activeSections = groupSections(activeGroup, sectionCtx);

  const renderSection = (
    sectionId: ProjectSettingsSectionId,
  ): React.ReactNode => {
    switch (sectionId) {
      case "general":
        return (
          <GeneralSection
            project={project}
            name={effective.name}
            isTeam={isTeam}
            templateLabel={meta.label}
            isMoving={isMoving}
            onNameChange={(name) => {
              patch({ name });
            }}
            onRequestMove={() => {
              setMovePickerOpen(true);
            }}
          />
        );
      case "confidentiality":
        return (
          <ConfidentialitySection isNda={isNda} onToggle={handleToggleNda} />
        );
      case "doc-set":
        // Пак-driven карточки: по одной на уведённую сюда группу. Переключатель
        // блоков рисует только первая — состав у ведомых авторов свой, но два
        // одинаковых переключателя подряд читались бы как разные выборы.
        return (
          <>
            {docSetCards.map((card, index) => (
              <MetaSection
                key={card.group.id}
                fields={card.fields}
                metaGroups={[card.group]}
                title={pickLocalized(
                  card.group.label,
                  i18n.language,
                  t("projectSettings.sectionDocSet"),
                )}
                teamHint={t("projectSettings.docSetTeamHint")}
                showGroupHeadings={false}
                blocks={metaBlocks}
                activeBlock={activeMetaBlock}
                showBlockSwitcher={
                  isTeam && metaBlocks.length > 1 && index === 0
                }
                onSelectBlock={onSelectMetaBlock}
                sharedMeta={effective.meta}
                authorMeta={metaAuthor?.author.meta ?? null}
                onSetValue={setMetaValue}
              />
            ))}
          </>
        );
      case "doc-formats":
        return (
          <DocFormatsSection
            groups={variantGroups}
            isPending={updateDocument.isPending}
            onSelectVariant={(docId, variantId) => {
              updateDocument.mutate({
                projectId: project.id,
                docId,
                data: { chosen_variant: variantId },
              });
            }}
          />
        );
      case "shared-docs":
        return (
          <SharedDocsSection
            isEnabled={project.shared_enabled}
            isPending={updateTeamSet.isPending}
            onToggle={() => {
              updateTeamSet.mutate({
                id: project.id,
                authorSlug: null,
                enabled: !project.shared_enabled,
              });
            }}
          />
        );
      case "authors":
        return (
          <AuthorsSection
            authors={authors}
            isTeam={isTeam}
            isTogglingManaged={updateTeamSet.isPending}
            onChangeAuthor={updateAuthor}
            onRemoveAuthor={(index) => {
              commitAuthors(
                authors.filter((_, idx) => idx !== index),
                true,
              );
            }}
            onAddAuthor={() => {
              // В team новый автор появляется «не ведущимся»: его папку
              // материализует тоггл комплекта (бэкенд выведет слаг сам).
              commitAuthors(
                [
                  ...authors,
                  { name: "", group: "", managed: !isTeam, meta: {} },
                ],
                true,
              );
            }}
            onToggleManaged={(author) => {
              updateTeamSet.mutate({
                id: project.id,
                authorSlug: author.slug ?? null,
                enabled: !author.managed,
              });
            }}
          />
        );
      case "meta":
        return (
          <MetaSection
            fields={metaFields}
            metaGroups={versionDetail?.meta_groups ?? []}
            blocks={metaBlocks}
            activeBlock={activeMetaBlock}
            showBlockSwitcher={isTeam && metaBlocks.length > 1}
            onSelectBlock={onSelectMetaBlock}
            sharedMeta={effective.meta}
            authorMeta={metaAuthor?.author.meta ?? null}
            onSetValue={setMetaValue}
          />
        );
      case "fonts":
        return (
          <FontsSection
            versionDetail={versionDetail}
            meta={effective.meta}
            onChange={(key, value) => {
              setMetaField(key, value, true);
            }}
          />
        );
      case "supervisor":
        return (
          <SupervisorSection
            supervisor={
              (effective.supervisor as Person | null | undefined) ?? null
            }
            coSupervisor={
              (effective.co_supervisor as Person | null | undefined) ?? null
            }
            academicSupervisor={
              (effective.academic_supervisor as Person | null | undefined) ??
              null
            }
            onChangeSupervisor={updateSupervisor}
            onAddSupervisor={() => {
              saveNow({
                supervisor: { name: "", role: "university", title: "" },
              });
            }}
            onRemoveSupervisor={() => {
              saveNow({ supervisor: null });
            }}
            onChangeCoSupervisor={updateCoSupervisor}
            onAddCoSupervisor={() => {
              saveNow({
                co_supervisor: { name: "", role: "university", title: "" },
              });
            }}
            onRemoveCoSupervisor={() => {
              saveNow({ co_supervisor: null });
            }}
            onChangeAcademicSupervisor={updateAcademicSupervisor}
            onAddAcademicSupervisor={() => {
              saveNow({
                academic_supervisor: {
                  name: "",
                  role: "university",
                  title: "",
                },
              });
            }}
            onRemoveAcademicSupervisor={() => {
              saveNow({ academic_supervisor: null });
            }}
          />
        );
      case "checks":
        return <ProjectChecksSection project={project} />;
      case "danger-zone":
        return (
          <DangerZoneSection
            isArchived={effective.archived}
            isRemoving={isRemoving}
            onToggleArchive={() => {
              saveNow({ archived: !effective.archived });
            }}
            onUnlink={() => {
              removeProject(project.id, {
                onSuccess: () => {
                  // The current route is /projects/{id}/... — the project is
                  // gone, so its queries will 404 forever. Bounce to the
                  // welcome page where the user can pick or create a project.
                  void navigate("/", { replace: true });
                },
              });
            }}
          />
        );
    }
  };

  return (
    <div
      style={{
        padding: "24px 32px",
        overflowY: "auto",
        flex: 1,
        minHeight: 0,
      }}
    >
      <PageHead
        icon={Settings}
        title={t("projectSettings.title")}
        sub={t("projectSettings.subtitle")}
      />

      {/* Одна секция за раз: какую — решает адрес, оглавление живёт в
          сменной панели верстака. Сетка осталась, но в одну колонку: карточки
          с fullSpan так выглядят ровно как раньше. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr)",
          gap: 16,
          marginTop: 24,
        }}
      >
        {activeSections.map((s) => (
          <Fragment key={s.id}>{renderSection(s.id)}</Fragment>
        ))}
      </div>

      <Modal
        isOpen={ndaConfirmOpen}
        onClose={() => {
          setNdaConfirmOpen(false);
        }}
        title={t("projectSettings.ndaConfirmTitle")}
        description={t("projectSettings.ndaConfirmDescription")}
        footer={
          <>
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                disableNda(false);
                setNdaConfirmOpen(false);
              }}
            >
              {t("projectSettings.ndaKeepFiles")}
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={() => {
                disableNda(true);
                setNdaConfirmOpen(false);
              }}
            >
              {t("projectSettings.ndaDeleteFiles")}
            </button>
          </>
        }
      />

      <FolderPickerModal
        isOpen={movePickerOpen}
        onClose={() => {
          setMovePickerOpen(false);
        }}
        onSelect={moveToParent}
        initialPath={project.folder
          .replace(/[/\\]+$/, "")
          .replace(/[/\\][^/\\]+$/, "")}
      />
    </div>
  );
};

import { ChevronLeft, ListCheck, PenTool } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useForms } from "@entities/form";
import { useProject } from "@entities/project";
import { useSignaturesState } from "@entities/signature";
import { useSubmissionProfiles, useSubmissions } from "@entities/submission";
import type { CheckpointReadiness } from "@entities/submission";
import { getFormIcon } from "@features/form-fill";
import {
  pickLocalized,
  useSubmissionAuthor,
  useWorkspaceStore,
} from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { CheckpointRow } from "./CheckpointRow";

export type SubmitPanelProps = {
  projectId: string;
  selectedDocId?: string | undefined;
  onSelectDoc: (docId: string) => void;
  /** Открыть экран упаковки на конкретном профиле сдачи. */
  onOpenCheckpoint: (profileId: string) => void;
  onOpenForm: (formId: string) => void;
  onOpenSignatures: () => void;
  onOpenRequirements: () => void;
  /**
   * Готовность по профилям, посчитанная страницей (см. useCheckpointReadiness).
   * Расчёт комбинирует четыре сущности, а виджету нельзя делать это дважды —
   * поэтому он приходит сверху, а не считается здесь.
   */
  readinessByProfile?: ReadonlyMap<string, CheckpointReadiness> | undefined;
  /**
   * Анкеты, входящие в пакет ближайшей точки (CheckpointReadiness.formIds).
   * Список анкет ниже намеренно ПОЛНЫЙ — заполнить декларацию заранее никто не
   * мешает, — но «жёлтая точка» означает «блокирует упаковку», и вешать её на
   * анкету, которой эта точка не требует, значит противоречить кольцу прямо
   * над списком.
   */
  activeFormIds?: readonly string[] | undefined;
  /** Точка, закреплённая пользователем; null — автовыбор ближайшей. */
  pinnedProfileId?: string | null | undefined;
  onPinProfile?: ((profileId: string | null) => void) | undefined;
};

// Ключи канваса. Панель их не назначает — она только сверяет с ними
// selectedDocId, чтобы подсветить активную строку. Ключи анкет/подписей/
// требований унаследованы от DocumentNav, ключ контрольной точки — новый:
// экран упаковки теперь адресуется вместе с профилем.
const SIGNATURES_DOC_ID = "signatures";
const REQUIREMENTS_DOC_ID = "requirements";
const formDocId = (formId: string): string => `form:${formId}`;
const checkpointDocId = (profileId: string): string => `pack:${profileId}`;

const MUTED_NOTE_STYLE = {
  padding: "6px 10px",
  fontSize: 11.5,
  lineHeight: 1.4,
  color: "var(--fg-3)",
} as const;

/**
 * «Сдача» — единственная панель, отвечающая на вопрос «что от меня хотят к
 * ближайшей контрольной точке». Собирает то, что в старом DocumentNav было
 * размазано по секциям ИНСТРУМЕНТЫ и ФОРМЫ: контрольные точки, анкеты,
 * библиотеку подписей и трассировку требований.
 */
export const SubmitPanel = ({
  projectId,
  selectedDocId,
  onOpenCheckpoint,
  onOpenForm,
  onOpenSignatures,
  onOpenRequirements,
  readinessByProfile,
  activeFormIds,
  pinnedProfileId,
  onPinProfile,
}: SubmitPanelProps) => {
  const { t } = useTranslation("workbench");
  const setSidebarCollapsed = useWorkspaceStore(
    (state) => state.setSidebarCollapsed,
  );
  const { data: project } = useProject(projectId);
  const { data: profiles, isLoading: isProfilesLoading } =
    useSubmissionProfiles(projectId);
  const { data: submissions } = useSubmissions(projectId);
  const { data: formsData } = useForms(projectId);
  const { data: signaturesState } = useSignaturesState(projectId);

  // Названия профилей и анкет приходят из пака словарём {ru, en}: берём язык
  // документа, как это делают PackView и DocumentNav.
  const lang = project?.lang ?? "ru";
  const profileList = profiles ?? [];
  const forms = formsData?.forms ?? [];
  const activeFormIdSet = new Set(activeFormIds ?? []);

  // В команде анкеты личные («ai_declaration--ivanov»), и без ФИО владельца
  // строки неразличимы. Кольца точек уже посчитаны на выбранного автора
  // (см. useCheckpointReadiness) — панель лишь честно подписывает, чьи анкеты
  // она перечисляет; второго переключателя автора здесь нет намеренно.
  const isTeam = project?.staffing === "team";
  const authorNameBySlug = new Map(
    (project?.authors ?? []).flatMap((author) =>
      author.slug != null && author.slug !== ""
        ? [[author.slug, author.name] as const]
        : [],
    ),
  );

  // Кольца точек посчитаны на ОДНОГО автора (сдача персональная), и без имени
  // «КТ1 · 2/4» не отвечает на вопрос «чья это готовность». Кандидаты те же,
  // что в useCheckpointReadiness: только управляемые папки со slug.
  const { selectedAuthorSlug } = useSubmissionAuthor(
    projectId,
    (project?.authors ?? []).flatMap((author) =>
      author.managed && author.slug != null && author.slug !== ""
        ? [author.slug]
        : [],
    ),
  );
  const selectedAuthorName =
    isTeam && selectedAuthorSlug != null
      ? (authorNameBySlug.get(selectedAuthorSlug) ?? selectedAuthorSlug)
      : null;

  // Профиль считается сданным, если по нему уже собирали пакет.
  const packedProfileIds = new Set(
    (submissions ?? []).flatMap((s) =>
      s.profile_id != null ? [s.profile_id] : [],
    ),
  );

  // Дешёвая сводка по подписям из уже кэшированного состояния: сколько слотов
  // текущего проекта закрыто картинкой подписи. runtime_slots пуст только на
  // старом бэкенде — тогда сводки просто нет, вместо выдуманных чисел.
  const runtimeSlots = signaturesState?.runtime_slots ?? [];
  const signedSlotCount = runtimeSlots.filter(
    (slot) => signaturesState?.slots[slot.id]?.png_path != null,
  ).length;

  // Исследовательская работа матрицу требований не ведёт — секции нет вовсе.
  // Ждём загрузки проекта, иначе строка мигает и исчезает.
  const isRequirementsVisible = project != null && project.kind !== "research";

  const isSignaturesActive = selectedDocId === SIGNATURES_DOC_ID;
  const isRequirementsActive = selectedDocId === REQUIREMENTS_DOC_ID;

  return (
    <div className="workbench-panel">
      <div className="panel-head">
        <span className="panel-head-title">{t("submit.title")}</span>
        <div className="panel-head-actions">
          <button
            type="button"
            className="icon-btn sm tt"
            data-tt={t("panel.collapse")}
            onClick={() => {
              setSidebarCollapsed(true);
            }}
          >
            <ChevronLeft size={11} />
          </button>
        </div>
      </div>

      <div className="panel-body">
        <div className="nav-sub">
          <span>{t("submit.checkpoints")}</span>
          {/* Имя автора не переводится — это ФИО человека, а не термин. */}
          {selectedAuthorName != null && (
            <span
              className="truncate"
              title={selectedAuthorName}
              style={{
                minWidth: 0,
                maxWidth: 120,
                textTransform: "none",
                letterSpacing: 0,
                color: "var(--fg-2)",
              }}
            >
              {selectedAuthorName}
            </span>
          )}
        </div>
        {isProfilesLoading ? (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              padding: "10px 0",
            }}
          >
            <Spinner size="sm" />
          </div>
        ) : profileList.length === 0 ? (
          <div style={MUTED_NOTE_STYLE}>{t("submit.noProfiles")}</div>
        ) : (
          profileList.map((profile) => {
            // Пустое описание не должно превращаться в пустую подсказку —
            // тогда строка покажет в title собственное имя.
            const description = pickLocalized(profile.description, lang, "");
            // Профиль без описанного состава (items == null) даёт isUnknown —
            // кольцо не показываем вовсе, «0 из 0» было бы враньём.
            const readiness = readinessByProfile?.get(profile.id);
            const ring =
              readiness && !readiness.isUnknown
                ? { done: readiness.done, total: readiness.total }
                : undefined;
            return (
              <CheckpointRow
                key={profile.id}
                name={pickLocalized(profile.name, lang, profile.id)}
                description={description === "" ? undefined : description}
                isPacked={packedProfileIds.has(profile.id)}
                isActive={selectedDocId === checkpointDocId(profile.id)}
                readiness={ring}
                isPinned={pinnedProfileId === profile.id}
                onTogglePin={
                  onPinProfile
                    ? () => {
                        onPinProfile(
                          pinnedProfileId === profile.id ? null : profile.id,
                        );
                      }
                    : undefined
                }
                onOpen={() => {
                  onOpenCheckpoint(profile.id);
                }}
              />
            );
          })
        )}

        {forms.length > 0 && (
          <>
            <div className="nav-sub">{t("submit.forms")}</div>
            {forms.map((form) => {
              const isActive = selectedDocId === formDocId(form.id);
              const Icon = getFormIcon(form.icon);
              // Точка заполненности: зелёная — анкета валидна; жёлтая — она
              // блокирует упаковку БЛИЖАЙШЕЙ точки и не заполнена; нейтральная
              // — остальное. Раньше жёлтой светилась любая required_for_pack, и
              // «Декларация ИИ» висела блокером с первого дня проекта, хотя в
              // пакет входит только на ПДП и ГИА.
              const sev = form.complete
                ? "ok"
                : activeFormIdSet.has(form.id)
                  ? "warn"
                  : "info";
              const ownerName =
                isTeam && form.owner != null
                  ? (authorNameBySlug.get(form.owner) ?? form.owner)
                  : null;
              const title = pickLocalized(form.title, lang, form.id);
              return (
                <button
                  key={form.id}
                  type="button"
                  className={clsx("row-btn", isActive && "active")}
                  onClick={() => {
                    onOpenForm(form.id);
                  }}
                  title={ownerName == null ? title : `${title} — ${ownerName}`}
                  style={{ alignItems: "center", gap: 8 }}
                >
                  <Icon
                    size={13}
                    style={{
                      flexShrink: 0,
                      color: isActive ? "var(--accent)" : "var(--fg-2)",
                    }}
                  />
                  <span
                    className="truncate"
                    style={{
                      flex: 1,
                      minWidth: 0,
                      fontSize: 12,
                      textAlign: "left",
                    }}
                  >
                    {title}
                  </span>
                  {ownerName != null && (
                    <span
                      className="truncate dim"
                      style={{
                        flexShrink: 1,
                        minWidth: 0,
                        maxWidth: 84,
                        fontSize: 10.5,
                        textAlign: "right",
                      }}
                    >
                      {ownerName}
                    </span>
                  )}
                  <span className={"dot " + sev} style={{ flexShrink: 0 }} />
                </button>
              );
            })}
          </>
        )}

        <div className="nav-sub">{t("submit.signatures")}</div>
        <button
          type="button"
          className={clsx("row-btn", isSignaturesActive && "active")}
          onClick={onOpenSignatures}
          style={{ alignItems: "center", gap: 8 }}
        >
          <PenTool
            size={13}
            style={{
              flexShrink: 0,
              color: isSignaturesActive ? "var(--accent)" : "var(--fg-2)",
            }}
          />
          <span
            className="truncate"
            style={{ flex: 1, minWidth: 0, fontSize: 12, textAlign: "left" }}
          >
            {t("submit.openSignatures")}
          </span>
          {runtimeSlots.length > 0 && (
            <span
              className="mono dim"
              style={{ flexShrink: 0, fontSize: 9.5, letterSpacing: "0.04em" }}
            >
              {signedSlotCount}/{runtimeSlots.length}
            </span>
          )}
        </button>

        {isRequirementsVisible && (
          <>
            <div className="nav-sub">{t("submit.requirements")}</div>
            <button
              type="button"
              className={clsx("row-btn", isRequirementsActive && "active")}
              onClick={onOpenRequirements}
              style={{ alignItems: "center", gap: 8 }}
            >
              <ListCheck
                size={13}
                style={{
                  flexShrink: 0,
                  color: isRequirementsActive ? "var(--accent)" : "var(--fg-2)",
                }}
              />
              <span
                className="truncate"
                style={{
                  flex: 1,
                  minWidth: 0,
                  fontSize: 12,
                  textAlign: "left",
                }}
              >
                {t("submit.openRequirements")}
              </span>
            </button>
          </>
        )}
      </div>
    </div>
  );
};

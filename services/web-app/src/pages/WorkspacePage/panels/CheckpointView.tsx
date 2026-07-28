import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { ClipboardCheck } from "lucide-react";
import { clsx } from "clsx";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { getDocMeta, useDocuments } from "@entities/document";
import { useForms } from "@entities/form";
import { useSignaturesState } from "@entities/signature";
import {
  computeCheckpointReadiness,
  useSubmissionProfiles,
  useSubmissions,
} from "@entities/submission";
import { getFormIcon } from "@features/form-fill";
import { pickLocalized } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { useCheckpointReadiness } from "../lib";
import { CheckpointBuilds } from "./checkpoint/CheckpointBuilds";
import { CheckpointHero } from "./checkpoint/CheckpointHero";
import { CheckpointPackCard } from "./checkpoint/CheckpointPackCard";
import { PageHead } from "./PageHead";
import { SectionCard } from "./SectionCard";

type Project = z.infer<typeof ProjectResponseSchema>;

export type CheckpointViewProps = {
  project: Project;
  profileId: string;
};

const PAGE_STYLE = {
  padding: "24px 32px",
  overflowY: "auto",
  flex: 1,
  minHeight: 0,
} as const;

/**
 * Экран контрольной точки — ответ на вопрос «можно ли сдавать и чего не
 * хватает». Состав точки описывает профиль сдачи (`items`), а состояние —
 * документы, подписи и анкеты проекта; сводит их чистая функция
 * computeCheckpointReadiness, чтобы экран остался разметкой.
 */
export const CheckpointView = ({
  project,
  profileId,
}: CheckpointViewProps): React.JSX.Element => {
  const { t } = useTranslation("workbench");
  const navigate = useNavigate();
  const lang = project.lang ?? "ru";

  const { data: profiles, isLoading: isProfilesLoading } =
    useSubmissionProfiles(project.id);
  const { data: submissions } = useSubmissions(project.id);
  const { data: documents } = useDocuments(project.id);
  const { data: formsData } = useForms(project.id);
  const { data: signaturesState } = useSignaturesState(project.id);
  // Выбор автора общий с панелью «Сдача»: сдача персональная, и экран обязан
  // отвечать на вопрос «можно ли сдавать» про ОДНОГО человека.
  const { authors, isTeam, selectedAuthorSlug, setSelectedAuthorSlug } =
    useCheckpointReadiness(project.id);

  const profile = (profiles ?? []).find((p) => p.id === profileId);

  if (isProfilesLoading) {
    return (
      <div style={PAGE_STYLE}>
        <PageHead icon={ClipboardCheck} title={t("checkpoint.title")} />
        <div className="flex justify-center" style={{ padding: 32 }}>
          <Spinner />
        </div>
      </div>
    );
  }

  // Адрес мог сохраниться в закладке или прийти от агента, а профиль исчезнуть
  // вместе со сменой пака — это не ошибка, а обычная устаревшая ссылка.
  if (!profile) {
    return (
      <div style={PAGE_STYLE}>
        <PageHead icon={ClipboardCheck} title={t("checkpoint.title")} />
        <p className="dim" style={{ marginTop: 24, fontSize: 13 }}>
          {t("submit.noProfiles")}
        </p>
      </div>
    );
  }

  const readiness = computeCheckpointReadiness(
    profile,
    documents ?? [],
    signaturesState,
    formsData?.forms ?? [],
    selectedAuthorSlug,
    // Общий документ команды требует подписи КАЖДОГО автора, поэтому расчёту
    // нужен весь состав, а не только тот, чей пакет сейчас смотрим.
    authors.map((author) => author.slug),
    { kind: project.kind, isNda: project.meta?.nda === true },
  );

  const name = pickLocalized(profile.name, lang, profile.id);
  const description = pickLocalized(profile.description, lang, "");
  const isPacked = (submissions ?? []).some((s) => s.profile_id === profile.id);

  const documentsById = new Map((documents ?? []).map((doc) => [doc.id, doc]));
  const runtimeSlots = signaturesState?.runtime_slots ?? [];
  // Подписи слотов ищем по id ЭКЗЕМПЛЯРА: в команде бэкенд размножает личные
  // слоты по авторам («author--shalaev»), и расчёт уже вернул именно такой id
  // (см. resolveSignatureSlotId) — по каталожному «author» подпись не нашлась
  // бы, и строка показывала бы сырой ASCII.
  const slotLabel = (slotId: string): string => {
    const slot = runtimeSlots.find((s) => s.id === slotId);
    return slot ? pickLocalized(slot.label, lang, slotId) : slotId;
  };

  // Неприменимые пункты (профиль называет документ, которого в этом виде
  // работы нет) скрываем целиком: они не входят в счёт, и студенту с ними
  // нечего делать.
  const items = readiness.items.filter((item) => item.isApplicable);
  // Состав запроса на сборку: те же пункты, что показаны выше, но в терминах
  // профиля (каталожные id подписей). Что применимо — уже решил расчёт, и
  // второго мнения об этом на экране быть не должно.
  const applicableDocIds = new Set(items.map((item) => item.docId));
  const packedItems = (profile.items ?? []).filter((item) =>
    applicableDocIds.has(item.doc_id),
  );
  // Список берём ровно из расчёта, а не фильтруем формы заново: анкета относится
  // к КОНКРЕТНОЙ точке (через extra_items профиля), и повторный отбор по
  // required_for_pack показывал «Декларацию ИИ» на всех точках подряд, хотя в
  // пакет она входит только на ПДП и ГИА.
  const countedFormIds = new Set(readiness.formIds);
  const requiredForms = (formsData?.forms ?? []).filter((form) =>
    countedFormIds.has(form.id),
  );

  return (
    <div style={PAGE_STYLE}>
      <CheckpointHero
        name={name}
        description={description}
        readiness={readiness}
        isPacked={isPacked}
      />

      {/* Точка и её упаковка — один экран. Раньше состав показывался здесь, а
          собрать пакет можно было только на отдельной странице, которая
          повторяла тот же список; справа при этом пустовало пол-экрана. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
          gap: 20,
          marginTop: 24,
          alignItems: "start",
        }}
      >
        <div className="flex flex-col" style={{ gap: 16 }}>
          {items.length > 0 && (
            <SectionCard title={t("checkpoint.sectionDocs")}>
              <div className="flex flex-col">
                {items.map((item) => {
                  // Профиль называет ОПРЕДЕЛЕНИЕ документа, а в проекте лежит
                  // экземпляр («technical_specification--shalaev») — состояние и
                  // ссылка берутся по нему.
                  const doc =
                    item.resolvedDocId == null
                      ? undefined
                      : documentsById.get(item.resolvedDocId);
                  // getDocMeta дописывает ФИО прямо в название; здесь владелец
                  // показан отдельной колонкой, поэтому имя оставляем типовым.
                  const meta = getDocMeta(
                    item.docId,
                    doc ? { ...doc, owner_name: null } : undefined,
                    lang,
                  );
                  const ownerLabel =
                    item.ownerName ?? t("documents.sectionShared");
                  // «warn» у бэкенда означает УСПЕШНУЮ сборку с предупреждениями
                  // проверок, поэтому такой документ собран — жёлтой остаётся
                  // только точка, а подпись честно называет обе вещи сразу.
                  const sev = item.hasErrors
                    ? "err"
                    : item.isBuilt && !item.hasWarnings
                      ? "ok"
                      : "warn";
                  const builtLabel = item.hasWarnings
                    ? `${t("checkpoint.statusBuilt")}, ${t("documents.rollupWarn")}`
                    : t("checkpoint.statusBuilt");
                  const statusLabel = item.hasErrors
                    ? t("checkpoint.statusErrors")
                    : item.isBuilt
                      ? builtLabel
                      : t("checkpoint.statusNotBuilt");
                  // Код документа — маргиналия в левой канавке: коды
                  // выстраиваются в направляющую, и список сканируется, а не
                  // читается построчно.
                  return (
                    <div key={item.docId} className="cp-row">
                      <span className="cp-row-code" title={meta.name}>
                        {meta.code}
                      </span>
                      <span className={clsx("dot", sev)} />
                      <span
                        className="truncate"
                        style={{ minWidth: 0, fontSize: 13 }}
                        title={meta.name}
                      >
                        {meta.name}
                      </span>
                      <span
                        style={{
                          fontSize: 11.5,
                          whiteSpace: "nowrap",
                          color:
                            sev === "err"
                              ? "var(--c-err)"
                              : sev === "warn"
                                ? "var(--c-warn)"
                                : "var(--fg-2)",
                        }}
                      >
                        {statusLabel}
                      </span>
                      {/* Кнопка видна всегда: это единственный путь починить
                          блокер, и прятать его под наведение на экране с
                          высокой ценой ошибки нельзя. */}
                      <button
                        type="button"
                        className="btn xs ghost"
                        onClick={() => {
                          void navigate(
                            `/projects/${project.id}/documents/${item.resolvedDocId ?? item.docId}`,
                          );
                        }}
                      >
                        {t("checkpoint.openDoc")}
                      </button>

                      {(isTeam || item.signatures.length > 0) && (
                        <div className="cp-row-sub">
                          {/* Чей это документ — вопрос номер один в команде: у
                              нескольких авторов строки иначе неотличимы. */}
                          {isTeam && <span>{ownerLabel}</span>}
                          {item.signatures.map((signature) => (
                            <span
                              key={signature.slotId}
                              className="flex items-center"
                              style={{ gap: 5 }}
                            >
                              <span
                                className={clsx(
                                  "dot",
                                  signature.isSigned ? "ok" : "warn",
                                )}
                              />
                              <span
                                style={{
                                  color: signature.isSigned
                                    ? "var(--fg-3)"
                                    : "var(--fg-1)",
                                }}
                              >
                                {slotLabel(signature.slotId)}
                              </span>
                              <span>
                                {signature.isSigned
                                  ? t("checkpoint.signed")
                                  : t("checkpoint.notSigned")}
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}

          {requiredForms.length > 0 && (
            <SectionCard title={t("checkpoint.sectionForms")}>
              <div className="flex flex-col">
                {requiredForms.map((form) => {
                  const Icon = getFormIcon(form.icon);
                  return (
                    <div key={form.id} className="cp-row">
                      <Icon
                        size={13}
                        style={{
                          justifySelf: "end",
                          flexShrink: 0,
                          color: "var(--fg-3)",
                        }}
                      />
                      <span
                        className={clsx("dot", form.complete ? "ok" : "warn")}
                      />
                      <span
                        className="truncate"
                        style={{ minWidth: 0, fontSize: 13 }}
                      >
                        {pickLocalized(form.title, lang, form.id)}
                      </span>
                      <span
                        style={{
                          fontSize: 11.5,
                          whiteSpace: "nowrap",
                          color: form.complete
                            ? "var(--fg-2)"
                            : "var(--c-warn)",
                        }}
                      >
                        {form.complete
                          ? t("formFill:preview.ready")
                          : t("formFill:preview.incomplete")}
                      </span>
                      <button
                        type="button"
                        className="btn xs ghost"
                        onClick={() => {
                          void navigate(
                            `/projects/${project.id}/submit/form/${form.id}`,
                          );
                        }}
                      >
                        {t("checkpoint.openForm")}
                      </button>
                    </div>
                  );
                })}
              </div>
            </SectionCard>
          )}
        </div>

        {/* Липкая: список документов длинный, а кнопка сборки обязана
            оставаться в поле зрения — иначе экран снова распадается на два
            шага, только вертикально. */}
        <div style={{ position: "sticky", top: 0 }}>
          <CheckpointPackCard
            project={project}
            profileId={profileId}
            packedItems={packedItems}
            isTeam={isTeam}
            authors={authors}
            selectedAuthorSlug={selectedAuthorSlug}
            onSelectAuthor={setSelectedAuthorSlug}
          />
        </div>
      </div>

      <CheckpointBuilds project={project} profileId={profileId} />
    </div>
  );
};

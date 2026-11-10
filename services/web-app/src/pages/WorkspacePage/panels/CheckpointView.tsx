import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router";
import { ClipboardCheck } from "lucide-react";
import { clsx } from "clsx";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { getDocMeta, useDocuments } from "@entities/document";
import { useForms } from "@entities/form";
import { useSignaturePlan, useSignaturesState } from "@entities/signature";
import { SIGNING_CARD_ANCHOR } from "@entities/signing-route";
import {
  computeCheckpointReadiness,
  useSubmissionProfiles,
  useSubmissions,
} from "@entities/submission";
import { getFormIcon } from "@features/form-fill";
import { SignSubmissionDialog } from "@features/signature-stamper";
import {
  SigningRouteCard,
  useRouteSlotHints,
} from "@features/signing-route-progress";
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
  // План подписей бэкенда — единственный источник статуса слота: он знает про
  // файл открепленной подписи, устаревшую фиксацию и картинку против ЭП.
  const { data: signaturePlan } = useSignaturePlan(
    project.id,
    profileId,
    isTeam ? selectedAuthorSlug : null,
  );

  const profile = (profiles ?? []).find((p) => p.id === profileId);
  const [isSigning, setIsSigning] = useState(false);
  // Сколько своих слотов можно сделать сейчас: считает сервер, тем же правилом, что и счётчик
  // панели «Сдача». Слот документа идущего маршрута ждёт человека, только когда маршрут ждёт его.
  const waitingForMe = signaturePlan?.waiting_for_me ?? 0;
  // Слоты документов, которые держит идущий маршрут: почему и когда, вместо «устарело».
  const {
    heldDocs,
    heldMine,
    hint: routeHint,
    approvedSlot,
    tally: routeTally,
  } = useRouteSlotHints(project.id, signaturePlan);

  // «Отправить новую версию» у пакета, вкладка «Подписи» документа и уведомления автору ведут к
  // карточке «Подписание» (якорь SIGNING_CARD_ANCHOR): прокручиваем к колонке, где она стоит.
  const location = useLocation();
  const anchored = location.hash === `#${SIGNING_CARD_ANCHOR}`;
  const shown = profile !== undefined;
  useEffect(() => {
    if (!anchored || !shown) return;
    const target = document.getElementById(SIGNING_CARD_ANCHOR);
    // В тестовом окружении (jsdom) прокрутки нет.
    if (target && typeof target.scrollIntoView === "function")
      target.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [anchored, shown, location.key]);

  if (isProfilesLoading) {
    return (
      <div style={PAGE_STYLE}>
        <PageHead icon={ClipboardCheck} title={t("checkpoint.title")} />
        <div className="flex justify-center" style={{ padding: "2rem" }}>
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
        <p
          className="dim"
          style={{ marginTop: "1.5rem", fontSize: "0.8125rem" }}
        >
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
    signaturePlan,
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
        routeTally={routeTally}
      />

      {waitingForMe === 0 && heldMine && (
        <p
          className="dim"
          style={{ fontSize: "0.8125rem", marginTop: "1rem" }}
          data-testid="checkpoint-held-mine"
        >
          {t("signingProgress:wait.heldMine")}
        </p>
      )}
      {waitingForMe > 0 && (
        <div
          className="flex items-center"
          style={{ gap: "0.75rem", marginTop: "1rem" }}
        >
          <span style={{ fontSize: "0.8125rem", color: "var(--accent)" }}>
            {t("signatureStamper:signSubmission.waiting", {
              count: waitingForMe,
            })}
          </span>
          <button
            type="button"
            className="btn primary sm"
            onClick={() => {
              setIsSigning(true);
            }}
          >
            {t("signatureStamper:signSubmission.title")}
          </button>
        </div>
      )}
      {isSigning && (
        <SignSubmissionDialog
          projectId={project.id}
          profileId={profileId}
          author={isTeam ? selectedAuthorSlug : null}
          lang={lang}
          docName={(docId) => {
            const doc = documentsById.get(docId);
            return getDocMeta(
              docId,
              doc ? { ...doc, owner_name: null } : undefined,
              lang,
            ).name;
          }}
          onClose={() => {
            setIsSigning(false);
          }}
        />
      )}

      {/* Точка и её упаковка — один экран. Раньше состав показывался здесь, а
          собрать пакет можно было только на отдельной странице, которая
          повторяла тот же список; справа при этом пустовало пол-экрана. */}
      <div
        className="grid-split"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
          gap: "1.25rem",
          marginTop: "1.5rem",
          alignItems: "start",
        }}
      >
        <div
          id={SIGNING_CARD_ANCHOR}
          className="flex flex-col"
          style={{ gap: "1rem", scrollMarginTop: "1rem" }}
        >
          {/* Маршрут подписания точки: только на сервере, локально карточки нет. */}
          <SigningRouteCard
            project={project}
            profileId={profile.id}
            signatures={readiness.breakdown.signatures}
          />
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
                        style={{ minWidth: 0, fontSize: "0.8125rem" }}
                        title={meta.name}
                      >
                        {meta.name}
                      </span>
                      <span
                        style={{
                          fontSize: "0.71875rem",
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
                          {item.signatures.map((signature) => {
                            const planSlot = signature.plan;
                            const docId = item.resolvedDocId ?? item.docId;
                            // Документ держит идущий маршрут: старая фиксация не беда, маршрут
                            // зафиксирует PDF заново сам, когда все согласуют.
                            const held = heldDocs.has(docId);
                            const refreeze =
                              held && planSlot?.status === "stale";
                            // Подписант согласовал, его ЭП маршрут попросит после фиксации PDF:
                            // это не «ждёт подписи» без причины и не ошибка старой подписи.
                            const approved =
                              !signature.isSigned &&
                              approvedSlot(docId, signature.slotId);
                            const tone = signature.isSigned
                              ? "ok"
                              : approved || refreeze
                                ? "pending"
                                : planSlot?.status === "invalid"
                                  ? "err"
                                  : "warn";
                            const statusText = approved
                              ? t("signingProgress:slotApproved")
                              : refreeze
                                ? t("signingProgress:wait.refreeze")
                                : planSlot
                                  ? t(
                                      `checkpoint.slotStatus.${planSlot.status}`,
                                    )
                                  : signature.isSigned
                                    ? t("checkpoint.signed")
                                    : t("checkpoint.notSigned");
                            const hint =
                              (held
                                ? routeHint(docId, signature.slotId)
                                : null) ??
                              planSlot?.hint ??
                              "";
                            return (
                              <span
                                key={signature.slotId}
                                className="flex flex-col"
                                style={{ gap: "0.125rem" }}
                              >
                                <span
                                  className="flex items-center"
                                  style={{ gap: "0.3125rem" }}
                                >
                                  <span className={clsx("dot", tone)} />
                                  <span
                                    style={{
                                      color: signature.isSigned
                                        ? "var(--fg-3)"
                                        : "var(--fg-1)",
                                    }}
                                  >
                                    {slotLabel(signature.slotId)}
                                    {planSlot?.signer.name
                                      ? ` (${planSlot.signer.name})`
                                      : ""}
                                  </span>
                                  {/* Картинка не выдаётся за ЭП: способ
                                      подписи виден у каждого слота. */}
                                  {planSlot && (
                                    <span
                                      className="chip subtle"
                                      title={
                                        planSlot.crypto
                                          ? t("checkpoint.cryptoHint")
                                          : t("checkpoint.imageHint")
                                      }
                                    >
                                      {t(
                                        `checkpoint.method.${planSlot.method}`,
                                      )}
                                    </span>
                                  )}
                                  <span>{statusText}</span>
                                </span>
                                {!signature.isSigned && hint !== "" && (
                                  <span
                                    className="dim"
                                    style={{ fontSize: "0.6875rem" }}
                                    data-testid={`checkpoint-slot-hint-${docId}-${signature.slotId}`}
                                  >
                                    {hint}
                                  </span>
                                )}
                              </span>
                            );
                          })}
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
                        size="0.8125rem"
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
                        style={{ minWidth: 0, fontSize: "0.8125rem" }}
                      >
                        {pickLocalized(form.title, lang, form.id)}
                      </span>
                      <span
                        style={{
                          fontSize: "0.71875rem",
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

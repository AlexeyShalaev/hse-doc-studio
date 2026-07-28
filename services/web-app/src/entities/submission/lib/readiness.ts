import type { z } from "zod";
import type { SubmissionProfileSchema } from "../api/submissionSchemas";

export type SubmissionProfile = z.infer<typeof SubmissionProfileSchema>;

// Готовность считается по данным трёх соседних сущностей. Тянуть их публичные
// API внутрь submission значило бы связать чистую функцию с react-query, а сам
// расчёт — с формой ответа конкретного эндпоинта. Вместо этого минимальные
// структурные типы (как DocDefLike в entities/document): DocumentResponse,
// SignaturesState и элемент списка форм удовлетворяют им как есть.
export type DocumentLike = {
  // В командном проекте личные документы существуют по экземпляру на автора и
  // называются «<def_id>--<slug>»; в одиночном id совпадает с def_id.
  id: string;
  def_id?: string | null | undefined;
  // slug и ФИО владельца; null — общий документ команды или одиночный проект.
  owner?: string | null | undefined;
  owner_name?: string | null | undefined;
  status: "draft" | "building" | "ok" | "warn" | "err" | "locked";
  errors?: number | null | undefined;
};

export type SignaturePlacementLike = {
  enabled: boolean;
};

/** Слот подписи. png_path === null — картинка ещё не загружена. */
export type SignatureSlotLike = {
  png_path?: string | null | undefined;
};

export type SignaturesStateLike = {
  placements: Record<string, Record<string, SignaturePlacementLike>>;
  // Загруженные PNG по слотам. Включённое размещение без картинки подписью не
  // является: бэкенд при сборке требует и enabled, и png_path
  // (SubmissionService._validated_signatures), иначе упаковка падает.
  slots?: Record<string, SignatureSlotLike> | undefined;
  // Слоты, посчитанные бэкендом для ТЕКУЩЕГО проекта: в команде личные слоты
  // размножены по авторам («author--shalaev»), общие («supervisor») остаются
  // без суффикса. Старый бэкенд их не присылает — см. resolveSignatureSlotIds.
  runtime_slots?: readonly { id: string }[] | undefined;
};

export type FormLike = {
  // В команде анкета размножается по авторам («ai_declaration--shalaev»);
  // базовая часть id совпадает с именем файла в extra_items профиля.
  id: string;
  required_for_pack: boolean;
  complete: boolean;
  // Как и у документов: null — анкета проекта, иначе личная анкета автора.
  owner?: string | null | undefined;
};

export type CheckpointSignatureState = {
  // Реальный слот проекта, в который разрешился пункт профиля: в команде это
  // «<slot_id>--<slug>». По нему же ищется локализованная подпись слота.
  slotId: string;
  isSigned: boolean;
};

export type CheckpointItemState = {
  // Идентификатор ИЗ ПРОФИЛЯ (id определения документа в паке).
  docId: string;
  // Реальный документ проекта, в который разрешился пункт: в команде это
  // «<def_id>--<slug>». Отдаём наружу, чтобы UI подписывал и открывал строку
  // без повторного поиска. null — пункт неприменим.
  resolvedDocId: string | null;
  // ФИО владельца найденного экземпляра: в команде у одного пункта профиля
  // разные документы у разных авторов, и строку нужно чем-то различать.
  ownerName: string | null;
  // false — профиль называет документ, которого в этом проекте нет. Профили
  // сдач общие для всех видов работ, и исследовательский проект законно не
  // содержит части документов прикладного.
  isApplicable: boolean;
  // Документ СОБРАН: бэкенд ставит «warn», когда компиляция прошла, но проверки
  // дали предупреждения (trigger_compile: err → warn → ok), поэтому «warn» —
  // такой же собранный документ, как «ok». Не собран — «draft».
  isBuilt: boolean;
  // Собран, но с предупреждениями проверок: в счёт не влияет, а строку списка
  // подписать «собран» без оговорки было бы неполной правдой.
  hasWarnings: boolean;
  hasErrors: boolean;
  // У неприменимого документа список пуст: в signatures лежат только те слоты,
  // которые реально входят в счёт.
  signatures: CheckpointSignatureState[];
};

/** Пара «сделано / всего» по одной оси счёта. */
export type ReadinessTally = {
  done: number;
  total: number;
};

/**
 * Тот же счёт, что и в кольце, разрезанный по трём осям. Считается В ТЕХ ЖЕ
 * циклах, поэтому сумма трёх пар равна done/total ПО ПОСТРОЕНИЮ, а не по
 * договорённости: экран, показывающий «7/9 документы · 3/4 подписи», не может
 * разойтись с «Готово 10 из 13» над ним. Пересчитать это в вёрстке значило бы
 * завести четвёртый источник истины о готовности.
 */
export type ReadinessBreakdown = {
  documents: ReadinessTally;
  signatures: ReadinessTally;
  forms: ReadinessTally;
};

export type CheckpointReadiness = {
  done: number;
  total: number;
  breakdown: ReadinessBreakdown;
  isComplete: boolean;
  // Бэкенд вправе не прислать items — тогда цифру показывать нельзя вообще:
  // «0 из 0» студент прочитает как «ничего не готово».
  isUnknown: boolean;
  items: CheckpointItemState[];
  // Анкеты, реально входящие в пакет ЭТОЙ точки, — id экземпляров (в команде
  // «ai_declaration--shalaev»). Отдаём наружу, чтобы список на экране физически
  // не мог разойтись со счётом: отфильтровав формы по одному лишь
  // required_for_pack, экран показывал «Декларацию ИИ» на КТ1, где её в пакете
  // нет, — при кольце «Готово 3 из 3», которое её справедливо не считало.
  formIds: string[];
  blockers: number;
};

const EMPTY_TALLY: ReadinessTally = { done: 0, total: 0 };

const UNKNOWN_READINESS: CheckpointReadiness = {
  done: 0,
  total: 0,
  breakdown: {
    documents: EMPTY_TALLY,
    signatures: EMPTY_TALLY,
    forms: EMPTY_TALLY,
  },
  isComplete: false,
  isUnknown: true,
  items: [],
  formIds: [],
  blockers: 0,
};

/**
 * Реальные id слотов подписи, которые обязан закрыть пункт профиля.
 *
 * Профиль сдачи называет слот id из КАТАЛОГА пака («author», «supervisor»), а
 * бэкенд в командном проекте размножает личные слоты по авторам
 * («author--shalaev», «author--ivanov»); общие слоты остаются без суффикса.
 * Сколько получится единиц счёта — решает документ:
 *
 * - ЛИЧНЫЙ документ автора: слот один, его собственный, — чужой не проверяется;
 * - ОБЩИЙ документ команды: личный слот размножен по ВСЕМ авторам, и подписать
 *   обязан каждый. Считать только выбранного значило бы показывать «всё готово»
 *   там, где упаковка упадёт на недостающей подписи соавтора;
 * - слот без личных экземпляров («supervisor») остаётся одной единицей.
 *
 * Список авторов приходит снаружи, а не выводится из документов: у общего
 * документа, созданного до добавления автора, его подписи в размещениях ещё
 * нет, и вывод по данным молча потерял бы этого человека.
 *
 * Источник истины о существовании слота — runtime_slots: бэкенд отдаёт их
 * рассчитанными для этого проекта.
 */
export const resolveSignatureSlotIds = (
  slotId: string,
  authorSlug: string | null | undefined,
  signatures: SignaturesStateLike | undefined,
  doc: DocumentLike,
  authorSlugs: readonly string[],
): string[] => {
  if (authorSlug == null || authorSlug === "") return [slotId];

  const exists = (candidateId: string): boolean =>
    signatures?.runtime_slots?.some((slot) => slot.id === candidateId) ?? false;

  // Владелец есть — документ личный, и слот у него ровно один. Владельца берём
  // у самого документа, а не из выбора: пункт, разрешившийся в чужой экземпляр,
  // не должен превращаться в набор слотов всей команды.
  const owner = doc.owner ?? null;
  if (owner != null && owner !== "") {
    const personalSlotId = `${slotId}--${owner}`;
    return exists(personalSlotId) ? [personalSlotId] : [slotId];
  }

  // Общий документ. Пустой список авторов — вызывающий не знает состава команды;
  // тогда честнее посчитать хотя бы выбранного, чем не посчитать никого.
  const slugs = authorSlugs.length > 0 ? authorSlugs : [authorSlug];
  const perAuthorSlotIds = slugs
    .map((slug) => `${slotId}--${slug}`)
    .filter(exists);
  return perAuthorSlotIds.length > 0 ? perAuthorSlotIds : [slotId];
};

const buildItemState = (
  item: { doc_id: string; signatures: string[] },
  doc: DocumentLike | undefined,
  signatures: SignaturesStateLike | undefined,
  authorSlug: string | null | undefined,
  authorSlugs: readonly string[],
): CheckpointItemState => {
  if (!doc) {
    return {
      docId: item.doc_id,
      resolvedDocId: null,
      ownerName: null,
      isApplicable: false,
      isBuilt: false,
      hasWarnings: false,
      hasErrors: false,
      signatures: [],
    };
  }

  // Размещения подписей лежат под РЕАЛЬНЫМ id документа: в команде это
  // «<def_id>--<slug>», и поиск по id из профиля не нашёл бы ничего.
  // Состояние подписей может ещё грузиться; отсутствующее размещение читается
  // как «не подписано» — вызывающий в это время показывает загрузку.
  const docPlacements = signatures?.placements[doc.id];

  return {
    docId: item.doc_id,
    resolvedDocId: doc.id,
    ownerName: doc.owner_name ?? null,
    isApplicable: true,
    isBuilt: doc.status === "ok" || doc.status === "warn",
    hasWarnings: doc.status === "warn",
    hasErrors: doc.status === "err" || (doc.errors ?? 0) > 0,
    // flatMap, а не map: на общем документе команды один пункт профиля даёт
    // столько единиц, сколько авторов обязаны его подписать.
    signatures: item.signatures.flatMap((slotId) =>
      resolveSignatureSlotIds(
        slotId,
        authorSlug,
        signatures,
        doc,
        authorSlugs,
      ).map((resolvedSlotId) => ({
        slotId: resolvedSlotId,
        // Зеркалим проверку бэкенда: размещение включено И PNG загружен.
        // Иначе кольцо зеленеет на слоте, который студент включил лишь чтобы
        // посмотреть, куда ляжет штамп, — а упаковка потом откажет.
        isSigned:
          docPlacements?.[resolvedSlotId]?.enabled === true &&
          signatures?.slots?.[resolvedSlotId]?.png_path != null,
      })),
    ),
  };
};

/**
 * Готовность точки контроля в рамках ОДНОГО автора.
 *
 * Профиль сдачи перечисляет документы по id ОПРЕДЕЛЕНИЯ («technical_specification»),
 * а в команде реальные документы — это личные экземпляры автора
 * («technical_specification--shalaev»). Поэтому пункт разрешается сначала по
 * паре (def_id, владелец), и только потом по прямому id — так подхватываются
 * общие документы команды и весь одиночный режим.
 *
 * `authorSlug` — тот же выбор «чей пакет собираем», что и на экране «Сдача»:
 * пакет всегда собирается на конкретного автора. Без него (одиночный проект)
 * поиск по владельцу не выполняется вовсе. Слоты подписей разрешаются по тому
 * же автору (см. resolveSignatureSlotIds): в команде они тоже личные.
 *
 * `authorSlugs` — весь состав команды. Нужен ровно для общих документов: их
 * подписывают все авторы сразу, и без списка счёт был бы завышен на подписи,
 * которых ещё нет.
 */
/** Свойства проекта, от которых зависит состав точки. */
export type CheckpointScope = {
  /** project.kind — гейт supported_kinds. Не задан — гейт не применяется. */
  kind?: string | undefined;
  /** project.meta.nda — гейт skip_if_nda. */
  isNda?: boolean | undefined;
};

/**
 * Базовый id без суффикса автора: «ai_declaration--shalaev» → «ai_declaration».
 * Тот же разделитель, которым бэкенд размножает документы и слоты подписи.
 */
const baseId = (id: string): string => id.split("--")[0] ?? id;

/**
 * Анкеты, входящие в пакет этой точки. `extra_items.source` — путь к файлу
 * формы («.hse-studio/forms/ai_declaration.json»), из него берём имя файла без
 * расширения: именно оно совпадает с базовым id формы.
 */
const extraItemFormIds = (
  profile: SubmissionProfile,
  scope: CheckpointScope,
): Set<string> => {
  const ids = new Set<string>();
  for (const extra of profile.extra_items ?? []) {
    // Extra другого вида работы в пакет не попадает — значит и анкету за собой
    // не тянет (create_submission гейтит extras тем же supported_kinds).
    if (scope.kind != null && !extra.supported_kinds.includes(scope.kind)) {
      continue;
    }
    const fileName = extra.source.split("/").pop();
    if (fileName == null || fileName === "") continue;
    ids.add(fileName.replace(/\.[^.]+$/, ""));
  }
  return ids;
};

export const computeCheckpointReadiness = (
  profile: SubmissionProfile,
  documents: DocumentLike[],
  signatures: SignaturesStateLike | undefined,
  forms: FormLike[],
  authorSlug?: string | null,
  authorSlugs: readonly string[] = [],
  scope: CheckpointScope = {},
): CheckpointReadiness => {
  const profileItems = profile.items;
  if (profileItems == null) return UNKNOWN_READINESS;

  // Те же гейты, что применяет бэкенд в build_item_list, и в том же порядке.
  // Пункт, который при сборке пакета будет пропущен, не должен ни попадать в
  // знаменатель, ни висеть блокером: документ у студента есть, а сдавать его
  // на этой точке не нужно.
  const applicableItems = profileItems.filter((item) => {
    if (item.skip_if_nda && scope.isNda === true) return false;
    return scope.kind == null || item.supported_kinds.includes(scope.kind);
  });

  const documentsById = new Map(documents.map((doc) => [doc.id, doc]));
  const ownedByDefId = new Map<string, DocumentLike>();
  if (authorSlug != null) {
    for (const doc of documents) {
      if (doc.def_id != null && doc.owner === authorSlug) {
        ownedByDefId.set(doc.def_id, doc);
      }
    }
  }

  const items = applicableItems.map((item) =>
    buildItemState(
      item,
      ownedByDefId.get(item.doc_id) ?? documentsById.get(item.doc_id),
      signatures,
      authorSlug,
      authorSlugs,
    ),
  );

  let total = 0;
  let done = 0;
  // Разрез того же счёта по осям — накапливаем здесь же, чтобы сумма сходилась
  // с total/done по построению (см. ReadinessBreakdown).
  const docs: { done: number; total: number } = { done: 0, total: 0 };
  const sigs: { done: number; total: number } = { done: 0, total: 0 };
  const formTally: { done: number; total: number } = { done: 0, total: 0 };

  for (const item of items) {
    // Неприменимый документ не увеличивает ни знаменатель, ни число блокеров:
    // студенту нечего с ним делать.
    if (!item.isApplicable) continue;
    total += 1;
    docs.total += 1;
    if (item.isBuilt && !item.hasErrors) {
      done += 1;
      docs.done += 1;
    }
    for (const signature of item.signatures) {
      total += 1;
      sigs.total += 1;
      if (signature.isSigned) {
        done += 1;
        sigs.done += 1;
      }
    }
  }

  // Анкета принадлежит КОНКРЕТНОЙ точке — через extra_items профиля, а не
  // глобальному флагу required_for_pack. Иначе КТ1 показывала бы блокером
  // «Декларацию ИИ», которой в её пакете нет и которая нужна только к КТ4.
  // Общая анкета (owner == null) считается тому автору, чей пакет собираем;
  // чужая личная декларация в его счёт не входит — снять её он не может.
  const profileFormIds = extraItemFormIds(profile, scope);
  const formIds: string[] = [];
  for (const form of forms) {
    if (!form.required_for_pack) continue;
    if (!profileFormIds.has(baseId(form.id))) continue;
    if (form.owner != null && form.owner !== authorSlug) continue;
    formIds.push(form.id);
    total += 1;
    formTally.total += 1;
    if (form.complete) {
      done += 1;
      formTally.done += 1;
    }
  }

  return {
    done,
    total,
    breakdown: { documents: docs, signatures: sigs, forms: formTally },
    formIds,
    // Пустая точка контроля (профиль без items и без обязательных форм) — не
    // «всё готово»: показывать нечего, и об этом говорит отдельное состояние
    // «нет пунктов», а не зелёное кольцо.
    isComplete: total > 0 && done === total,
    isUnknown: false,
    items,
    blockers: total - done,
  };
};

export const pickActiveProfile = (
  profiles: SubmissionProfile[],
  packedProfileIds: string[],
  // undefined допускается наравне с null: закреплённый профиль приходит и из
  // словаря «проект → точка контроля», где чтение по ключу даёт undefined.
  pinnedProfileId: string | null | undefined,
): SubmissionProfile | null => {
  if (profiles.length === 0) return null;

  if (pinnedProfileId != null) {
    const pinned = profiles.find((profile) => profile.id === pinnedProfileId);
    // Закрепление, указывающее на исчезнувший профиль (сменился пак), не должно
    // прятать точку контроля — тогда работает автовыбор ближайшей.
    if (pinned) return pinned;
  }

  const packed = new Set(packedProfileIds);
  const nearest = profiles.find((profile) => !packed.has(profile.id));
  // Всё уже собрано — показываем последнюю: это финальная сдача, к ней и
  // возвращаются, чтобы пересобрать пакет.
  return nearest ?? profiles[profiles.length - 1] ?? null;
};

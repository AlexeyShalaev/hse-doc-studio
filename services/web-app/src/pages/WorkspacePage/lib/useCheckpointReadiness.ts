import { useCallback, useMemo, useState } from "react";
import { useDocuments } from "@entities/document";
import { useForms } from "@entities/form";
import { useProject } from "@entities/project";
import { useSignaturesState } from "@entities/signature";
import {
  computeCheckpointReadiness,
  pickActiveProfile,
  useSubmissionProfiles,
  useSubmissions,
} from "@entities/submission";
import type {
  CheckpointReadiness,
  SubmissionProfile,
} from "@entities/submission";
import { useSubmissionAuthor } from "@shared/lib";

const pinnedStorageKey = (projectId: string): string =>
  `hse-studio.nav.checkpoint.${projectId}`;

const readPinned = (projectId: string): string | null => {
  try {
    return window.localStorage.getItem(pinnedStorageKey(projectId));
  } catch {
    // Приватный режим / переполненное хранилище: закрепление — удобство, а не
    // данные, поэтому молча откатываемся на автовыбор ближайшей точки.
    return null;
  }
};

/** Автор, на которого можно собрать пакет: только управляемая папка со slug. */
export type CheckpointAuthor = {
  slug: string;
  name: string;
};

export type CheckpointReadinessResult = {
  profiles: SubmissionProfile[];
  /** Готовность по каждому профилю; ключ — profile.id. */
  readinessByProfile: Map<string, CheckpointReadiness>;
  /** Профили, для которых уже собран пакет. */
  packedProfileIds: string[];
  /** Точка, по которой считается кольцо и бейдж рейки. */
  activeProfile: SubmissionProfile | null;
  activeReadiness: CheckpointReadiness | null;
  pinnedProfileId: string | null;
  setPinnedProfileId: (profileId: string | null) => void;
  /** Авторы, на которых собирается пакет; в одиночном проекте пуст. */
  authors: CheckpointAuthor[];
  /**
   * Автор, в рамках которого посчитана готовность: его личные документы, общие
   * документы команды и его анкеты. null — одиночный проект.
   */
  selectedAuthorSlug: string | null;
  setSelectedAuthorSlug: (slug: string | null) => void;
  isTeam: boolean;
};

/**
 * Готовность контрольных точек, посчитанная ОДИН раз на уровне страницы.
 *
 * Живёт в pages, а не в entities: расчёт комбинирует четыре разные сущности
 * (submission + document + form + signature), а сущностям запрещено импортировать
 * друг друга. Страница — ближайший слой, которому такая композиция разрешена;
 * результат раздаётся вниз пропсами, чтобы рейка и панель «Сдача» не делали
 * одни и те же запросы дважды.
 *
 * Сдача всегда персональная: в команде документы существуют по экземпляру на
 * автора («technical_specification--shalaev»), поэтому готовность считается для
 * ОДНОГО выбранного автора — того же, что выбирается на экране упаковки.
 */
export const useCheckpointReadiness = (
  projectId: string,
): CheckpointReadinessResult => {
  const { data: project } = useProject(projectId);
  const { data: profiles } = useSubmissionProfiles(projectId);
  const { data: submissions } = useSubmissions(projectId);
  const { data: documents } = useDocuments(projectId);
  const { data: formsData } = useForms(projectId);
  const { data: signatures } = useSignaturesState(projectId);

  // Закрепление читается лениво из localStorage: пользователь выбрал ручной
  // режим выбора точки, авто-ближайшая осталась фолбэком.
  const [pinnedProfileId, setPinnedState] = useState<string | null>(() =>
    readPinned(projectId),
  );

  const setPinnedProfileId = useCallback(
    (next: string | null): void => {
      setPinnedState(next);
      try {
        if (next === null) {
          window.localStorage.removeItem(pinnedStorageKey(projectId));
        } else {
          window.localStorage.setItem(pinnedStorageKey(projectId), next);
        }
      } catch {
        // См. readPinned: сбой хранилища не должен ломать переключение.
      }
    },
    [projectId],
  );

  // Кандидаты те же, что на экране упаковки: неуправляемые папки приложение не
  // разворачивает, собрать по ним пакет нельзя.
  const authors = useMemo<CheckpointAuthor[]>(
    () =>
      (project?.authors ?? []).flatMap((author) =>
        author.managed && author.slug != null && author.slug !== ""
          ? [{ slug: author.slug, name: author.name }]
          : [],
      ),
    [project],
  );
  const authorSlugs = useMemo(
    () => authors.map((author) => author.slug),
    [authors],
  );

  // ВТОРОЙ, более широкий список — для размножения слотов подписи. Бэкенд
  // (SignatureSlotService.runtime_slots) перебирает ВСЕХ авторов проекта и
  // отсеивает только бесслаговых, про `managed` там речи нет. Считать общий
  // документ подписанным, пропустив неведомого соавтора, значит показать
  // «всё готово» там, где упаковка упадёт.
  const signatureAuthorSlugs = useMemo(
    () =>
      (project?.authors ?? []).flatMap((author) =>
        author.slug != null && author.slug !== "" ? [author.slug] : [],
      ),
    [project],
  );

  // Выбор автора — общий стор: экран упаковки собирает пакет ровно на того
  // человека, про которого экран контрольной точки только что показал цифру.
  // Откат на первого автора, если сохранённый исчез, живёт там же.
  const { selectedAuthorSlug: authorSlug, setSelectedAuthorSlug } =
    useSubmissionAuthor(projectId, authorSlugs);

  // Признак команды берём из staffing, как PackView: у команды документы личные
  // даже когда в ней временно остался один автор, и считать её одиночной значило
  // бы снова потерять их из счёта.
  const isTeam = authors.length > 0 && project?.staffing === "team";

  const selectedAuthorSlug = isTeam ? authorSlug : null;

  return useMemo(() => {
    const allProfiles = profiles ?? [];
    const docs = documents ?? [];
    const forms = formsData?.forms ?? [];
    const packedProfileIds = (submissions ?? [])
      .map((record) => record.profile_id)
      .filter((id): id is string => typeof id === "string" && id.length > 0);

    const readinessByProfile = new Map<string, CheckpointReadiness>();
    for (const profile of allProfiles) {
      readinessByProfile.set(
        profile.id,
        computeCheckpointReadiness(
          profile,
          docs,
          signatures,
          forms,
          selectedAuthorSlug,
          // Состав команды нужен целиком: общий документ подписывают ВСЕ авторы,
          // и по одному выбранному кольцо было бы завышенным.
          signatureAuthorSlugs,
          // Вид работы и NDA — те же гейты, что у бэкенда: пункт другого вида
          // или снятый под NDA не должен ни считаться, ни висеть блокером.
          { kind: project?.kind, isNda: project?.meta?.nda === true },
        ),
      );
    }

    const activeProfile = pickActiveProfile(
      allProfiles,
      packedProfileIds,
      pinnedProfileId,
    );

    return {
      profiles: allProfiles,
      readinessByProfile,
      packedProfileIds,
      activeProfile,
      activeReadiness: activeProfile
        ? (readinessByProfile.get(activeProfile.id) ?? null)
        : null,
      pinnedProfileId,
      setPinnedProfileId,
      authors,
      selectedAuthorSlug,
      setSelectedAuthorSlug,
      isTeam,
    };
  }, [
    signatureAuthorSlugs,
    project?.kind,
    project?.meta?.nda,
    authors,
    documents,
    formsData,
    isTeam,
    pinnedProfileId,
    profiles,
    selectedAuthorSlug,
    setPinnedProfileId,
    setSelectedAuthorSlug,
    signatures,
    submissions,
  ]);
};

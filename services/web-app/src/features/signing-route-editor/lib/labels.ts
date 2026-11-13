import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { ParticipantMembership } from "@entities/signing-route";
import {
  DEFAULT_DEADLINE_TIME,
  deadlineFromInput,
  deadlineToInput,
} from "@entities/submission";

type Author = {
  slug?: string | null | undefined;
  name?: string | null | undefined;
};

const SUPERVISOR = new Set([
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
]);

/**
 * Название персоны: «Автор», роль руководителя или имя автора команды (персона это его слаг).
 * Те же подписи, что у формы приглашения.
 */
export const usePersonaLabel = (
  authors: readonly Author[] | null | undefined,
) => {
  const { t } = useTranslation("signingRouteEditor");
  return useCallback(
    (persona: string): string => {
      if (persona === "author") return t("persona.author");
      if (SUPERVISOR.has(persona)) return t(`invitations:persona.${persona}`);
      const name = authors?.find((a) => a.slug === persona)?.name;
      return name != null && name !== "" ? name : persona;
    },
    [authors, t],
  );
};

export const MEMBERSHIP_TONE: Record<ParticipantMembership, string> = {
  member: "var(--c-ok)",
  invited: "var(--c-info)",
  missing: "var(--c-warn)",
};

/**
 * Срок маршрута: дата в поле, конец этого дня по Москве в контракте (пояс отображения, 14.4; так
 * же вводится срок точки, 16.3). Пустое поле или неразборчивая дата значат «без срока».
 */
export const deadlineToIso = (day: string): string | null =>
  day === "" ? null : deadlineFromInput(day, DEFAULT_DEADLINE_TIME);

/** День срока маршрута по Москве для поля даты; без срока пусто. */
export const isoToDeadline = (iso: string | null): string =>
  deadlineToInput(iso).date;

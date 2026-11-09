import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import type { ParticipantMembership } from "@entities/signing-route";

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

/** Срок маршрута: дата в поле, конец этого дня по местному времени в контракте (ISO UTC). */
export const deadlineToIso = (day: string): string | null => {
  if (day === "") return null;
  const at = new Date(`${day}T23:59:00`);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
};

export const isoToDeadline = (iso: string | null): string => {
  if (iso === null) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(at.getFullYear())}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
};

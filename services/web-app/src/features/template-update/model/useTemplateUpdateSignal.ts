import { useTemplateUpdateStatus } from "@entities/template-update";
import type { AvailableUpdate } from "@entities/template-update";

export type TemplateUpdateSignal = {
  /** Версия шаблона, на которой проект сейчас. */
  currentVersion: string;
  /** Что предложить: последний patch, иначе minor, иначе major (из статуса). */
  update: AvailableUpdate | null;
  /** Файлы последнего обновления, где ещё стоят маркеры конфликта. */
  markers: string[];
  /** Есть ли повод привлечь внимание: обновление или недоразрешённый конфликт. */
  hasSignal: boolean;
};

const EMPTY: TemplateUpdateSignal = {
  currentVersion: "",
  update: null,
  markers: [],
  hasSignal: false,
};

/**
 * Единый источник «шаблону есть что сказать» для бейджей рейки, оглавления
 * настроек, строки состояния и уведомления при открытии проекта — чтобы все
 * они загорались и гасли одновременно.
 */
export const useTemplateUpdateSignal = (
  projectId: string,
): TemplateUpdateSignal => {
  const { data } = useTemplateUpdateStatus(projectId);
  if (!data || data.in_progress) return EMPTY;
  const update = data.recommended ?? null;
  const markers = data.unresolved_markers;
  return {
    currentVersion: data.current_version,
    update,
    markers,
    hasSignal: update !== null || markers.length > 0,
  };
};

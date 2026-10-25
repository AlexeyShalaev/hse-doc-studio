import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { useTemplateUpdateSignal } from "../model/useTemplateUpdateSignal";
import { isDismissed } from "./templateUpdate.model";

// Уже показанные уведомления — по проекту и версии, на сессию браузера: при
// каждом переходе между документами одно и то же «вышло обновление» раздражало бы.
const SHOWN_KEY = "hse-studio.template-update.notified";

const wasShown = (key: string): boolean => {
  try {
    return (sessionStorage.getItem(SHOWN_KEY) ?? "").split("\n").includes(key);
  } catch {
    return false;
  }
};

const markShown = (key: string): void => {
  try {
    const prev = sessionStorage.getItem(SHOWN_KEY);
    sessionStorage.setItem(SHOWN_KEY, prev ? `${prev}\n${key}` : key);
  } catch {
    // Хранилище недоступно — уведомление просто может повториться.
  }
};

/**
 * Уведомление при открытии проекта: «вышли исправления шаблона» (только patch —
 * новое и новая редакция не навязываются) и «в файлах остались маркеры
 * конфликта». Один раз за сессию на версию; скрытая на обзоре версия молчит.
 */
export const useTemplateUpdateToast = (
  projectId: string,
  onOpen: () => void,
): void => {
  const { t } = useTranslation("templateUpdate");
  const { update, markers } = useTemplateUpdateSignal(projectId);
  const patchVersion =
    update?.update_class === "patch" ? update.version.version : null;

  useEffect(() => {
    if (markers.length > 0) {
      const key = `${projectId}:markers:${markers.join(",")}`;
      if (wasShown(key)) return;
      markShown(key);
      toast.warning(t("notify.markers", { count: markers.length }), {
        title: t("notify.markersTitle"),
        duration: 10_000,
        action: { label: t("notify.open"), onClick: onOpen },
      });
      return;
    }
    if (!patchVersion || isDismissed(projectId, patchVersion)) return;
    const key = `${projectId}:${patchVersion}`;
    if (wasShown(key)) return;
    markShown(key);
    toast.info(t("notify.patch", { version: patchVersion }), {
      title: t("card.title"),
      duration: 10_000,
      action: { label: t("notify.open"), onClick: onOpen },
    });
    // onOpen — новая функция на каждый рендер; уведомление зависит только от данных.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, patchVersion, markers.join(",")]);
};

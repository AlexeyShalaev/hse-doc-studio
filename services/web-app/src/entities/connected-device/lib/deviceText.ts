import type { TFunction } from "i18next";
import { formatPastTime } from "@shared/lib";
import type { Device } from "../model/device.schema";

/** «в сети» или «была в сети 5 минут назад»: возраст считается по часам клиента. */
export const presenceText = (
  t: TFunction,
  device: Pick<Device, "presence" | "last_seen_at">,
  now: number,
): string =>
  device.presence === "online"
    ? t("presence.online")
    : t("presence.offlineAgo", {
        when: formatPastTime(device.last_seen_at, now),
      });

/** Число коммитов со склонением. */
export const commitsText = (t: TFunction, count: number): string =>
  t("card.commits", { count });

/** Первые модели списком, остальные счётчиком: панель остаётся компактной. */
export const modelNames = (
  t: TFunction,
  models: readonly string[],
  limit = 3,
): string =>
  models.length <= limit
    ? models.join(", ")
    : t("ai.moreModels", {
        models: models.slice(0, limit).join(", "),
        count: models.length - limit,
      });

export const modelsText = (
  t: TFunction,
  models: readonly string[],
  limit = 3,
): string => t("ai.models", { models: modelNames(t, models, limit) });

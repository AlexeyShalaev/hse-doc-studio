import type { TFunction } from "i18next";
import type {
  Device,
  LinkServer,
  ProjectStudios,
  StudioLink,
} from "@entities/connected-device";

/** Тон плашки: цвет только подчёркивает, смысл несут точка и слова. */
export type PresenceTone = "ok" | "info" | "warn" | "err" | "quiet";

export type PresenceSummary = {
  tone: PresenceTone;
  label: string;
  /** Для скринридера и подсказки: то же, что на плашке, без сокращений. */
  title: string;
  online: boolean;
};

const online = (device: Device): boolean => device.presence === "online";

/** Облако: плашка по Студиям проекта; null, когда показывать нечего (ни своих Студий, ни работающих локально). */
export const cloudSummary = (
  t: TFunction,
  studios: ProjectStudios | undefined,
): PresenceSummary | null => {
  if (studios === undefined) return null;
  const mine = studios.mine;
  const live = mine.filter(online);
  if (mine.length > 0) {
    const first = live[0] ?? mine[0];
    if (first === undefined) return null;
    const label =
      live.length > 1
        ? t("badge.cloudOnlineMany", { count: live.length })
        : live.length === 1
          ? t("badge.cloudOnline", { name: first.name })
          : mine.length > 1
            ? t("badge.cloudOfflineMany", { count: mine.length })
            : t("badge.cloudOffline", { name: first.name });
    const attention = live.some((d) => d.ai.state === "no_provider");
    return {
      tone: live.length > 0 ? (attention ? "info" : "ok") : "quiet",
      label,
      title: label,
      online: live.length > 0,
    };
  }
  if (studios.others.length > 0) {
    const names = studios.others.map((p) => p.name).join(", ");
    const label =
      studios.others.length === 1
        ? t("badge.othersLocal", { names })
        : t("badge.othersLocalMany", { count: studios.others.length });
    return { tone: "info", label, title: label, online: true };
  }
  return null;
};

/** Сервер локальной Студии, о котором говорит плашка: первый рабочий, иначе первый. */
export const pickServer = (link: StudioLink | undefined): LinkServer | null => {
  if (link === undefined) return null;
  return link.servers.find((s) => s.state === "ok") ?? link.servers[0] ?? null;
};

/** Локальная Студия: плашка о связи с облаком; null, если проект не подключён к облаку. */
export const localSummary = (
  t: TFunction,
  link: StudioLink | undefined,
): PresenceSummary | null => {
  if (link === undefined || link.project === null) return null;
  const server = pickServer(link);
  if (server === null) return null;
  const make = (tone: PresenceTone, label: string, up: boolean) => ({
    tone,
    label,
    title: label,
    online: up,
  });
  if (server.state === "expired") {
    return make("err", t("badge.localExpired"), false);
  }
  if (server.state === "revoked") {
    return make("err", t("badge.localRevoked"), false);
  }
  if (server.state === "unreachable" || server.cloud_error !== null) {
    return make("warn", t("badge.localUnreachable"), false);
  }
  if (server.cloud?.device?.presence === "online") {
    return make("ok", t("badge.localOnline"), true);
  }
  return make("warn", t("badge.localSeen"), false);
};

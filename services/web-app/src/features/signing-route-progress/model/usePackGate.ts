import { useTranslation } from "react-i18next";
import { useBootstrap } from "@entities/session";
import { useSignaturePlan } from "@entities/signature";
import {
  signingCardPath,
  useSigningRoutes,
  type SigningRouteSummary,
} from "@entities/signing-route";
import { endSentence } from "@shared/lib";
import { pickCurrentRoute } from "../lib/routeView";
import { useWaitText } from "../lib/useWaitText";

/** Строка готовности пакета: блокирует сборку (`err`) или только предупреждает (`warn`). */
export type PackGateRow = {
  key: "route" | "signatures";
  tone: "err" | "warn";
  text: string;
  /** Куда идти чинить: карточка «Подписание» этой точки; null, если ссылки нет. */
  link: string | null;
};

export type PackGate = {
  /** Пакет сейчас не собрать: сервер откажет. Кнопка «Упаковать» выключена. */
  blocked: boolean;
  /** Почему, для подсказки кнопки; null, если не заблокировано. */
  reason: string | null;
  rows: PackGateRow[];
};

type OpenRoute = SigningRouteSummary & {
  status: "active" | "paused" | "returned";
};

const isOpen = (route: SigningRouteSummary | null): route is OpenRoute =>
  route !== null &&
  (route.status === "active" ||
    route.status === "paused" ||
    route.status === "returned");

export type UsePackGateArgs = {
  project: { id: string };
  profileId: string;
  /** Автор пакета в команде; null у одиночного проекта. */
  author: string | null;
};

/**
 * Можно ли собрать пакет точки (docs/design/signing-route.md, 12.8.1). Пакет требует все
 * обязательные подписи точки готовыми по плану подписей: сервер иначе откажет, поэтому кнопка
 * выключается заранее, а не показывает ошибку после нажатия. Частая причина неготовности
 * маршрут подписания, который ещё идёт, остановлен или возвращён: тогда строка называет его и
 * того, кого ждём. Если обязательные подписи уже готовы, а маршрут ждёт необязательных,
 * строка только предупреждает.
 */
export const usePackGate = ({
  project,
  profileId,
  author,
}: UsePackGateArgs): PackGate => {
  const { t } = useTranslation("signingProgress");
  const waitText = useWaitText();
  const boot = useBootstrap().data;
  // Маршруты есть только на сервере и только вошедшему (раздел 7), как у карточки «Подписание».
  const isServer = boot?.mode === "server" && boot.user !== null;
  const { data: plan } = useSignaturePlan(project.id, profileId, author);
  const { data: routes } = useSigningRoutes(project.id, profileId, {
    enabled: isServer,
  });
  const current = pickCurrentRoute(routes?.items ?? []);
  const route = isOpen(current) ? current : null;

  const unsigned =
    plan !== undefined && plan.total > plan.signed
      ? { done: plan.signed, total: plan.total }
      : null;
  // Без плана (ещё грузится или недоступен) незавершённый маршрут считается помехой: так
  // ответит и сервер, ведь его подписи ещё не поставлены.
  const routeBlocks =
    route !== null && (plan === undefined || unsigned !== null);

  const rows: PackGateRow[] = [];
  if (route !== null) {
    const link = signingCardPath(project.id, profileId);
    const who = route.waiting_for
      .map((p) =>
        waitText.who({
          name: p.name,
          cardName: null,
          persona: p.persona,
          state: "to_approve",
        }),
      )
      .join(", ");
    const text = (() => {
      if (route.status === "paused") return t("pack.paused");
      if (route.status === "returned") return t("pack.returned");
      const step = {
        step: route.current_step ?? route.steps_total,
        total: route.steps_total,
      };
      if (!routeBlocks)
        return who === ""
          ? t("pack.optionalStep", step)
          : t("pack.optional", { ...step, who });
      return who === ""
        ? t("pack.activeStep", step)
        : endSentence(t("pack.active", { ...step, who }));
    })();
    rows.push({ key: "route", tone: routeBlocks ? "err" : "warn", text, link });
  } else if (unsigned !== null) {
    rows.push({
      key: "signatures",
      tone: "err",
      text: t("pack.unsigned", unsigned),
      link: null,
    });
  }

  const blocked = routeBlocks || unsigned !== null;
  const reason = blocked ? (rows[0]?.text ?? null) : null;
  return { blocked, reason, rows };
};

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarClock, TriangleAlert } from "lucide-react";
import {
  formatDeadlineDay,
  routeDeadlineFromPoint,
  sameMoment,
} from "@entities/submission";
import { useDeadlineText } from "../lib/useDeadlineText";
import {
  CheckpointDeadlineLine,
  type CheckpointDeadlineProfile,
} from "./CheckpointDeadlineLine";

export type RoutePointDeadlineProps = {
  projectId: string;
  /** Профиль точки маршрута со сроком; пока профили грузятся, undefined. */
  profile: CheckpointDeadlineProfile | undefined;
  /** Нынешний срок маршрута. */
  routeDeadline: string | null;
  /**
   * Срок точки, из которого сервер посчитал срок черновика (R29). undefined, пока сервер поля не
   * присылает: тогда «Срок точки изменился» не определить, и редактор только предлагает срок.
   */
  pointDeadlineAtDraft: string | null | undefined;
  /** Маршрут можно править и человек управляет им: можно «Поставить» и указать срок точки. */
  canEdit: boolean;
  /** «Поставить»: срок маршрута из срока точки (16.5). */
  onApply: (deadline: string) => void;
  busy?: boolean;
  now?: number;
};

const LINE = { gap: "0.375rem", fontSize: "0.71875rem" } as const;

/**
 * Срок точки в блоке срока маршрута «Отправить на подписание» (docs/design/signing-route.md, 16.2
 * и 16.5). Есть срок точки: откуда взят срок маршрута, «Поставить», если срок маршрута пуст или
 * срок точки изменился, и предупреждение, если срок маршрута позже срока сдачи. Нет срока точки:
 * та же мягкая строка, что на точке, с полем и «Указать срок».
 */
export const RoutePointDeadline = ({
  projectId,
  profile,
  routeDeadline,
  pointDeadlineAtDraft,
  canEdit,
  onApply,
  busy = false,
  now: fixedNow,
}: RoutePointDeadlineProps) => {
  const { t } = useTranslation("checkpointDeadline");
  const [openedAt] = useState(() => Date.now());
  const now = fixedNow ?? openedAt;
  const text = useDeadlineText();
  if (!profile) return null;

  const point = profile.deadline;
  if (point === null) {
    return (
      <CheckpointDeadlineLine
        projectId={projectId}
        profile={profile}
        canEdit={canEdit}
        now={now}
      />
    );
  }

  const pointText = text.at(point, now);
  const day = (iso: string) => formatDeadlineDay(iso, now);
  const suggest = routeDeadlineFromPoint(point, now);
  const routeLater =
    routeDeadline !== null && Date.parse(routeDeadline) > Date.parse(point);

  const offer = (key: "route.suggest" | "route.changed", target: string) => (
    <span
      className="flex items-center"
      style={{ ...LINE, flexWrap: "wrap" }}
      data-testid="route-point-offer"
    >
      <CalendarClock size="0.75rem" aria-hidden="true" />
      <span>{t(key, { point: day(point), route: day(target) })}</span>
      <button
        type="button"
        className="btn xs"
        disabled={busy}
        onClick={() => {
          onApply(target);
        }}
        data-testid="route-point-apply"
      >
        {t("route.apply")}
      </button>
    </span>
  );

  let main: React.ReactNode;
  if (suggest === null) {
    main = (
      <span className="flex items-center dim" style={LINE}>
        <CalendarClock size="0.75rem" aria-hidden="true" />
        {t("route.passed", { point: pointText })}
      </span>
    );
  } else if (routeDeadline !== null && sameMoment(routeDeadline, suggest)) {
    main = (
      <span className="flex items-center dim" style={LINE}>
        <CalendarClock size="0.75rem" aria-hidden="true" />
        {sameMoment(suggest, point)
          ? t("route.same", { point: pointText })
          : t("route.derived", {
              route: text.at(suggest, now),
              point: day(point),
            })}
      </span>
    );
  } else if (
    canEdit &&
    pointDeadlineAtDraft != null &&
    !sameMoment(pointDeadlineAtDraft, point)
  ) {
    main = offer("route.changed", suggest);
  } else if (canEdit && routeDeadline === null) {
    main = offer("route.suggest", suggest);
  } else {
    main = (
      <span className="flex items-center dim" style={LINE}>
        <CalendarClock size="0.75rem" aria-hidden="true" />
        {t("route.point", { point: pointText })}
      </span>
    );
  }

  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.25rem" }}
      data-testid="route-point-deadline"
    >
      {main}
      {routeLater && (
        <span
          className="flex items-center"
          style={{ ...LINE, color: "var(--c-warn)" }}
          data-testid="route-point-later"
        >
          <TriangleAlert size="0.75rem" aria-hidden="true" />
          {t("route.later")}
        </span>
      )}
    </div>
  );
};

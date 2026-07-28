import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { Pin } from "lucide-react";

/**
 * Готовность контрольной точки: сколько её пунктов уже собрано/подписано.
 * Считает НЕ строка, а страница (useCheckpointReadiness): расчёт комбинирует
 * четыре сущности сразу. Проп необязателен, потому что бэкенд может не прислать
 * `items` профиля (SubmissionProfileSchema.items = .nullish()) — тогда кольца
 * нет вовсе, «0 из 0» было бы враньём.
 */
export type CheckpointReadiness = {
  done: number;
  total: number;
};

export type CheckpointRowProps = {
  /** Локализованное имя профиля сдачи («КТ1», «Заявление на ПДП»…). */
  name: string;
  /** Локализованное описание — уходит в подсказку, строка узкая. */
  description?: string | undefined;
  /** Пакет по этому профилю уже собирали (есть запись в /submissions). */
  isPacked: boolean;
  isActive: boolean;
  /** Не передаётся, когда бэкенд не описал состав точки (items == null). */
  readiness?: CheckpointReadiness | undefined;
  /** Закреплена пользователем — по ней считается бейдж рейки. */
  isPinned?: boolean | undefined;
  onTogglePin?: (() => void) | undefined;
  onOpen: () => void;
};

const RING_BOX = 18;
const RING_RADIUS = 7;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

const ReadinessRing = ({ done, total }: CheckpointReadiness) => {
  const ratio = total > 0 ? Math.min(1, Math.max(0, done / total)) : 0;
  const isDone = total > 0 && done >= total;
  return (
    <span className="readiness" style={{ flexShrink: 0, gap: 5 }}>
      <svg
        className="readiness-ring"
        width={RING_BOX}
        height={RING_BOX}
        viewBox={`0 0 ${String(RING_BOX)} ${String(RING_BOX)}`}
        aria-hidden="true"
      >
        <circle
          className="readiness-track"
          cx={RING_BOX / 2}
          cy={RING_BOX / 2}
          r={RING_RADIUS}
        />
        <circle
          className={clsx("readiness-value", isDone && "done")}
          cx={RING_BOX / 2}
          cy={RING_BOX / 2}
          r={RING_RADIUS}
          strokeDasharray={RING_LENGTH}
          strokeDashoffset={RING_LENGTH * (1 - ratio)}
        />
      </svg>
      <span className="mono dim" style={{ fontSize: 9.5 }}>
        {done}/{total}
      </span>
    </span>
  );
};

/**
 * Одна контрольная точка в панели «Сдача». Состояние строки читается точкой
 * слева: зелёная — пакет уже собран, нейтральная — точка ещё впереди.
 */
export const CheckpointRow = ({
  name,
  description,
  isPacked,
  isActive,
  readiness,
  isPinned = false,
  onTogglePin,
  onOpen,
}: CheckpointRowProps) => {
  const { t } = useTranslation("workbench");

  // Кнопка закрепления — СОСЕД строки, а не вложенная кнопка: <button> внутри
  // <button> невалиден и ломает клавиатуру. Тот же приём, что у меню документа.
  return (
    <div className="flex items-center" style={{ gap: 2 }}>
      <button
        type="button"
        className={clsx("row-btn", isActive && "active")}
        onClick={onOpen}
        title={description ?? name}
        aria-label={`${name} — ${t("submit.openCheckpoint")}`}
        style={{ alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}
      >
        <span
          className={clsx("dot", isPacked ? "ok" : "info")}
          style={{ flexShrink: 0 }}
        />
        <span
          style={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            gap: 1,
          }}
        >
          <span className="truncate" style={{ fontSize: 12, lineHeight: 1.3 }}>
            {name}
          </span>
          {isPacked && (
            <span
              className="mono dim"
              style={{ fontSize: 9, letterSpacing: "0.06em" }}
            >
              {t("submit.packed")}
            </span>
          )}
        </span>
        {readiness != null && (
          <ReadinessRing done={readiness.done} total={readiness.total} />
        )}
      </button>
      {onTogglePin && (
        <button
          type="button"
          className={clsx("icon-btn sm tt", isPinned && "active")}
          data-tt={
            isPinned ? t("submit.unpinCheckpoint") : t("submit.pinCheckpoint")
          }
          aria-label={
            isPinned ? t("submit.unpinCheckpoint") : t("submit.pinCheckpoint")
          }
          aria-pressed={isPinned}
          onClick={onTogglePin}
          style={{
            flexShrink: 0,
            color: isPinned ? "var(--accent)" : undefined,
          }}
        >
          <Pin size={12} />
        </button>
      )}
    </div>
  );
};

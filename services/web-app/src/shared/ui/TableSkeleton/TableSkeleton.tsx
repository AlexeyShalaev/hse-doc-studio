import { useTranslation } from "react-i18next";

// Скелет таблицы или списка на время первой загрузки: строки с полосами
// разной длины, чтобы не мерцало пустотой и не прыгала высота.

export type TableSkeletonProps = {
  rows?: number | undefined;
  columns?: number | undefined;
  /** Первая колонка с кружком аватара: для списков людей. */
  withAvatar?: boolean | undefined;
  /** В рамке карточки, как DataTable. */
  framed?: boolean | undefined;
  testId?: string | undefined;
};

const width = (row: number, col: number): string =>
  `${String(40 + ((row * 17 + col * 29) % 45))}%`;

export const TableSkeleton = ({
  rows = 5,
  columns = 4,
  withAvatar = false,
  framed = true,
  testId,
}: TableSkeletonProps) => {
  const { t } = useTranslation("uiPrimitives");
  return (
    <div
      role="status"
      aria-label={t("adminKit.loading")}
      data-testid={testId}
      className={framed ? "card" : undefined}
      style={{ overflow: "hidden" }}
    >
      {Array.from({ length: rows }, (_, row) => (
        <div
          key={row}
          aria-hidden="true"
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${String(columns)}, minmax(0, 1fr))`,
            gap: 16,
            alignItems: "center",
            padding: "14px 16px",
            borderTop: row === 0 ? 0 : "1px solid var(--border)",
          }}
        >
          {Array.from({ length: columns }, (_, col) =>
            col === 0 && withAvatar ? (
              <span key={col} className="flex items-center" style={{ gap: 10 }}>
                <span
                  className="adm-skel"
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: "50%",
                    flexShrink: 0,
                  }}
                />
                <span className="adm-skel" style={{ width: width(row, 0) }} />
              </span>
            ) : (
              <span
                key={col}
                className="adm-skel"
                style={{ width: width(row, col) }}
              />
            ),
          )}
        </div>
      ))}
    </div>
  );
};

TableSkeleton.displayName = "TableSkeleton";

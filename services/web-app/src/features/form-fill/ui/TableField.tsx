import { useTranslation } from "react-i18next";
import { Plus, X } from "lucide-react";
import type { FormColumn } from "@entities/form";
import { loc } from "../lib/forms";

type TableRow = Record<string, string>;

export type TableFieldProps = {
  columns: readonly FormColumn[];
  rows: readonly TableRow[];
  lang: string;
  onChange: (rows: TableRow[]) => void;
};

/**
 * Repeatable rows over pack-declared columns. Generic add/remove-row grid —
 * the columns come from the form schema, nothing is hardcoded.
 */
export const TableField = ({
  columns,
  rows,
  lang,
  onChange,
}: TableFieldProps) => {
  const { t } = useTranslation("formFill");
  const emptyRow = (): TableRow =>
    Object.fromEntries(columns.map((c) => [c.id, ""]));

  const handleCell = (rowIndex: number, columnId: string, value: string) => {
    onChange(
      rows.map((row, i) =>
        i === rowIndex ? { ...row, [columnId]: value } : row,
      ),
    );
  };

  const handleAdd = () => {
    onChange([...rows, emptyRow()]);
  };

  const handleRemove = (rowIndex: number) => {
    onChange(rows.filter((_, i) => i !== rowIndex));
  };

  return (
    <div className="flex flex-col gap-2">
      <div
        className="mono dim"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${String(columns.length)}, 1fr) 28px`,
          gap: 6,
          fontSize: 10.5,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        {columns.map((col) => (
          <span key={col.id}>{loc(col.label, lang)}</span>
        ))}
        <span />
      </div>

      {rows.map((row, rowIndex) => (
        <div
          key={rowIndex}
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${String(columns.length)}, 1fr) 28px`,
            gap: 6,
            alignItems: "center",
          }}
        >
          {columns.map((col) => (
            <input
              key={col.id}
              type="text"
              className="input"
              value={row[col.id] ?? ""}
              onChange={(e) => {
                handleCell(rowIndex, col.id, e.target.value);
              }}
            />
          ))}
          <button
            type="button"
            className="icon-btn"
            title={t("table.removeRow")}
            onClick={() => {
              handleRemove(rowIndex);
            }}
          >
            <X size={12} />
          </button>
        </div>
      ))}

      <div>
        <button type="button" className="btn xs" onClick={handleAdd}>
          <Plus size={11} />
          {t("table.addRow")}
        </button>
      </div>
    </div>
  );
};

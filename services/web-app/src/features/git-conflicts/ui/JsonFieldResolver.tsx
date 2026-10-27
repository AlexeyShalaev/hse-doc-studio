import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Check, ChevronDown, ChevronRight, Undo2 } from "lucide-react";
import type { FileResolution, JsonFieldConflict } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import {
  autoFieldWinner,
  autoFieldsOf,
  conflictFieldsOf,
  fieldChoicesFor,
  fieldsProgress,
  sameValue,
  unionValue,
  type FieldChoiceValue,
  type JsonDetail,
} from "../model/conflictModel";

export type JsonFieldResolverProps = {
  detail: JsonDetail;
  resolution: FileResolution | null | undefined;
  /** Подпись «их» с именем автора, если оно известно. */
  theirsLabel: string;
  onChoose: (pointer: string, choice: FieldChoiceValue) => void;
  onClear: (pointer: string) => void;
  onChooseAll: (choice: "mine" | "theirs") => void;
  onNextFile: () => void;
  hasNextFile: boolean;
};

// --- значение поля ------------------------------------------------------------

const itemText = (item: unknown): string => {
  if (typeof item === "string") return item;
  if (item !== null && typeof item === "object") return JSON.stringify(item);
  return String(item);
};

/**
 * Значение поля как его видит человек: строка текстом, список значками, объект
 * как JSON. Пусто и «нет» называются словами, а не пустым местом.
 */
const FieldValue = ({
  value,
  type,
  against,
}: {
  value: unknown;
  type: string;
  /** Список для сравнения: значения, которых в нём нет, отмечаются как новые. */
  against?: unknown;
}) => {
  const { t } = useTranslation("gitConflicts");
  const dim = (text: string) => (
    <span className="dim" style={{ fontStyle: "italic" }}>
      {text}
    </span>
  );
  if (value === null || value === undefined) {
    return dim(t(type === "presence" ? "fields.absent" : "fields.empty"));
  }
  if (typeof value === "string") {
    return value === "" ? (
      dim(t("fields.empty"))
    ) : (
      <span className="field-text">{value}</span>
    );
  }
  if (typeof value === "boolean") {
    return <span>{t(value ? "fields.yes" : "fields.no")}</span>;
  }
  if (typeof value === "number") {
    return (
      <span className="mono" style={{ fontSize: 11.5 }}>
        {value}
      </span>
    );
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return dim(t("fields.emptyList"));
    const known: unknown[] = Array.isArray(against) ? against : [];
    return (
      <ul className="field-list">
        {value.map((item: unknown, index) => {
          const isNew =
            Array.isArray(against) && !known.some((k) => sameValue(k, item));
          return (
            <li key={`${itemText(item)}:${String(index)}`} data-new={isNew}>
              {itemText(item)}
              {isNew && <span className="sr-only"> ({t("fields.added")})</span>}
            </li>
          );
        })}
      </ul>
    );
  }
  return <pre className="field-json">{JSON.stringify(value, null, 2)}</pre>;
};

// --- конфликтное поле ---------------------------------------------------------

type SideProps = {
  field: JsonFieldConflict;
  groupName: string;
  choice: FieldChoiceValue | null;
  side: FieldChoiceValue;
  label: string;
  /** Что значит этот вариант для человека: значение или результат объединения. */
  children: React.ReactNode;
  onChoose: (choice: FieldChoiceValue) => void;
};

const ChoiceCell = ({
  field,
  groupName,
  choice,
  side,
  label,
  children,
  onChoose,
}: SideProps) => {
  const id = useId();
  const checked = choice === side;
  return (
    <label
      className="field-side"
      data-side={side === "theirs" ? "theirs" : "mine"}
      data-wide={side === "union" ? "true" : undefined}
      data-included={checked ? "true" : undefined}
    >
      <span className="field-side-head">
        <input
          type="radio"
          name={groupName}
          checked={checked}
          aria-label={`${field.label ?? field.pointer}: ${label}`}
          aria-describedby={id}
          onChange={() => {
            onChoose(side);
          }}
        />
        <span className="truncate" title={label}>
          {label}
        </span>
        {checked && (
          <Check size={12} aria-hidden="true" style={{ marginLeft: "auto" }} />
        )}
      </span>
      <span className="field-side-body" id={id}>
        {children}
      </span>
    </label>
  );
};

const FieldCard = ({
  field,
  index,
  total,
  choice,
  theirsLabel,
  onChoose,
  onClear,
}: {
  field: JsonFieldConflict;
  index: number;
  total: number;
  choice: FieldChoiceValue | null;
  theirsLabel: string;
  onChoose: (pointer: string, choice: FieldChoiceValue) => void;
  onClear: (pointer: string) => void;
}) => {
  const { t } = useTranslation("gitConflicts");
  const groupName = useId();
  const title = field.label ?? field.pointer;
  const union = field.allowed.includes("union") ? unionValue(field) : null;
  const canMine = field.allowed.length === 0 || field.allowed.includes("mine");
  const canTheirs =
    field.allowed.length === 0 || field.allowed.includes("theirs");
  const resolved = choice !== null;
  const pick = (value: FieldChoiceValue): void => {
    onChoose(field.pointer, value);
  };
  return (
    <div
      role="radiogroup"
      aria-label={t("fields.group", { field: title, n: index + 1, total })}
      data-state={resolved ? "resolved" : "open"}
      data-pointer={field.pointer}
      className="hunk-card"
    >
      <div className="hunk-head">
        <strong
          style={{
            fontSize: 12.5,
            fontFamily: field.label ? undefined : "var(--font-mono)",
          }}
        >
          {title}
        </strong>
        {field.label && (
          <span className="dim mono" style={{ fontSize: 10.5 }}>
            {field.pointer}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {resolved ? (
          <>
            <span className="hunk-state" data-state="resolved">
              <Check size={11} aria-hidden="true" />
              {t(`fields.chosen.${choice}`)}
            </span>
            <button
              type="button"
              className="btn xs ghost"
              onClick={() => {
                onClear(field.pointer);
              }}
            >
              <Undo2 size={11} aria-hidden="true" />
              {t("hunk.undo")}
            </button>
          </>
        ) : (
          <span className="hunk-state" data-state="open">
            {t("hunk.open")}
          </span>
        )}
      </div>

      <div className="field-sides">
        <div className="field-side" data-base="true">
          <span className="field-side-head">{t("fields.base")}</span>
          <span className="field-side-body">
            <FieldValue value={field.base} type={field.type} />
          </span>
        </div>
        {canMine && (
          <ChoiceCell
            field={field}
            groupName={groupName}
            choice={choice}
            side="mine"
            label={t("fields.mine")}
            onChoose={pick}
          >
            <FieldValue
              value={field.ours}
              type={field.type}
              against={field.base}
            />
          </ChoiceCell>
        )}
        {canTheirs && (
          <ChoiceCell
            field={field}
            groupName={groupName}
            choice={choice}
            side="theirs"
            label={theirsLabel}
            onChoose={pick}
          >
            <FieldValue
              value={field.theirs}
              type={field.type}
              against={field.base}
            />
          </ChoiceCell>
        )}
        {union && (
          <ChoiceCell
            field={field}
            groupName={groupName}
            choice={choice}
            side="union"
            label={t("fields.union")}
            onChoose={pick}
          >
            <span className="dim" style={{ fontSize: 11.5 }}>
              {t("fields.unionHint")}
            </span>
            <FieldValue value={union} type={field.type} against={field.base} />
          </ChoiceCell>
        )}
      </div>
    </div>
  );
};

// --- поля, которые сервер слил сам ----------------------------------------------

const autoSourceKey = (field: JsonFieldConflict): string =>
  `fields.auto.from.${autoFieldWinner(field)}`;

const AutoFields = ({
  fields,
  t,
}: {
  fields: JsonFieldConflict[];
  t: TFunction<"gitConflicts">;
}) => {
  const [open, setOpen] = useState(false);
  const listId = useId();
  if (fields.length === 0) return null;
  return (
    <section className="flex flex-col" style={{ gap: 6 }}>
      <button
        type="button"
        className="flex items-center"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => {
          setOpen((value) => !value);
        }}
        style={{
          gap: 4,
          background: "none",
          border: 0,
          padding: 0,
          cursor: "pointer",
          textAlign: "left",
          fontSize: 12,
          fontWeight: 600,
          color: "var(--fg-1)",
        }}
      >
        {open ? (
          <ChevronDown size={13} aria-hidden="true" />
        ) : (
          <ChevronRight size={13} aria-hidden="true" />
        )}
        {t("fields.auto.title", { count: fields.length })}
      </button>
      {open && (
        <div id={listId} className="flex flex-col" style={{ gap: 6 }}>
          <p className="dim" style={{ margin: 0, fontSize: 11.5 }}>
            {t("fields.auto.hint")}
          </p>
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            {fields.map((field) => {
              const winner = autoFieldWinner(field);
              const merged = winner === "theirs" ? field.theirs : field.ours;
              return (
                <div key={field.pointer} className="field-auto-row">
                  <div className="flex items-center" style={{ gap: 8 }}>
                    <strong
                      style={{
                        fontSize: 12,
                        fontFamily: field.label
                          ? undefined
                          : "var(--font-mono)",
                      }}
                    >
                      {field.label ?? field.pointer}
                    </strong>
                    <span className="chip subtle">
                      {t(autoSourceKey(field))}
                    </span>
                  </div>
                  <div style={{ fontSize: 12 }}>
                    <FieldValue value={merged} type={field.type} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
};

/**
 * Разбор файла с полями (форма, подписи, настройки): на каждое спорное поле
 * карточка «было, моё, их», у списков ещё и «объединить». Поля, которые сервер
 * слил сам, свёрнуты ниже: решать в них нечего.
 */
export const JsonFieldResolver = ({
  detail,
  resolution,
  theirsLabel,
  onChoose,
  onClear,
  onChooseAll,
  onNextFile,
  hasNextFile,
}: JsonFieldResolverProps) => {
  const { t } = useTranslation("gitConflicts");
  const conflicts = useMemo(() => conflictFieldsOf(detail), [detail]);
  const auto = useMemo(() => autoFieldsOf(detail), [detail]);
  const choices = fieldChoicesFor(detail, resolution);
  const progress = fieldsProgress(detail, resolution);

  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      {conflicts.length > 0 && (
        <div className="hunk-toolbar">
          <span style={{ fontSize: 12, fontWeight: 600 }} aria-live="polite">
            {progress.open > 0
              ? t("fields.open", {
                  open: progress.open,
                  total: progress.total,
                })
              : t("fields.allDone")}
          </span>
          <span style={{ flex: 1 }} />
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onChooseAll("mine");
            }}
          >
            {t("fields.allMine")}
          </button>
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onChooseAll("theirs");
            }}
          >
            {t("fields.allTheirs")}
          </button>
        </div>
      )}

      {progress.open === 0 && conflicts.length > 0 && hasNextFile && (
        <Notice
          tone="info"
          role="status"
          text={t("parts.fileDone")}
          action={
            <button type="button" className="btn xs" onClick={onNextFile}>
              {t("parts.nextFile")}
            </button>
          }
        />
      )}

      <div className="flex flex-col" style={{ gap: 10 }}>
        {conflicts.map((field, index) => (
          <FieldCard
            key={field.pointer}
            field={field}
            index={index}
            total={conflicts.length}
            choice={choices[field.pointer] ?? null}
            theirsLabel={theirsLabel}
            onChoose={onChoose}
            onClear={onClear}
          />
        ))}
      </div>

      <AutoFields fields={auto} t={t} />
    </div>
  );
};

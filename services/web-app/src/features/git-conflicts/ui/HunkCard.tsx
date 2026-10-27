import { forwardRef, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Pencil, Undo2 } from "lucide-react";
import type { HunkChoice } from "@entities/git-sync";
import { diffLines } from "@shared/lib";
import {
  composeHunkText,
  hasConflictMarkers,
  hunkResultLines,
  type HunkChoiceValue,
  type HunkSegment,
} from "../model/conflictModel";

export type HunkCardProps = {
  hunk: HunkSegment;
  /** Номер места и сколько их всего в файле. */
  index: number;
  total: number;
  choice: HunkChoice | undefined;
  theirsLabel: string;
  onChoose: (choice: HunkChoice) => void;
  onClear: () => void;
  onActivate: () => void;
};

type SideKey = "mine" | "theirs";

// Что из двух сторон попадёт в итог при выбранном варианте.
const INCLUDED: Record<HunkChoiceValue, SideKey[]> = {
  mine: ["mine"],
  theirs: ["theirs"],
  both: ["mine", "theirs"],
  both_reverse: ["mine", "theirs"],
  base: [],
  custom: [],
};

const asValue = (choice: HunkChoice | undefined): HunkChoiceValue | null => {
  switch (choice?.choice) {
    case "mine":
    case "theirs":
    case "both":
    case "both_reverse":
    case "base":
    case "custom":
      return choice.choice;
    default:
      return null;
  }
};

type SideLine = { text: string; own: boolean };

/** Строки стороны с отметкой «есть только здесь», чтобы взгляд ловил разницу. */
const markSides = (
  mine: string[],
  theirs: string[],
): { mine: SideLine[]; theirs: SideLine[] } => {
  // Пустая сторона (чаще всего удаление против правки): сравнивать нечего, а
  // diffLines("", "x") вернул бы лишнюю пустую строку.
  if (mine.length === 0 || theirs.length === 0) {
    return {
      mine: mine.map((text) => ({ text, own: true })),
      theirs: theirs.map((text) => ({ text, own: true })),
    };
  }
  const diff = diffLines(mine.join("\n"), theirs.join("\n"));
  const left: SideLine[] = [];
  const right: SideLine[] = [];
  for (const line of diff) {
    if (line.kind === "del") left.push({ text: line.text, own: true });
    else if (line.kind === "add") right.push({ text: line.text, own: true });
    else {
      left.push({ text: line.text, own: false });
      right.push({ text: line.text, own: false });
    }
  }
  return { mine: left, theirs: right };
};

const SideColumn = ({
  side,
  label,
  lines,
  startLine,
  included,
  dimmed,
  empty,
  lineTitle,
}: {
  side: SideKey;
  label: string;
  lines: SideLine[];
  startLine: number;
  included: boolean;
  dimmed: boolean;
  empty: string;
  lineTitle: string;
}) => (
  <div
    className="hunk-side"
    data-side={side}
    data-included={included ? "true" : undefined}
    data-dimmed={dimmed ? "true" : undefined}
  >
    <div className="hunk-side-head">
      <span className="truncate" title={label}>
        {label}
      </span>
      {included && <Check size={12} aria-hidden="true" />}
    </div>
    {lines.length === 0 ? (
      <div className="hunk-line dim" style={{ fontStyle: "italic" }}>
        <span className="hunk-gutter" />
        <span className="hunk-code">{empty}</span>
      </div>
    ) : (
      lines.map((line, i) => (
        <div
          key={i}
          className="hunk-line"
          data-own={line.own ? "true" : undefined}
        >
          <span className="hunk-gutter" title={lineTitle}>
            {startLine + i}
          </span>
          <span className="hunk-code">{line.text || " "}</span>
        </div>
      ))
    )}
  </div>
);

/**
 * Одно место конфликта: моя и чужая версии рядом, кнопки выбора, возможность
 * дописать свой вариант. Карточка сама является группой с подписью: к ней
 * переводят фокус клавишей N и после выбора.
 */
export const HunkCard = forwardRef<HTMLDivElement, HunkCardProps>(
  (
    { hunk, index, total, choice, theirsLabel, onChoose, onClear, onActivate },
    ref,
  ) => {
    const { t } = useTranslation("gitConflicts");
    const value = asValue(choice);
    const resolved = value !== null;
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState("");
    const sides = useMemo(
      () => markSides(hunk.ours, hunk.theirs),
      [hunk.ours, hunk.theirs],
    );
    const included = value ? INCLUDED[value] : [];
    const result = useMemo(() => hunkResultLines(hunk, choice), [choice, hunk]);
    const hasMarkers = hasConflictMarkers(draft);

    const startEditing = (): void => {
      setDraft(
        choice?.choice === "custom" && choice.text != null
          ? choice.text
          : composeHunkText(hunk, choice),
      );
      setEditing(true);
    };

    const quick: { value: HunkChoiceValue; label: string }[] = [
      { value: "mine", label: t("hunk.choose.mine") },
      { value: "theirs", label: t("hunk.choose.theirs") },
      { value: "both", label: t("hunk.choose.both") },
      { value: "both_reverse", label: t("hunk.choose.both_reverse") },
    ];

    return (
      <div
        ref={ref}
        role="group"
        tabIndex={-1}
        aria-label={t("hunk.aria", { n: index + 1, total })}
        data-hunk-key={hunk.key}
        data-state={resolved ? "resolved" : "open"}
        className="hunk-card"
        onFocus={onActivate}
      >
        <div className="hunk-head">
          <strong style={{ fontSize: 12.5 }}>
            {t("hunk.title", { n: index + 1, total })}
          </strong>
          <span className="dim mono" style={{ fontSize: 10.5 }}>
            {t("hunk.line", { line: hunk.ours_start })}
          </span>
          <span style={{ flex: 1 }} />
          {resolved ? (
            <>
              <span className="hunk-state" data-state="resolved">
                <Check size={11} aria-hidden="true" />
                {t(`hunk.chosen.${value}`)}
              </span>
              <button type="button" className="btn xs ghost" onClick={onClear}>
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

        <div className="hunk-sides">
          <SideColumn
            side="mine"
            label={t("hunk.mine")}
            lines={sides.mine}
            startLine={hunk.ours_start}
            included={included.includes("mine")}
            dimmed={resolved && !included.includes("mine")}
            empty={t("hunk.empty")}
            lineTitle={t("hunk.lineMine")}
          />
          <SideColumn
            side="theirs"
            label={theirsLabel}
            lines={sides.theirs}
            startLine={hunk.result_start}
            included={included.includes("theirs")}
            dimmed={resolved && !included.includes("theirs")}
            empty={t("hunk.empty")}
            lineTitle={t("hunk.lineTheirs")}
          />
        </div>

        {(value === "base" || value === "custom") && !editing && (
          <div className="hunk-result">
            <div className="hunk-side-head">
              <span>{t("hunk.result")}</span>
            </div>
            {result.length === 0 ? (
              <div className="hunk-line dim" style={{ fontStyle: "italic" }}>
                <span className="hunk-gutter" />
                <span className="hunk-code">{t("hunk.empty")}</span>
              </div>
            ) : (
              result.map((line, i) => (
                <div key={i} className="hunk-line">
                  <span className="hunk-gutter" />
                  <span className="hunk-code">{line || " "}</span>
                </div>
              ))
            )}
          </div>
        )}

        {hunk.base.length > 0 && (
          <details className="hunk-base">
            <summary>{t("hunk.base")}</summary>
            <div>
              {hunk.base.map((line, i) => (
                <div key={i} className="hunk-line">
                  <span className="hunk-gutter" />
                  <span className="hunk-code">{line || " "}</span>
                </div>
              ))}
            </div>
          </details>
        )}

        {editing ? (
          <div className="flex flex-col" style={{ gap: 6 }}>
            <label
              className="dim"
              htmlFor={`hunk-edit-${hunk.key}`}
              style={{ fontSize: 11.5 }}
            >
              {t("hunk.customHint")}
            </label>
            <textarea
              id={`hunk-edit-${hunk.key}`}
              className="textarea mono"
              rows={Math.min(Math.max(draft.split("\n").length, 3), 12)}
              value={draft}
              spellCheck={false}
              aria-invalid={hasMarkers}
              onChange={(event) => {
                setDraft(event.target.value);
              }}
            />
            {hasMarkers && (
              <span
                role="alert"
                style={{ fontSize: 11.5, color: "var(--c-err)" }}
              >
                {t("hunk.customMarkers")}
              </span>
            )}
            <div className="flex" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn sm primary"
                disabled={hasMarkers}
                onClick={() => {
                  onChoose({ choice: "custom", text: draft });
                  setEditing(false);
                }}
              >
                {t("hunk.customApply")}
              </button>
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  setEditing(false);
                }}
              >
                {t("hunk.customCancel")}
              </button>
            </div>
          </div>
        ) : (
          <div className="hunk-actions">
            {quick.map((option) => (
              <button
                key={option.value}
                type="button"
                className={value === option.value ? "btn sm primary" : "btn sm"}
                aria-pressed={value === option.value}
                onClick={() => {
                  onChoose({ choice: option.value });
                }}
              >
                {option.label}
              </button>
            ))}
            <button
              type="button"
              className={value === "custom" ? "btn sm primary" : "btn sm"}
              aria-pressed={value === "custom"}
              onClick={startEditing}
            >
              <Pencil size={11} aria-hidden="true" />
              {t("hunk.choose.custom")}
            </button>
            {hunk.base.length > 0 && (
              <button
                type="button"
                className={value === "base" ? "btn sm primary" : "btn sm ghost"}
                aria-pressed={value === "base"}
                onClick={() => {
                  onChoose({ choice: "base" });
                }}
              >
                {t("hunk.choose.base")}
              </button>
            )}
          </div>
        )}
      </div>
    );
  },
);

HunkCard.displayName = "HunkCard";

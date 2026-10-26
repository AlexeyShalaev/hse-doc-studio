import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronUp,
  FoldVertical,
  UnfoldVertical,
} from "lucide-react";
import type { FileResolution, HunkChoice } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { chosenHunks, hunksOf, type TextDetail } from "../model/conflictModel";
import type { HunkFocusRequest } from "../model/useConflictWorkspace";
import { HunkCard } from "./HunkCard";

// Сколько строк контекста оставляем у места конфликта, когда остальное свёрнуто.
const CONTEXT_LINES = 3;

export type TextHunkResolverProps = {
  detail: TextDetail;
  resolution: FileResolution | null | undefined;
  theirsLabel: string;
  focusRequest: HunkFocusRequest | null;
  onFocusHandled: (token: number) => void;
  onActivateHunk: (key: string) => void;
  onChoose: (key: string, choice: HunkChoice) => void;
  onClear: (key: string) => void;
  onChooseAll: (choice: "mine" | "theirs") => void;
  onJump: (direction: 1 | -1) => void;
  onNextFile: () => void;
  hasNextFile: boolean;
  onRevertManual: () => void;
};

type Numbered = { text: string; no: number };

/** Номера строк в моём файле: чистые участки идут подряд, места задают свой старт. */
const startLines = (detail: TextDetail): number[] => {
  const starts: number[] = [];
  let line = 1;
  for (const segment of detail.segments) {
    if (segment.type === "clean") {
      starts.push(line);
      line += segment.lines.length;
    } else {
      starts.push(segment.ours_start);
      line = segment.ours_start + segment.ours.length;
    }
  }
  return starts;
};

const numbered = (lines: string[], start: number): Numbered[] =>
  lines.map((text, i) => ({ text, no: start + i }));

const CleanLines = ({ lines }: { lines: Numbered[] }) => (
  <div className="hunk-context">
    {lines.map((line) => (
      <div key={line.no} className="hunk-line">
        <span className="hunk-gutter">{line.no}</span>
        <span className="hunk-code">{line.text || " "}</span>
      </div>
    ))}
  </div>
);

const scrollBehavior = (): ScrollBehavior =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? "auto"
    : "smooth";

/**
 * Файл «по частям»: свёрнутый контекст вокруг мест конфликта и карточка на
 * каждое место. Сверху счётчик и переходы (клавиши N и Shift+N), готовый
 * результат файла остаётся на вкладке «Итог».
 */
export const TextHunkResolver = ({
  detail,
  resolution,
  theirsLabel,
  focusRequest,
  onFocusHandled,
  onActivateHunk,
  onChoose,
  onClear,
  onChooseAll,
  onJump,
  onNextFile,
  hasNextFile,
  onRevertManual,
}: TextHunkResolverProps) => {
  const { t } = useTranslation("gitConflicts");
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const cards = useRef(new Map<string, HTMLDivElement>());

  const hunks = useMemo(() => hunksOf(detail), [detail]);
  const starts = useMemo(() => startLines(detail), [detail]);
  const chosen = chosenHunks(resolution);
  const openCount = hunks.filter((h) => !(h.key in chosen)).length;
  const isManual = resolution?.kind === "text";

  // Фокус на карточку по просьбе (выбор, клавиша N): прокрутка и фокус сразу.
  // Просьбу гасим после исполнения, иначе возврат на вкладку «По частям» снова
  // увёл бы фокус на давно выбранное место.
  useEffect(() => {
    if (!focusRequest) return;
    const el = cards.current.get(focusRequest.key);
    if (!el) return;
    el.focus({ preventScroll: true });
    (el as Partial<HTMLElement>).scrollIntoView?.({
      block: "center",
      behavior: scrollBehavior(),
    });
    onFocusHandled(focusRequest.token);
  }, [focusRequest, detail, onFocusHandled]);

  if (isManual) {
    return (
      <div className="flex flex-col" style={{ gap: 10 }}>
        <Notice
          tone="info"
          role="status"
          text={t("manual.active")}
          action={
            <button type="button" className="btn xs" onClick={onRevertManual}>
              {t("manual.revert")}
            </button>
          }
        />
      </div>
    );
  }

  const toggle = (index: number): void => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  let hunkIndex = -1;
  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      {detail.truncated && (
        <Notice tone="warn" role="status" text={t("parts.truncated")} />
      )}
      <div className="hunk-toolbar">
        <span style={{ fontSize: 12, fontWeight: 600 }} aria-live="polite">
          {openCount > 0
            ? t("parts.open", { open: openCount, total: hunks.length })
            : t("parts.allDone")}
        </span>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            onChooseAll("mine");
          }}
        >
          {t("parts.allMine")}
        </button>
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            onChooseAll("theirs");
          }}
        >
          {t("parts.allTheirs")}
        </button>
        <span className="hunk-toolbar-sep" aria-hidden="true" />
        <button
          type="button"
          className="btn xs"
          disabled={openCount === 0}
          aria-keyshortcuts="Shift+N"
          title={t("parts.prevHint")}
          onClick={() => {
            onJump(-1);
          }}
        >
          <ChevronUp size={12} aria-hidden="true" />
          {t("parts.prev")}
        </button>
        <button
          type="button"
          className="btn xs"
          disabled={openCount === 0}
          aria-keyshortcuts="N"
          title={t("parts.nextHint")}
          onClick={() => {
            onJump(1);
          }}
        >
          <ChevronDown size={12} aria-hidden="true" />
          {t("parts.next")}
        </button>
      </div>

      {openCount === 0 && hunks.length > 0 && hasNextFile && (
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
        {detail.segments.map((segment, index) => {
          const start = starts[index] ?? 1;
          if (segment.type === "hunk") {
            hunkIndex += 1;
            return (
              <HunkCard
                key={segment.key}
                ref={(el) => {
                  if (el) cards.current.set(segment.key, el);
                  else cards.current.delete(segment.key);
                }}
                hunk={segment}
                index={hunkIndex}
                total={hunks.length}
                choice={chosen[segment.key]}
                theirsLabel={theirsLabel}
                onChoose={(choice) => {
                  onChoose(segment.key, choice);
                }}
                onClear={() => {
                  onClear(segment.key);
                }}
                onActivate={() => {
                  onActivateHunk(segment.key);
                }}
              />
            );
          }

          const prevIsHunk = detail.segments[index - 1]?.type === "hunk";
          const nextIsHunk = detail.segments[index + 1]?.type === "hunk";
          const lines = numbered(segment.lines, start);
          const head = prevIsHunk ? CONTEXT_LINES : 0;
          const tail = nextIsHunk ? CONTEXT_LINES : 0;
          const hidden = lines.length - head - tail;
          if (lines.length === 0) return null;
          // Короткий участок не стоит сворачивать: кнопка заняла бы столько же места.
          if (hidden <= 2 || expanded.has(index)) {
            return (
              <div key={`clean-${String(index)}`}>
                <CleanLines lines={lines} />
                {hidden > 2 && (
                  <button
                    type="button"
                    className="hunk-fold"
                    aria-expanded="true"
                    onClick={() => {
                      toggle(index);
                    }}
                  >
                    <FoldVertical size={12} aria-hidden="true" />
                    {t("parts.fold")}
                  </button>
                )}
              </div>
            );
          }
          return (
            <div key={`clean-${String(index)}`}>
              {head > 0 && <CleanLines lines={lines.slice(0, head)} />}
              <button
                type="button"
                className="hunk-fold"
                aria-expanded="false"
                onClick={() => {
                  toggle(index);
                }}
              >
                <UnfoldVertical size={12} aria-hidden="true" />
                {t("parts.unfold", { count: hidden })}
              </button>
              {tail > 0 && <CleanLines lines={lines.slice(-tail)} />}
            </div>
          );
        })}
      </div>
    </div>
  );
};

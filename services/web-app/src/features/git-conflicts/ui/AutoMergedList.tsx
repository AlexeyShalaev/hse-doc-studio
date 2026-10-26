import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  ActionTag,
  FileList,
  FileRowShell,
  type ConflictTone,
} from "@shared/ui/ConflictKit";

/** Файл, который сервер объединил сам: подходит и файл сеанса, и итог слияния. */
export type AutoMergedItem = {
  path: string;
  action: string;
  copy_path?: string | null | undefined;
};

export type AutoMergedListProps = {
  items: AutoMergedItem[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
  /** Раскрыть группу сразу (иначе она свёрнута, пока не выбран файл из неё). */
  defaultOpen?: boolean;
};

const ACTION_TONE: Record<string, ConflictTone> = {
  merged: "ok",
  take_theirs: "info",
  delete: "muted",
  binary_newest: "warn",
};

// Порядок слов в сводке: сначала то, что стоит проверить глазами.
const ACTION_ORDER = ["binary_newest", "merged", "take_theirs", "delete"];

const sectionLabelStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 10.5,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};

const summarize = (items: AutoMergedItem[]): [string, number][] => {
  const counts = new Map<string, number>();
  for (const item of items) {
    counts.set(item.action, (counts.get(item.action) ?? 0) + 1);
  }
  return [...counts.entries()].sort(
    ([a], [b]) =>
      (ACTION_ORDER.indexOf(a) + 1 || 99) - (ACTION_ORDER.indexOf(b) + 1 || 99),
  );
};

/**
 * Свёрнутая группа «Решено автоматически»: что сервер объединил сам. Под
 * заголовком сводка по видам действий; выбранный файл из группы остаётся виден,
 * даже если её свернули. Если рядом сохранена копия, имя копии видно в строке.
 */
export const AutoMergedList = ({
  items,
  selectedPath,
  onSelect,
  defaultOpen = false,
}: AutoMergedListProps) => {
  const { t } = useTranslation("gitConflicts");
  const [open, setOpen] = useState(defaultOpen);
  const listId = useId();
  if (items.length === 0) return null;

  const expanded = open || items.some((item) => item.path === selectedPath);
  const label = (action: string): string =>
    t(`auto.action.${action}`, { defaultValue: action });

  return (
    <section className="flex flex-col" style={{ gap: 6 }}>
      <button
        type="button"
        className="flex items-center mono dim"
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => {
          setOpen((value) => !value);
        }}
        style={{
          ...sectionLabelStyle,
          gap: 4,
          background: "none",
          border: 0,
          padding: 0,
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        {expanded ? (
          <ChevronDown size={12} aria-hidden="true" />
        ) : (
          <ChevronRight size={12} aria-hidden="true" />
        )}
        {t("list.auto")} · {items.length}
      </button>
      <div id={listId} className="flex flex-col" style={{ gap: 6 }}>
        {expanded && (
          <>
            <p
              className="dim"
              style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5 }}
            >
              {t("auto.hint")}
            </p>
            <p
              className="dim"
              data-testid="auto-summary"
              style={{ margin: 0, fontSize: 11 }}
            >
              {summarize(items)
                .map(([action, count]) =>
                  t("auto.summary", { label: label(action), count }),
                )
                .join(" · ")}
            </p>
            <FileList maxHeight="none">
              {items.map((item) => (
                <FileRowShell
                  key={item.path}
                  path={item.path}
                  isSelected={item.path === selectedPath}
                  onSelect={() => {
                    onSelect(item.path);
                  }}
                  tag={
                    <ActionTag
                      label={label(item.action)}
                      tone={ACTION_TONE[item.action] ?? "muted"}
                      minWidth={92}
                    />
                  }
                >
                  {item.copy_path ? (
                    <span
                      className="dim"
                      style={{ fontSize: 11 }}
                      title={item.copy_path}
                    >
                      {t("auto.copy")}{" "}
                      <span className="mono truncate">{item.copy_path}</span>
                    </span>
                  ) : undefined}
                </FileRowShell>
              ))}
            </FileList>
          </>
        )}
      </div>
    </section>
  );
};

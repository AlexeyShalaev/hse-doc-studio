import { Plus, Trash2, Users } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clsx } from "clsx";
import { SectionCard } from "../SectionCard";
import type { AuthorEntry } from "./types";

type AuthorRowProps = {
  value: AuthorEntry;
  index: number;
  removable: boolean;
  // Team mode: show topic/slug/managed extras. Per-author meta values are
  // edited in the «Метаданные» section (block switcher), not here.
  isTeam: boolean;
  // `immediate` marks deliberate clicks (selects) vs debounced typing.
  onChange: (patch: Partial<AuthorEntry>, immediate?: boolean) => void;
  onRemove: () => void;
  // Довключение/выключение комплекта автора (POST /team/sets). Undefined —
  // тоггл недоступен (solo или автор без слага).
  onToggleManaged?: (() => void) | undefined;
  isTogglingManaged?: boolean;
  // Подсказка в поле «Группа» из пака (формат шифра группы программы).
  groupPlaceholder: string;
};

const AuthorRow = ({
  value,
  index,
  removable,
  isTeam,
  onChange,
  onRemove,
  onToggleManaged,
  isTogglingManaged,
  groupPlaceholder,
}: AuthorRowProps) => {
  const { t } = useTranslation("workspace");
  return (
    <div
      className="card"
      style={{ padding: "0.875rem", background: "var(--bg-2)" }}
    >
      <div
        className="flex items-center justify-between person-head"
        style={{ marginBottom: "0.625rem" }}
      >
        <div className="flex items-center gap-2 author-head">
          <Users size="0.8125rem" style={{ color: "var(--accent)" }} />
          <strong style={{ fontSize: "0.78125rem" }}>
            {t("projectSettings.author", { number: index + 1 })}
          </strong>
          {isTeam && !!value.slug && (
            <span
              className="chip mono tt"
              data-tt={t("projectSettings.authorFolderHint")}
              style={{ fontSize: "0.625rem" }}
            >
              {value.slug}
            </span>
          )}
          {isTeam && (
            <button
              type="button"
              className={clsx("sev tt", value.managed && "ok")}
              data-tt={
                value.managed
                  ? t("projectSettings.authorManagedToggleHint")
                  : t("projectSettings.authorUnmanagedToggleHint")
              }
              disabled={!onToggleManaged || isTogglingManaged}
              onClick={onToggleManaged}
              style={{
                cursor: onToggleManaged ? "pointer" : "default",
                opacity: isTogglingManaged ? 0.6 : undefined,
                ...(value.managed
                  ? {}
                  : {
                      color: "var(--fg-2)",
                      borderColor: "var(--border)",
                      background: "var(--bg-2)",
                    }),
              }}
            >
              {value.managed
                ? t("projectSettings.authorManaged")
                : t("projectSettings.authorUnmanaged")}
            </button>
          )}
        </div>
        {removable && (
          <button
            type="button"
            className="icon-btn sm"
            style={{ color: "var(--c-err)" }}
            onClick={onRemove}
          >
            <Trash2 size="0.6875rem" />
          </button>
        )}
      </div>
      <div className="flex gap-3 author-fields">
        <div className="field flex-1">
          <label>{t("projectSettings.fullName")}</label>
          <input
            className="input"
            value={value.name}
            onChange={(e) => {
              onChange({ name: e.target.value });
            }}
          />
        </div>
        <div className="field" style={{ width: "8.75rem" }}>
          <label>{t("projectSettings.group")}</label>
          <input
            className="input"
            value={value.group ?? ""}
            placeholder={groupPlaceholder}
            onChange={(e) => {
              onChange({ group: e.target.value });
            }}
          />
        </div>
      </div>
      {isTeam && (
        <div className="field" style={{ marginTop: "0.625rem" }}>
          <label>{t("projectSettings.authorTopic")}</label>
          <input
            className="input"
            value={value.topic ?? ""}
            onChange={(e) => {
              onChange({ topic: e.target.value });
            }}
          />
        </div>
      )}
    </div>
  );
};

export type AuthorsSectionProps = {
  authors: readonly AuthorEntry[];
  isTeam: boolean;
  isTogglingManaged: boolean;
  onChangeAuthor: (
    index: number,
    patch: Partial<AuthorEntry>,
    immediate?: boolean,
  ) => void;
  onRemoveAuthor: (index: number) => void;
  onAddAuthor: () => void;
  onToggleManaged: (author: AuthorEntry) => void;
  // Подсказка в поле «Группа» из пака; пусто — общий плейсхолдер.
  groupPlaceholder?: string | undefined;
};

export const AuthorsSection = ({
  authors,
  isTeam,
  isTogglingManaged,
  onChangeAuthor,
  onRemoveAuthor,
  onAddAuthor,
  onToggleManaged,
  groupPlaceholder,
}: AuthorsSectionProps) => {
  const { t } = useTranslation("workspace");
  const groupHint = groupPlaceholder || t("projectSettings.groupPlaceholder");
  return (
    <SectionCard title={t("projectSettings.sectionAuthors")} fullSpan>
      <div className="flex flex-col" style={{ gap: "0.625rem" }}>
        {authors.length === 0 ? (
          <span className="dim" style={{ fontSize: "0.71875rem" }}>
            {t("projectSettings.noAuthors")}
          </span>
        ) : (
          authors.map((a, i) => (
            <AuthorRow
              key={i}
              value={a}
              index={i}
              // An author whose document set is app-managed cannot be
              // removed — their folder holds real per-author docs.
              removable={authors.length > 1 && !(isTeam && a.managed)}
              isTeam={isTeam}
              onChange={(p, immediate) => {
                onChangeAuthor(i, p, immediate);
              }}
              onRemove={() => {
                onRemoveAuthor(i);
              }}
              onToggleManaged={
                isTeam && a.slug
                  ? () => {
                      onToggleManaged(a);
                    }
                  : undefined
              }
              isTogglingManaged={isTogglingManaged}
              groupPlaceholder={groupHint}
            />
          ))
        )}
        <button
          type="button"
          className="btn ghost self-start"
          onClick={onAddAuthor}
        >
          <Plus size="0.6875rem" />
          {t("projectSettings.addAuthor")}
        </button>
      </div>
    </SectionCard>
  );
};

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
}: AuthorRowProps) => {
  const { t } = useTranslation("workspace");
  return (
    <div className="card" style={{ padding: 14, background: "var(--bg-2)" }}>
      <div
        className="flex items-center justify-between"
        style={{ marginBottom: 10 }}
      >
        <div className="flex items-center gap-2">
          <Users size={13} style={{ color: "var(--accent)" }} />
          <strong style={{ fontSize: 12.5 }}>
            {t("projectSettings.author", { number: index + 1 })}
          </strong>
          {isTeam && !!value.slug && (
            <span
              className="chip mono tt"
              data-tt={t("projectSettings.authorFolderHint")}
              style={{ fontSize: 10 }}
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
            <Trash2 size={11} />
          </button>
        )}
      </div>
      <div className="flex gap-3">
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
        <div className="field" style={{ width: 140 }}>
          <label>{t("projectSettings.group")}</label>
          <input
            className="input"
            value={value.group ?? ""}
            placeholder="БПИ222"
            onChange={(e) => {
              onChange({ group: e.target.value });
            }}
          />
        </div>
      </div>
      {isTeam && (
        <div className="field" style={{ marginTop: 10 }}>
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
};

export const AuthorsSection = ({
  authors,
  isTeam,
  isTogglingManaged,
  onChangeAuthor,
  onRemoveAuthor,
  onAddAuthor,
  onToggleManaged,
}: AuthorsSectionProps) => {
  const { t } = useTranslation("workspace");
  return (
    <SectionCard title={t("projectSettings.sectionAuthors")} fullSpan>
      <div className="flex flex-col" style={{ gap: 10 }}>
        {authors.length === 0 ? (
          <span className="dim" style={{ fontSize: 11.5 }}>
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
            />
          ))
        )}
        <button
          type="button"
          className="btn ghost self-start"
          onClick={onAddAuthor}
        >
          <Plus size={11} />
          {t("projectSettings.addAuthor")}
        </button>
      </div>
    </SectionCard>
  );
};

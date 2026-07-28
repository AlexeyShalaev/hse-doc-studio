import { Archive, Briefcase, Building, Lock, Pin, User } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { useKindMeta, useTemplateMeta } from "@entities/project";
import { localeTag } from "@shared/lib";

type Project = z.infer<typeof ProjectResponseSchema>;

export type ProjectCardProps = {
  project: Project;
  onOpen: () => void;
  onTogglePin: () => void;
  onToggleArchive: () => void;
};

const formatRelative = (
  isoString: string,
  locale: string,
  today: (time: string) => string,
): string => {
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return "—";
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return today(
      d.toLocaleTimeString(locale, {
        hour: "2-digit",
        minute: "2-digit",
      }),
    );
  }
  return d.toLocaleDateString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
};

export const ProjectCard = ({
  project,
  onOpen,
  onTogglePin,
  onToggleArchive,
}: ProjectCardProps) => {
  const { t } = useTranslation("welcome");
  const meta = useTemplateMeta(project);
  const Icon = meta.icon;

  const hue = String(meta.accentHue);
  const accentBg = `oklch(60% 0.16 ${hue} / 0.14)`;
  const accentFg = `oklch(70% 0.16 ${hue})`;
  const accentLine = `oklch(60% 0.16 ${hue} / 0.3)`;

  // Тип проекта (исследовательский / прикладной) — рядом с иконкой шаблона,
  // чтобы вид работы был понятен с одного взгляда.
  const kindMeta = useKindMeta(project.kind);
  const KindIcon = kindMeta.icon;
  const kHue = String(kindMeta.hue);
  const kChroma = String(kindMeta.chroma);
  const kindBg = `oklch(60% ${kChroma} ${kHue} / 0.16)`;
  const kindFg = `oklch(70% ${kChroma} ${kHue})`;
  const kindLine = `oklch(60% ${kChroma} ${kHue} / 0.34)`;

  const isNda = project.meta?.nda === true;
  const supervisor = project.supervisor ?? null;

  return (
    <div
      className={clsx("card hover relative", project.archived && "opacity-60")}
      style={{ padding: 18 }}
      // Карточка остаётся <div role="button">: внутри уже есть настоящие
      // кнопки (закрепить / архив), а <button> внутри <button> невалиден.
      role="button"
      tabIndex={0}
      aria-label={project.name}
      data-project-card={project.id}
      onClick={onOpen}
      onKeyDown={(e) => {
        // Enter/Space с вложенных кнопок всплывают сюда — иначе «закрепить»
        // с клавиатуры заодно открывало бы проект.
        if (e.target !== e.currentTarget) return;
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        onOpen();
      }}
    >
      <div
        className="flex items-center justify-between"
        style={{ marginBottom: 12 }}
      >
        {/* minWidth: 0 инлайном (утилита min-w-0 в этой сборке Tailwind не
            генерируется) + truncate на тексте: длинное название шаблона
            обрезается «…», не выталкивая кнопки. */}
        <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
          <div
            className="flex items-center justify-center shrink-0"
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: accentBg,
              color: accentFg,
            }}
          >
            <Icon size={16} />
          </div>
          <span
            className="chip"
            title={meta.label}
            style={{
              minWidth: 0,
              background: accentBg,
              color: accentFg,
              borderColor: accentLine,
            }}
          >
            <span className="truncate">{meta.label}</span>
          </span>
          <span
            className="chip shrink-0"
            title={kindMeta.label}
            style={{
              gap: 4,
              background: kindBg,
              color: kindFg,
              borderColor: kindLine,
            }}
          >
            <KindIcon size={11} />
            {kindMeta.label}
          </span>
        </div>
        <div
          className="flex items-center gap-1 shrink-0"
          onClick={(e) => {
            e.stopPropagation();
          }}
        >
          <button
            type="button"
            onClick={onTogglePin}
            className={clsx("icon-btn sm tt", project.pinned && "active")}
            data-tt={project.pinned ? t("card.unpin") : t("card.pin")}
            style={project.pinned ? { color: "var(--accent)" } : undefined}
          >
            <Pin size={11} />
          </button>
          <button
            type="button"
            onClick={onToggleArchive}
            className="icon-btn sm tt"
            data-tt={project.archived ? t("card.unarchive") : t("card.archive")}
          >
            <Archive size={11} />
          </button>
        </div>
      </div>

      <h3
        className="text-fg-0"
        style={{
          margin: "0 0 6px",
          fontSize: 15,
          fontWeight: 600,
          lineHeight: 1.3,
        }}
      >
        {project.name}
      </h3>
      <div className="mono dim" style={{ fontSize: 11, marginBottom: 14 }}>
        {project.folder}
      </div>

      <div
        className="flex items-center justify-between"
        style={{ paddingTop: 12, borderTop: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {supervisor && (
            <>
              <User size={11} style={{ color: "var(--fg-3)", flexShrink: 0 }} />
              <span
                className="dim truncate"
                style={{ fontSize: 11.5, minWidth: 0 }}
              >
                {supervisor.name}
              </span>
            </>
          )}
          {supervisor?.role === "company" && (
            <span
              className="chip shrink-0"
              style={{ fontSize: 9.5, height: 16, padding: "1px 6px" }}
            >
              <Briefcase size={8} />
              {t("card.company")}
            </span>
          )}
          {supervisor?.role === "university" && (
            <span
              className="chip shrink-0"
              style={{ fontSize: 9.5, height: 16, padding: "1px 6px" }}
            >
              <Building size={8} />
              {t("card.university")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {isNda && (
            <span
              className="chip"
              style={{
                color: "var(--c-warn)",
                borderColor:
                  "color-mix(in oklch, var(--c-warn) 30%, transparent)",
                background: "var(--c-warn-soft)",
              }}
            >
              <Lock size={8} />
              NDA
            </span>
          )}
          <span className="mono dim" style={{ fontSize: 10.5 }}>
            {(project.lang ?? "ru").toUpperCase()}
          </span>
          <span className="mono dim" style={{ fontSize: 10.5 }}>
            ·{" "}
            {formatRelative(project.updated_at, localeTag(), (time) =>
              t("card.today", { time }),
            )}
          </span>
        </div>
      </div>
    </div>
  );
};

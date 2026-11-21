import type { TFunction } from "i18next";
import {
  Archive,
  FileArchive,
  GitBranch,
  History,
  Pencil,
  Power,
  PowerOff,
  SearchCheck,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  shortRevision,
  sourceErrorText,
  sourceLocation,
  type CatalogSource,
} from "@entities/pack-catalog";
import { formatPastTime } from "@shared/lib";
import { ActionMenu, Badge, Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  needsAttention,
  sourceStatus,
  type SourceStatus,
} from "../lib/sourceStatus";
import { PackLine, PackList } from "./PackList";

export type SourceAction =
  "check" | "edit" | "replace" | "toggle" | "history" | "remove";

const SMALL = { fontSize: "0.71875rem", lineHeight: 1.5 } as const;

const STATUS_BADGE = {
  busy: "warning",
  failed: "error",
  off: "default",
  new: "info",
  blocked: "warning",
  update: "success",
  ok: "success",
} as const satisfies Record<SourceStatus, string>;

/** Состояние последней проверки словами. */
const checkLine = (source: CatalogSource, t: TFunction): string => {
  if (!source.checked_at) return t("source.notChecked");
  const when = formatPastTime(source.checked_at);
  if (source.error) return t("source.checkedFailed", { when });
  return source.check_ok
    ? t("source.checkedOk", { when })
    : t("source.checkedBlocked", { when });
};

/**
 * Карточка источника: что подключено (адрес и ref, архив), что применено, последняя
 * проверка и ошибка, метки включения, отслеживания и замены встроенного, паки с версиями.
 */
export const SourceCard = ({
  source,
  onAction,
  toggling = false,
}: {
  source: CatalogSource;
  onAction: (action: SourceAction, source: CatalogSource) => void;
  toggling?: boolean;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const location = sourceLocation(source);
  const errorText = source.error ? sourceErrorText(source.error) : null;
  const status = sourceStatus(source);
  return (
    <article
      className="card"
      style={{ padding: "0.75rem 0.875rem" }}
      data-testid={`pc-source-${source.id}`}
      data-enabled={source.enabled ? "true" : "false"}
    >
      <div
        className="flex items-start"
        style={{ gap: "0.5rem 0.75rem", flexWrap: "wrap" }}
      >
        <span
          className="adm-row-icon"
          data-tone={source.enabled ? "accent" : "neutral"}
          aria-hidden="true"
        >
          {source.kind === "git" ? (
            <GitBranch size="0.875rem" />
          ) : (
            <FileArchive size="0.875rem" />
          )}
        </span>
        <div
          className="flex flex-col"
          style={{ gap: "0.25rem", flex: "1 1 14rem", minWidth: 0 }}
        >
          <div
            className="flex items-center"
            style={{ gap: "0.375rem", flexWrap: "wrap" }}
          >
            <strong style={{ fontSize: "0.8125rem" }}>{source.label}</strong>
            <Badge variant="subtle">{t(`source.kind.${source.kind}`)}</Badge>
            <Badge
              variant={STATUS_BADGE[status]}
              title={status === "off" ? t("source.disabledHint") : undefined}
              data-testid="pc-source-status"
            >
              {status === "busy" && <Spinner size="sm" />}
              {status === "update"
                ? t("source.pending", { count: source.pending_versions })
                : t(`source.status.${status}`)}
            </Badge>
            {source.track && (
              <Badge variant="info" title={t("source.trackingHint")}>
                {t("source.tracking")}
              </Badge>
            )}
            {source.replace_builtin && (
              <Badge variant="accent">{t("source.replacesBuiltin")}</Badge>
            )}
          </div>
          <span
            className="mono dim truncate"
            style={SMALL}
            title={location}
            data-testid="pc-source-location"
          >
            {location}
            {source.kind === "git" && !source.ref && (
              <span className="dimmer"> @ {t("source.defaultBranch")}</span>
            )}
          </span>
          <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
            {t("source.packsPath", { path: source.packs_path })}
          </span>
          <span style={SMALL} data-testid="pc-source-applied">
            {source.applied_revision
              ? t("source.applied", {
                  revision: shortRevision(source.applied_revision),
                  when: formatPastTime(source.applied_at),
                })
              : t("source.notApplied")}
          </span>
          <span className="dim" style={SMALL} data-testid="pc-source-checked">
            {checkLine(source, t)}
          </span>
          {source.error && errorText && (
            <Notice
              tone="err"
              role="status"
              text={
                errorText === source.error.detail ? (
                  errorText
                ) : (
                  <>
                    {errorText}
                    <details>
                      <summary className="dim">
                        {t("source.errorDetail")}
                      </summary>
                      <span
                        className="mono"
                        style={{ overflowWrap: "anywhere" }}
                      >
                        {source.error.detail}
                      </span>
                    </details>
                  </>
                )
              }
            />
          )}
        </div>
        <div
          className="flex items-center"
          style={{ gap: "0.25rem", marginLeft: "auto" }}
        >
          <Button
            size="sm"
            variant={needsAttention(status) ? "primary" : "secondary"}
            disabled={source.busy}
            onClick={() => {
              onAction("check", source);
            }}
            data-testid="pc-source-check"
          >
            <SearchCheck size="0.75rem" />
            {t("source.check")}
          </Button>
          <ActionMenu
            label={t("source.actions", { name: source.label })}
            testId="pc-source-menu"
            items={[
              {
                id: "edit",
                label: t("source.edit"),
                icon: <Pencil size="0.875rem" />,
                onSelect: () => {
                  onAction("edit", source);
                },
                testId: "pc-source-edit",
              },
              ...(source.kind === "archive"
                ? [
                    {
                      id: "replace",
                      label: t("source.replaceArchive"),
                      icon: <Archive size="0.875rem" />,
                      onSelect: () => {
                        onAction("replace", source);
                      },
                      testId: "pc-source-replace",
                    },
                  ]
                : []),
              {
                id: "toggle",
                label: source.enabled
                  ? t("source.disable")
                  : t("source.enable"),
                icon: source.enabled ? (
                  <PowerOff size="0.875rem" />
                ) : (
                  <Power size="0.875rem" />
                ),
                disabled: toggling,
                onSelect: () => {
                  onAction("toggle", source);
                },
                testId: "pc-source-toggle",
              },
              {
                id: "history",
                label: t("source.history"),
                icon: <History size="0.875rem" />,
                onSelect: () => {
                  onAction("history", source);
                },
                testId: "pc-source-history",
              },
              {
                id: "remove",
                label: t("source.remove"),
                icon: <Trash2 size="0.875rem" />,
                danger: true,
                onSelect: () => {
                  onAction("remove", source);
                },
                testId: "pc-source-remove",
              },
            ]}
          />
        </div>
      </div>
      <div style={{ marginTop: "0.5rem", paddingLeft: "2.5rem" }}>
        <span className="dimmer" style={{ fontSize: "0.6875rem" }}>
          {t("source.packs")}
        </span>
        {source.packs.length === 0 ? (
          <p className="dim" style={{ ...SMALL, margin: 0 }}>
            {t("source.noPacks")}
          </p>
        ) : (
          <PackList>
            {source.packs.map((pack) => (
              <PackLine key={pack.id} pack={pack} />
            ))}
          </PackList>
        )}
      </div>
    </article>
  );
};

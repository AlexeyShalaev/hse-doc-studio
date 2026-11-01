import { useState } from "react";
import { Eye, KeyRound, Link2, LogIn, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ShareLink, ShareLinkList } from "@entities/share-link";
import { formatPastTime } from "@shared/lib";
import { formatLinkDate } from "../lib/format";
import {
  ActionMenu,
  Badge,
  Button,
  CopyField,
  EmptyState,
  ErrorState,
  Section,
  Spinner,
  Tooltip,
} from "@shared/ui";
import type { ActionMenuItem } from "@shared/ui/ActionMenu";
import { Notice } from "@shared/ui/ConflictKit";

export type ShareLinksViewProps = {
  status: "loading" | "error" | "ready";
  list: ShareLinkList | null;
  /** Ссылки, отозванные за 30 дней: приходят, только когда раскрыт список отозванных. */
  showRevoked: boolean;
  onToggleRevoked: () => void;
  onRetry?: () => void;
  onCreate: () => void;
  onEdit: (link: ShareLink) => void;
  onRotate: (link: ShareLink) => void;
  onRevoke: (link: ShareLink) => void;
  onVisits: (link: ShareLink) => void;
  onCopied?: () => void;
  /** Текущее время для «последний переход»; в галерее и тестах фиксировано. */
  now?: number;
};

const LinkChips = ({ link }: { link: ShareLink }) => {
  const { t } = useTranslation("shareLinks");
  return (
    <span className="share-link-chips">
      <Badge variant="accent">{t(`roles.${link.role}`)}</Badge>
      {link.role === "reader" && link.show_sources && (
        <Badge variant="subtle">
          <Eye size={11} aria-hidden /> {t("row.sources")}
        </Badge>
      )}
      {link.require_login && (
        <Badge variant="subtle">
          <LogIn size={11} aria-hidden /> {t("row.loginRequired")}
        </Badge>
      )}
      {link.has_password && (
        <Badge variant="subtle">
          <KeyRound size={11} aria-hidden /> {t("row.password")}
        </Badge>
      )}
      {link.state === "expired" ? (
        <Badge variant="warning">{t("row.expired")}</Badge>
      ) : link.state === "revoked" ? (
        <Badge variant="default">{t("row.revoked")}</Badge>
      ) : link.expires_at ? (
        <Badge variant="default">
          {t("row.until", { date: formatLinkDate(link.expires_at) })}
        </Badge>
      ) : null}
    </span>
  );
};

const VisitsLine = ({
  link,
  now,
  onVisits,
}: {
  link: ShareLink;
  now: number;
  onVisits: () => void;
}) => {
  const { t } = useTranslation("shareLinks");
  const { visits } = link;
  if (visits.opens === 0)
    return <span className="share-link-muted">{t("row.visitsNone")}</span>;
  const parts = [
    t("row.visits", { count: visits.opens }),
    t("row.visitors", { count: visits.visitors }),
    visits.last_at
      ? t("row.lastVisit", { when: formatPastTime(visits.last_at, now) })
      : null,
  ].filter(Boolean);
  return (
    <button
      type="button"
      className="share-link-visits-link"
      onClick={onVisits}
      data-testid={`share-link-visits-open-${link.id}`}
    >
      {parts.join(", ")}
    </button>
  );
};

const LinkRow = ({
  link,
  now,
  props,
}: {
  link: ShareLink;
  now: number;
  props: ShareLinksViewProps;
}) => {
  const { t } = useTranslation("shareLinks");
  const items: ActionMenuItem[] = [];
  if (link.editable) {
    items.push({
      id: "edit",
      label: link.state === "expired" ? t("row.extend") : t("row.edit"),
      onSelect: () => {
        props.onEdit(link);
      },
      testId: `share-link-edit-${link.id}`,
    });
    if (link.state !== "expired")
      items.push({
        id: "rotate",
        label: t("row.rotate"),
        onSelect: () => {
          props.onRotate(link);
        },
        testId: `share-link-rotate-${link.id}`,
      });
  }
  items.push({
    id: "visits",
    label: t("row.visitsAction"),
    onSelect: () => {
      props.onVisits(link);
    },
    testId: `share-link-visits-action-${link.id}`,
  });
  if (link.state !== "revoked" && link.editable)
    items.push({
      id: "revoke",
      label: t("row.revoke"),
      danger: true,
      onSelect: () => {
        props.onRevoke(link);
      },
      testId: `share-link-revoke-${link.id}`,
    });

  return (
    <li
      className="share-link-row"
      data-testid={`share-link-row-${link.id}`}
      data-state={link.state}
    >
      <div className="share-link-row-head">
        <span className="share-link-icon" aria-hidden>
          <Link2 size={14} />
        </span>
        <span className="share-link-label">{link.label}</span>
        <LinkChips link={link} />
        <span style={{ flex: 1 }} />
        <ActionMenu
          items={items}
          label={t("row.actions", { label: link.label })}
          testId={`share-link-actions-${link.id}`}
        />
      </div>
      <div className="share-link-row-meta">
        {link.created_by && (
          <span className="share-link-muted">
            {t("row.author", { name: link.created_by.name })}
          </span>
        )}
        <VisitsLine
          link={link}
          now={now}
          onVisits={() => {
            props.onVisits(link);
          }}
        />
      </div>
      {link.state === "blocked" && link.blocked_reason && (
        <Notice tone="warn" text={t(`blocked.${link.blocked_reason}`)} />
      )}
      {link.url && link.state !== "expired" && (
        <div data-testid={`share-link-url-${link.id}`}>
          <CopyField
            value={link.url}
            label={t("row.url")}
            {...(props.onCopied ? { onCopied: props.onCopied } : {})}
          />
        </div>
      )}
    </li>
  );
};

/** «Доступ по ссылке» в панели «Доступ»: список ссылок проекта и кнопка создания. */
export const ShareLinksView = (props: ShareLinksViewProps) => {
  const { t } = useTranslation("shareLinks");
  const { status, list } = props;
  const [mountedAt] = useState(() => Date.now());
  const now = props.now ?? mountedAt;
  const canCreate = list?.can_create ?? false;
  const active = list?.items.filter((x) => x.state !== "revoked") ?? [];
  const revoked = list?.items.filter((x) => x.state === "revoked") ?? [];
  const createButton = (
    <Button
      type="button"
      size="sm"
      onClick={props.onCreate}
      disabled={!canCreate}
      data-testid="share-link-create"
    >
      <Plus size={13} aria-hidden /> {t("section.create")}
    </Button>
  );

  return (
    <Section
      title={t("section.title")}
      description={t("section.description")}
      testId="project-share-links"
      actions={
        status === "ready" && !canCreate ? (
          <Tooltip content={t("section.createBlocked")}>
            <span>{createButton}</span>
          </Tooltip>
        ) : (
          createButton
        )
      }
    >
      {status === "loading" && (
        <div className="share-link-loading">
          <Spinner size="sm" />
        </div>
      )}
      {status === "error" && (
        <ErrorState
          title={t("section.error")}
          compact
          {...(props.onRetry ? { onRetry: props.onRetry } : {})}
        />
      )}
      {status === "ready" && list && (
        <div className="share-link-body">
          {list.forced_login && (
            <Notice tone="info" role="status" text={t("section.forcedLogin")} />
          )}
          {active.length === 0 ? (
            <EmptyState
              compact
              title={t("section.empty")}
              testId="share-links-empty"
            />
          ) : (
            <ul className="share-link-list" data-testid="share-links-list">
              {active.map((link) => (
                <LinkRow key={link.id} link={link} now={now} props={props} />
              ))}
            </ul>
          )}
          {list.revoked_count > 0 && (
            <button
              type="button"
              className="share-link-revoked-toggle"
              onClick={props.onToggleRevoked}
              aria-expanded={props.showRevoked}
              data-testid="share-links-revoked-toggle"
            >
              {props.showRevoked
                ? t("section.hideRevoked")
                : t("section.showRevoked", { count: list.revoked_count })}
            </button>
          )}
          {props.showRevoked && revoked.length > 0 && (
            <ul className="share-link-list" data-testid="share-links-revoked">
              {revoked.map((link) => (
                <LinkRow key={link.id} link={link} now={now} props={props} />
              ))}
            </ul>
          )}
        </div>
      )}
    </Section>
  );
};

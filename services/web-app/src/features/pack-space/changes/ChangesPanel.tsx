import {
  Check,
  Clock,
  ExternalLink,
  FileText,
  Folder,
  GitPullRequest,
  Info,
  TriangleAlert,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import {
  PACK_STUDIO_PATH,
  PackErrorText,
  type PackCiStatus,
  type PackDiagnostic,
  type PackVersionRef,
} from "@entities/pack-studio";
import { ActionMenu, Badge, Button, Spinner } from "@shared/ui";
import {
  changedOf,
  isNotesFinding,
  isNumberFinding,
  lintTargets,
} from "./deriveChangesStatus";
import {
  describeChanges,
  describePath,
  type ChangeItem,
} from "./describeChanges";
import { itemLabel } from "./itemLabel";
import type { ChangesData } from "./useChangesStatus";

/** Действия панели: диалоги и операции, которыми управляет контейнер. */
export type ChangesAction =
  "diff" | "checks" | "save" | "branch" | "take" | "access" | "reset";

export type ChangesPanelProps = {
  data: ChangesData;
  /** Названия документов открытой версии по идентификатору (из модели версии). */
  docNames: Readonly<Record<string, string>>;
  /** Название шаблона для заголовка группы. */
  templateName: (ref: PackVersionRef) => string;
  /** Идёт операция git: действия выключены. */
  busy: boolean;
  onClose: () => void;
  /** Открыть файл (его версия нужна, если он не в открытой). */
  onOpenFile: (ref: PackVersionRef | null, path: string) => void;
  onAction: (action: ChangesAction) => void;
  /** Находка без файла: открыть «Проверку» целиком. */
  onGoCheck: () => void;
  /** Блок «Что изменится у студентов» (`ImpactSlot`), контейнер кладёт его сюда. */
  impact?: ReactNode;
  /** Сообщение сверху (например, отказ «Забрать новое»). */
  notice?: ReactNode;
  /**
   * Место для S4. Действие у строки «нужны заметки» (кнопка «Написать»), раздел отправки между
   * проверками и подвалом и главная кнопка подвала. Пока S4 нет, они пусты.
   */
  notesAction?: ReactNode;
  submit?: ReactNode;
  primary?: ReactNode;
};

const MARK_ICON = { ok: Check, warn: TriangleAlert, err: X, wait: Clock };

const Mark = ({ tone }: { tone: keyof typeof MARK_ICON }) => {
  const Icon = MARK_ICON[tone];
  return (
    <span className="sp-ch-mark" data-tone={tone} aria-hidden="true">
      <Icon size="0.75rem" />
    </span>
  );
};

const Banner = ({
  tone,
  icon,
  children,
  testId,
}: {
  tone?: "ok" | "warn" | "err";
  icon: ReactNode;
  children: ReactNode;
  testId?: string;
}) => (
  <div
    className="sp-ch-banner"
    data-tone={tone}
    role="status"
    data-testid={testId}
  >
    {icon}
    <div className="sp-ch-banner-text">{children}</div>
  </div>
);

const ChangeRow = ({
  item,
  label,
  onOpen,
}: {
  item: ChangeItem;
  label: string;
  onOpen: (() => void) | null;
}) => {
  const { t } = useTranslation("packSpace");
  const body = (
    <>
      <FileText size="0.875rem" aria-hidden="true" />
      <span className="sp-ch-item-text">{label}</span>
      {item.status !== "modified" && (
        <span className="sp-ch-tag" data-status={item.status}>
          {t(`changes.what.tag.${item.status}`)}
        </span>
      )}
    </>
  );
  return (
    <li>
      {onOpen ? (
        <button
          type="button"
          className="sp-ch-item"
          onClick={onOpen}
          title={t("changes.what.openItem", { what: label })}
          data-testid="sp-ch-item"
        >
          {body}
        </button>
      ) : (
        <span className="sp-ch-item" data-testid="sp-ch-item">
          {body}
        </span>
      )}
    </li>
  );
};

const WhatChanged = ({
  data,
  docNames,
  templateName,
  onOpenFile,
  onAction,
}: Pick<
  ChangesPanelProps,
  "data" | "docNames" | "templateName" | "onOpenFile" | "onAction"
>) => {
  const { t } = useTranslation("packSpace");
  const { raw } = data;
  const groups = useMemo(
    () => describeChanges(changedOf(raw), raw.open, raw.copy?.dir ?? null),
    [raw],
  );
  return (
    <section className="sp-ch-section" data-testid="sp-ch-what">
      <h3 className="sp-ch-h">{t("changes.what.title")}</h3>
      {groups.map((group) => (
        <div className="sp-ch-group" key={group.key}>
          <div className="sp-ch-group-head">
            <span>
              {group.copy && group.version
                ? t("changes.what.groupCopy", {
                    version: group.version.version,
                  })
                : group.version
                ? t("changes.what.group", {
                    template: templateName(group.version),
                    version: group.version.version,
                  })
                : group.pack
                  ? t("changes.what.groupPack", { pack: group.pack })
                  : t("changes.what.groupOther")}
            </span>
            <span>{t("changes.what.files", { count: group.files })}</span>
          </div>
          <ul className="sp-ch-list">
            {group.items.map((item) => {
              // Документы других версий называем по идентификатору: имён их модель не читалась.
              const names =
                group.version?.version === raw.open.version ? docNames : {};
              const label = itemLabel(t, item.kind, item.doc, names);
              const path = item.path;
              return (
                <ChangeRow
                  key={item.key}
                  // У копии «новое» не значит ничего: новая вся папка, мои правки это отличия.
                  item={group.copy ? { ...item, status: "modified" } : item}
                  label={label}
                  onOpen={
                    path
                      ? () => {
                          onOpenFile(group.version, path);
                        }
                      : null
                  }
                />
              );
            })}
          </ul>
        </div>
      ))}
      <button
        type="button"
        className="sp-ch-link"
        onClick={() => {
          onAction("diff");
        }}
        data-testid="sp-ch-diff"
      >
        {t("changes.what.diff")}
      </button>
    </section>
  );
};

/** Находки проверки для списка: ошибки без заметок (они отдельным шагом) и замечания. */
const findingsOf = (data: ChangesData) => {
  const errors: PackDiagnostic[] = [];
  const warnings: PackDiagnostic[] = [];
  for (const report of data.raw.lint) {
    for (const finding of report.findings) {
      if (finding.severity === "warning") warnings.push(finding);
      else if (
        report.released ||
        !(isNotesFinding(finding) || isNumberFinding(finding))
      ) {
        errors.push(finding);
      }
    }
  }
  return { errors, warnings };
};

const Checks = ({
  data,
  docNames,
  notesAction,
  onOpenFile,
  onGoCheck,
}: Pick<ChangesPanelProps, "data" | "docNames" | "notesAction"> & {
  onOpenFile: ChangesPanelProps["onOpenFile"];
  onGoCheck: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const [warningsOpen, setWarningsOpen] = useState(false);
  const { status, raw } = data;
  const { errors, warnings } = useMemo(() => findingsOf(data), [data]);
  const waiting =
    raw.lint.length < lintTargets(changedOf(raw), raw.open).length;

  const where = (finding: PackDiagnostic): string => {
    if (finding.path === null) {
      return t("changes.checks.whereVersion", { version: raw.open.version });
    }
    const info = describePath(finding.path);
    const names = info.version?.version === raw.open.version ? docNames : {};
    return itemLabel(t, info.kind, info.doc, names);
  };
  const line = (finding: PackDiagnostic): string =>
    finding.line !== null
      ? t("changes.checks.where", {
          where: where(finding),
          line: finding.line,
          message: finding.message,
        })
      : t("changes.checks.whereNoLine", {
          where: where(finding),
          message: finding.message,
        });
  const go = (finding: PackDiagnostic) => {
    if (finding.path === null) onGoCheck();
    else onOpenFile(describePath(finding.path).version, finding.path);
  };

  return (
    <section className="sp-ch-section" data-testid="sp-ch-checks">
      <h3 className="sp-ch-h">
        {errors.length > 0
          ? t("changes.checks.errorsTitle")
          : t("changes.checks.title")}
      </h3>
      {waiting && errors.length === 0 && (
        <div className="sp-ch-row" role="status">
          <Mark tone="wait" />
          <div className="sp-ch-row-text">{t("changes.checks.running")}</div>
          <span />
        </div>
      )}
      {!waiting && errors.length === 0 && status.errors === 0 && (
        <div className="sp-ch-row" data-testid="sp-ch-ok">
          <Mark tone="ok" />
          <div className="sp-ch-row-text">{t("changes.checks.ok")}</div>
          <span />
        </div>
      )}
      {errors.map((finding, index) => (
        <div
          className="sp-ch-row"
          key={`${finding.path ?? ""}:${String(finding.line)}:${String(index)}`}
          data-testid="sp-ch-error"
        >
          <Mark tone="err" />
          <div className="sp-ch-row-text">{line(finding)}</div>
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              go(finding);
            }}
          >
            {t("changes.checks.go")}
          </Button>
        </div>
      ))}
      {status.notesNeeded && (
        <div className="sp-ch-row" data-testid="sp-ch-notes">
          <Mark tone="wait" />
          <div className="sp-ch-row-text">{t("changes.checks.notes")}</div>
          {notesAction ?? <span />}
        </div>
      )}
      {warnings.length > 0 && (
        <>
          <div className="sp-ch-row" data-testid="sp-ch-warnings">
            <Mark tone="warn" />
            <div className="sp-ch-row-text">
              {t("changes.checks.warnings", { count: warnings.length })}
            </div>
            <Button
              size="xs"
              variant="ghost"
              aria-expanded={warningsOpen}
              onClick={() => {
                setWarningsOpen((open) => !open);
              }}
            >
              {warningsOpen
                ? t("changes.checks.hide")
                : t("changes.checks.show")}
            </Button>
          </div>
          {warningsOpen &&
            warnings.map((finding, index) => (
              <div
                className="sp-ch-row"
                key={`${finding.path ?? ""}:${String(finding.line)}:${String(index)}`}
              >
                <span />
                <div className="sp-ch-row-text sp-ch-muted">
                  {line(finding)}
                </div>
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => {
                    go(finding);
                  }}
                >
                  {t("changes.checks.go")}
                </Button>
              </div>
            ))}
        </>
      )}
    </section>
  );
};

/** Проверки на хостинге: идут, прошли, не прошли, ждут одобрения. */
const HostChecks = ({
  checks,
  progress,
  ci,
  onDetails,
}: {
  checks: "pending" | "passed" | "failed" | "awaiting_approval" | "unknown";
  progress: { done: number; total: number } | null;
  ci: PackCiStatus | null;
  onDetails: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const tone =
    checks === "passed" ? "ok" : checks === "failed" ? "err" : "wait";
  const text =
    checks === "pending"
      ? progress
        ? t("changes.request.pending", progress)
        : t("changes.request.pendingNoCount")
      : t(
          `changes.request.${checks === "awaiting_approval" ? "awaiting" : checks}`,
        );
  return (
    <section className="sp-ch-section" data-testid="sp-ch-host">
      <h3 className="sp-ch-h">{t("changes.request.hostChecks")}</h3>
      <div className="sp-ch-row">
        <Mark tone={checks === "unknown" ? "warn" : tone} />
        <div className="sp-ch-row-text" role="status">
          {text}
        </div>
        <Button size="xs" variant="ghost" onClick={onDetails} disabled={!ci}>
          {t("changes.request.details")}
        </Button>
      </div>
    </section>
  );
};

/** Заголовок: название, состояние версии или запроса одним словом. */
const Header = ({
  data,
  headingRef,
  onClose,
}: {
  data: ChangesData;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { status, raw } = data;
  const { request } = status;
  let badge: ReactNode = null;
  if (status.workspaceKind === "folder") {
    badge = <Badge>{t("changes.badge.folder")}</Badge>;
  } else if (request.kind === "open") {
    badge = (
      <Badge variant="accent">
        {t("changes.badge.open", { label: request.label })}
      </Badge>
    );
  } else if (request.kind === "merged") {
    badge = <Badge variant="success">{t("changes.badge.merged")}</Badge>;
  } else if (request.kind === "closed") {
    badge = <Badge variant="warning">{t("changes.badge.closed")}</Badge>;
  } else if (status.connection === "ready") {
    badge = status.released ? (
      <Badge>
        {t("changes.badge.released", { version: raw.open.version })}
      </Badge>
    ) : (
      <Badge variant="warning">
        {t("changes.badge.draft", { version: raw.open.version })}
      </Badge>
    );
  }
  return (
    <div className="sp-ch-head">
      <h2 className="sp-ch-title" tabIndex={-1} ref={headingRef}>
        {t("changes.title")}
      </h2>
      {badge}
      <Button
        size="xs"
        variant="ghost"
        aria-label={t("changes.close")}
        title={t("changes.close")}
        onClick={onClose}
        data-testid="sp-ch-close"
      >
        <X size="0.9375rem" aria-hidden="true" />
      </Button>
    </div>
  );
};

const Message = ({
  icon,
  title,
  text,
  children,
}: {
  icon: ReactNode;
  title: string;
  text?: ReactNode;
  children?: ReactNode;
}) => (
  <div className="sp-ch-empty">
    <span className="sp-ch-empty-ico" aria-hidden="true">
      {icon}
    </span>
    <h3>{title}</h3>
    {text ? <p>{text}</p> : null}
    {children}
  </div>
);

/**
 * Панель «Изменения» (pack-studio-ux.md, 5.6), только отображение: всё, что нужно, приходит
 * props. Разделы сверху вниз: что изменено, что изменится у студентов, проверки, затем итог
 * запроса. Каждый раздел пуст и исчезает, когда показывать нечего. Действия и запросы ведёт
 * контейнер `ChangesDrawer`.
 */
export const ChangesPanel = ({
  data,
  docNames,
  templateName,
  busy,
  onClose,
  onOpenFile,
  onAction,
  onGoCheck,
  impact,
  notice,
  notesAction,
  submit,
  primary,
}: ChangesPanelProps) => {
  const { t } = useTranslation("packSpace");
  const { status, raw } = data;
  const git = raw.git;
  const { request } = status;
  const headingRef = useRef<HTMLHeadingElement>(null);
  // Фокус в панель при открытии: Esc закрывает её, а скринридер читает заголовок.
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, []);

  let body: ReactNode;
  let foot: ReactNode = null;
  if (status.connection === "cloning") {
    body = (
      <Message
        icon={<Spinner size="sm" />}
        title={t("changes.state.cloningTitle")}
        text={t("changes.state.cloningLead")}
      />
    );
  } else if (status.connection === "failed") {
    body = (
      <Message
        icon={<TriangleAlert size="1.25rem" />}
        title={t("changes.state.connectTitle")}
        text={t("changes.state.connectLead")}
      />
    );
  } else if (status.workspaceKind === "folder") {
    body = (
      <>
        <Banner
          icon={<Folder size="1rem" aria-hidden="true" />}
          testId="sp-ch-folder"
        >
          <strong>{t("changes.folder.title")}</strong>
          {raw.workspace.folder && (
            <span className="sp-ch-path">{raw.workspace.folder}</span>
          )}
        </Banner>
        <p className="sp-ch-muted">{t("changes.folder.lead")}</p>
      </>
    );
    foot = (
      <Button asChild>
        <Link to={PACK_STUDIO_PATH}>{t("changes.folder.connect")}</Link>
      </Button>
    );
  } else if (status.load === "loading") {
    body = (
      <div className="sp-ch-loading" role="status" data-testid="sp-ch-loading">
        <Spinner size="sm" />
        {t("changes.state.loading")}
      </div>
    );
  } else if (status.load === "failed") {
    body = (
      <Message
        icon={<TriangleAlert size="1.25rem" />}
        title={t("changes.state.failedTitle")}
        text={data.error ? <PackErrorText error={data.error} /> : undefined}
      >
        <Button variant="secondary" size="sm" onClick={data.retry}>
          {t("changes.state.retry")}
        </Button>
      </Message>
    );
  } else {
    const sent = request.kind !== "none";
    const showWork =
      status.changedFiles > 0 &&
      (request.kind === "none" || request.kind === "open");
    const showVerdict =
      showWork && (request.kind === "none" || request.newEdits);
    body = (
      <>
        {notice}
        {status.behind > 0 &&
          (request.kind === "none" || request.kind === "open") && (
            <Banner
              tone="warn"
              icon={<Info size="1rem" aria-hidden="true" />}
              testId="sp-ch-behind"
            >
              <strong>{t("changes.behind.title")}</strong>
              <span>{t("changes.behind.lead")}</span>
              <Button
                size="xs"
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  onAction("take");
                }}
              >
                {t("changes.behind.take")}
              </Button>
            </Banner>
          )}
        {request.kind === "open" && (
          <>
            <Banner
              tone="ok"
              icon={<Check size="1rem" aria-hidden="true" />}
              testId="sp-ch-open"
            >
              <strong>
                {t("changes.request.openTitle", { label: request.label })}
              </strong>
              <span>{t("changes.request.openLead")}</span>
            </Banner>
            <HostChecks
              checks={request.checks}
              progress={request.progress}
              ci={raw.ci}
              onDetails={() => {
                onAction("checks");
              }}
            />
            <section className="sp-ch-section">
              <h3 className="sp-ch-h">{t("changes.request.next")}</h3>
              <p className="sp-ch-muted">
                {request.newEdits
                  ? t("changes.request.nextEdits")
                  : t("changes.request.nextClean")}
              </p>
            </section>
          </>
        )}
        {request.kind === "merged" && (
          <Banner
            tone="ok"
            icon={<Check size="1rem" aria-hidden="true" />}
            testId="sp-ch-merged"
          >
            <strong>
              {t("changes.request.mergedTitle", { label: request.label })}
            </strong>
            <span>{t("changes.request.mergedLead")}</span>
            <span>{t("changes.request.mergedNext")}</span>
          </Banner>
        )}
        {request.kind === "closed" && (
          <Banner
            tone="warn"
            icon={<Info size="1rem" aria-hidden="true" />}
            testId="sp-ch-closed"
          >
            <strong>
              {t("changes.request.closedTitle", { label: request.label })}
            </strong>
            <span>{t("changes.request.closedLead")}</span>
          </Banner>
        )}
        {!sent && status.changedFiles === 0 && (
          <Message
            icon={<GitPullRequest size="1.25rem" />}
            title={t("changes.empty.title")}
            text={
              status.released
                ? t("changes.empty.released", { version: raw.open.version })
                : t("changes.empty.draft")
            }
          />
        )}
        {request.kind === "none" && status.changedFiles > 0 && (
          <p className="sp-ch-muted" data-testid="sp-ch-intro">
            {t("changes.intro")}
          </p>
        )}
        {showWork && (
          <WhatChanged
            data={data}
            docNames={docNames}
            templateName={templateName}
            onOpenFile={onOpenFile}
            onAction={onAction}
          />
        )}
        {showVerdict && status.errors === 0 && impact}
        {showVerdict && (
          <Checks
            data={data}
            docNames={docNames}
            notesAction={notesAction}
            onOpenFile={onOpenFile}
            onGoCheck={onGoCheck}
          />
        )}
        {showVerdict && status.errors > 0 && impact}
        {showVerdict && submit}
        {git && (request.kind === "none" || request.kind === "open") && (
          <p className="sp-ch-muted" data-testid="sp-ch-where">
            {git.branch
              ? t("changes.where.branch", { branch: git.branch })
              : t("changes.where.noBranch")}
            {git.branch && git.ahead > 0
              ? ` ${t("changes.where.ahead", { count: git.ahead })}`
              : ""}
          </p>
        )}
      </>
    );
    if (request.kind === "open" && request.url) {
      foot = (
        // Когда рядом главная кнопка «Обновить запрос», ссылка на сам запрос вторична.
        <Button asChild variant={primary ? "secondary" : "primary"}>
          <a href={request.url} target="_blank" rel="noopener noreferrer">
            <ExternalLink size="0.8125rem" aria-hidden="true" />
            {t("changes.request.open", { label: request.label })}
          </a>
        </Button>
      );
    } else if (request.kind === "merged") {
      foot = (
        <Button
          disabled={busy}
          onClick={() => {
            onAction("reset");
          }}
        >
          {t("changes.request.startNew")}
        </Button>
      );
    } else if (request.kind === "closed") {
      foot = (
        <Button
          disabled={busy}
          onClick={() => {
            onAction("reset");
          }}
        >
          {t("changes.request.reset")}
        </Button>
      );
    }
  }

  const live =
    status.connection === "ready" &&
    status.workspaceKind === "git" &&
    status.load === "ready";
  return (
    <div className="sp-ch" id="sp-changes-panel" data-testid="sp-changes-panel">
      <Header data={data} headingRef={headingRef} onClose={onClose} />
      <div className="sp-ch-body">{body}</div>
      <div className="sp-ch-foot">
        {primary}
        {foot}
        <Button variant="secondary" onClick={onClose}>
          {t("changes.footer.close")}
        </Button>
        <span className="sp-ch-foot-grow" />
        {live && git && (
          <ActionMenu
            label={t("changes.menu.label")}
            testId="sp-ch-menu"
            align="end"
            items={[
              {
                id: "save",
                label: t("changes.menu.save"),
                disabled: busy || !git.dirty,
                onSelect: () => {
                  onAction("save");
                },
                testId: "sp-ch-menu-save",
              },
              {
                id: "branch",
                label: t("changes.menu.branch"),
                disabled: busy,
                onSelect: () => {
                  onAction("branch");
                },
                testId: "sp-ch-menu-branch",
              },
              {
                id: "take",
                label: t("changes.menu.take"),
                disabled: busy || git.branch === null,
                onSelect: () => {
                  onAction("take");
                },
                testId: "sp-ch-menu-take",
              },
              {
                id: "access",
                label: t("changes.menu.access"),
                onSelect: () => {
                  onAction("access");
                },
                testId: "sp-ch-menu-access",
              },
              ...(git.compare_url
                ? [
                    {
                      id: "compare",
                      label: t("changes.menu.compare"),
                      onSelect: () => {
                        window.open(
                          git.compare_url ?? "",
                          "_blank",
                          "noopener,noreferrer",
                        );
                      },
                      testId: "sp-ch-menu-compare",
                    },
                  ]
                : []),
              {
                id: "reset",
                label: t("changes.menu.reset"),
                danger: true,
                disabled: busy,
                onSelect: () => {
                  onAction("reset");
                },
                testId: "sp-ch-menu-reset",
              },
            ]}
          />
        )}
      </div>
    </div>
  );
};

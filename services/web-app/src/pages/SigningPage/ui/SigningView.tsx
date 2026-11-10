import { useState } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { FileQuestion } from "lucide-react";
import { useIsCompactWidth } from "@shared/lib";
import { Button, EmptyState, ErrorState, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  signingPdfUrl,
  type SigningTask,
  type SigningTaskDoc,
} from "@entities/signing-route";
import { SIGNING_INBOX_PATH } from "@features/inbox";
import { newVersionDocs, signingStatus } from "../lib/signingState";
import type { SigningExtension, SigningSlotContext } from "../model/extension";
import type { SigningPageState } from "../model/useSigningPage";
import { MethodSummary } from "./MethodSummary";
import { ReturnDialog } from "./ReturnDialog";
import { RouteHistory } from "./RouteHistory";
import { RouteProgress } from "./RouteProgress";
import { SigningActions } from "./SigningActions";
import { SigningDocs } from "./SigningDocs";
import { SigningHeader } from "./SigningHeader";
import { StatusCard } from "./StatusCard";
import { DivergenceBanner, NewVersionNotice } from "./VersionNotices";
import "./signing.css";

export type SigningViewProps = {
  state: SigningPageState;
  /** Текущее время (мс): просрочен ли срок. */
  now: number;
  /** Действие идёт: кнопки заняты. */
  busy?: boolean;
  approving?: boolean;
  /** Код отказа последнего действия (`doc_changed`, `not_your_turn`, ..., `unknown`). */
  failure?: string | null;
  /** Пояснение сервера к отказу без своего текста (`unknown`). */
  failureDetail?: string | null;
  onDismissFailure?: () => void;
  onApprove: () => void;
  /** Вернуть на доработку; true закрывает окно. */
  onReturn: (comment: string) => Promise<boolean>;
  onRetry?: () => void;
  /** Блоки подписи среза W5 и контекст для них. */
  extension?: SigningExtension;
  slot?: (task: SigningTask) => SigningSlotContext;
  /** Адрес PDF документа; галерея подставляет образец. */
  pdfUrlOf?: (doc: SigningTaskDoc) => string;
  /** Под карточкой состояния: кто не принял приглашение и ссылки для них (страница берёт из маршрута). */
  note?: React.ReactNode;
};

const defaultPdfUrl = (doc: SigningTaskDoc) => signingPdfUrl(doc.pdf_url);

const noop = () => Promise.resolve(null);

/** Контекст без действий: галерея и тесты вида. */
const idleSlot = (task: SigningTask): SigningSlotContext => ({
  projectId: task.route.project.id,
  routeId: task.route.id,
  task,
  busy: false,
  failure: null,
  expected: {},
  approve: noop,
  sign: noop,
});

/**
 * Страница подписанта (docs/design/signing-route.md, 3.2): шапка, ход маршрута, что нужно,
 * документы с рамками своих слотов, «Как подписать», «Согласовать» и «Вернуть на доработку».
 * Без рабочего места проекта; уже десктопа кнопки прилипают к низу экрана.
 */
export const SigningView = ({
  state,
  now,
  busy = false,
  approving = false,
  failure = null,
  failureDetail = null,
  onDismissFailure,
  onApprove,
  onReturn,
  onRetry,
  extension,
  slot = idleSlot,
  pdfUrlOf = defaultPdfUrl,
  note,
}: SigningViewProps) => {
  const { t } = useTranslation("signing");
  const compact = useIsCompactWidth();
  const [returning, setReturning] = useState(false);

  if (state.kind === "loading") {
    return (
      <div
        className="sgn-scroll"
        data-testid="signing-page"
        data-state="loading"
      >
        <div className="sgn-center" aria-label={t("page.loading")}>
          <Spinner size="lg" />
        </div>
      </div>
    );
  }
  if (state.kind === "not_found" || state.kind === "error") {
    const notFound = state.kind === "not_found";
    return (
      <div
        className="sgn-scroll"
        data-testid="signing-page"
        data-state={state.kind}
      >
        <div className="sgn-page">
          {notFound ? (
            <EmptyState
              framed
              icon={<FileQuestion size="1.125rem" />}
              title={t("page.notFoundTitle")}
              description={t("page.notFoundBody")}
              action={
                <div
                  className="flex"
                  style={{ gap: "0.5rem", flexWrap: "wrap" }}
                >
                  <Button asChild size="sm">
                    <Link to={SIGNING_INBOX_PATH}>{t("page.inbox")}</Link>
                  </Button>
                  <Button asChild size="sm" variant="secondary">
                    <Link to="/">{t("page.home")}</Link>
                  </Button>
                </div>
              }
            />
          ) : (
            <ErrorState
              framed
              title={t("page.errorTitle")}
              {...(onRetry ? { onRetry } : {})}
            />
          )}
        </div>
      </div>
    );
  }

  const { task } = state;
  const status = signingStatus(task);
  const ctx = slot(task);
  const action = status.kind === "turn" ? status.action : null;
  const method = action
    ? (extension?.method?.(ctx) ?? <MethodSummary task={task} />)
    : null;
  const actions = action ? (
    <SigningActions
      task={task}
      action={action}
      busy={busy}
      approving={approving}
      primary={extension?.primary?.(ctx) ?? undefined}
      onApprove={onApprove}
      onReturn={() => {
        // Отказ прошлого действия к окну возврата не относится.
        onDismissFailure?.();
        setReturning(true);
      }}
    />
  ) : null;

  return (
    <div
      className="sgn-scroll"
      data-testid="signing-page"
      data-state={status.kind}
    >
      <div className="sgn-page">
        {/* В раунде новой версии сообщение автора стоит в плашке «Новая версия». */}
        <SigningHeader
          task={task}
          now={now}
          hideMessage={newVersionDocs(task) !== null}
        />
        <RouteProgress task={task} />
        <StatusCard task={task} status={status} />
        <DivergenceBanner task={task} />
        <NewVersionNotice task={task} status={status} />
        {note}
        {failure && !returning && (
          <div data-testid="signing-failure" data-code={failure}>
            <Notice
              tone="err"
              role="alert"
              text={
                failure === "unknown" && failureDetail
                  ? t("failure.unknownDetail", { detail: failureDetail })
                  : t(`failure.${failure}`)
              }
              action={
                onDismissFailure && (
                  <Button
                    type="button"
                    size="xs"
                    variant="ghost"
                    onClick={onDismissFailure}
                  >
                    {t("failure.dismiss")}
                  </Button>
                )
              }
            />
          </div>
        )}
        <div className="sgn-grid">
          <SigningDocs task={task} pdfUrlOf={pdfUrlOf} />
          <aside className="sgn-side">
            {method}
            {!compact && actions && <div className="sgn-card">{actions}</div>}
            <RouteHistory events={task.events} />
          </aside>
        </div>
        {compact && actions && <div className="sgn-actionbar">{actions}</div>}
      </div>
      <ReturnDialog
        key={String(returning)}
        open={returning}
        busy={busy}
        error={returning ? failure : null}
        projectId={task.route.project.id}
        onClose={() => {
          setReturning(false);
        }}
        onSubmit={(comment) => {
          void onReturn(comment).then((ok) => {
            if (ok) setReturning(false);
          });
        }}
      />
    </div>
  );
};

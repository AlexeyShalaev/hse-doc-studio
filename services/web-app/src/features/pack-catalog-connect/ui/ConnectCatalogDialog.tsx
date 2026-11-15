import { useId, useState } from "react";
import { Power, PowerOff, SearchCheck, Unplug } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  CatalogApplyResult,
  CatalogCheckPending,
  CatalogCheckReport,
  CatalogFlowError,
  catalogErrorText,
  hasBuiltinConflict,
  shortRevision,
  sourceErrorText,
  useApplyWorkspaceCatalog,
  useCheckWorkspaceCatalog,
  useDisconnectWorkspaceCatalog,
  useSetWorkspaceCatalogEnabled,
  useWorkspaceCatalog,
  type CatalogSource,
} from "@entities/pack-catalog";
import { formatPastTime } from "@shared/lib";
import { Badge, Button, ErrorState, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

const SMALL = { fontSize: "0.75rem", lineHeight: 1.5 } as const;

/** Что сейчас с папкой в каталоге: подключена ли, что применено, включена ли. */
const SourceState = ({ source }: { source: CatalogSource | null }) => {
  const { t } = useTranslation("packStudio");
  if (!source) {
    return (
      <p
        className="dim"
        style={{ ...SMALL, margin: 0 }}
        data-testid="ws-catalog-none"
      >
        {t("catalog.notConnected")}
      </p>
    );
  }
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.25rem" }}
      data-testid="ws-catalog-state"
    >
      <div
        className="flex items-center"
        style={{ gap: "0.5rem", flexWrap: "wrap" }}
      >
        <span style={SMALL}>{t("catalog.connected")}</span>
        <Badge
          variant={source.enabled ? "success" : "default"}
          title={source.enabled ? undefined : t("catalog.offHint")}
        >
          {source.enabled ? t("catalog.on") : t("catalog.off")}
        </Badge>
      </div>
      <span className="dim" style={SMALL}>
        {source.applied_revision
          ? t("catalog.applied", {
              revision: shortRevision(source.applied_revision),
              when: formatPastTime(source.applied_at),
            })
          : t("catalog.notApplied")}
      </span>
      {!source.enabled && (
        <span className="dim" style={SMALL}>
          {t("catalog.offHint")}
        </span>
      )}
      {source.pending_versions > 0 && (
        <span style={SMALL}>
          {t("catalog.pending", { count: source.pending_versions })}
        </span>
      )}
      {source.error && (
        <Notice tone="err" role="status" text={sourceErrorText(source.error)} />
      )}
    </div>
  );
};

const ConnectFlow = ({
  workspaceId,
  onClose,
}: {
  workspaceId: string;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packStudio");
  const { t: tc } = useTranslation("packCatalog");
  const state = useWorkspaceCatalog(workspaceId);
  const check = useCheckWorkspaceCatalog(workspaceId);
  const apply = useApplyWorkspaceCatalog(workspaceId);
  const toggle = useSetWorkspaceCatalogEnabled(workspaceId);
  const disconnect = useDisconnectWorkspaceCatalog(workspaceId);
  const [replace, setReplace] = useState<boolean | null>(null);
  const [confirming, setConfirming] = useState(false);
  const replaceId = useId();

  const source = state.data?.source ?? null;
  const replaceBuiltin = replace ?? source?.replace_builtin ?? false;
  const report = check.data;
  const applied = apply.data;
  const busy =
    check.isPending ||
    apply.isPending ||
    toggle.isPending ||
    disconnect.isPending;

  const runCheck = () => {
    apply.reset();
    check.mutate(replaceBuiltin);
  };
  const close = () => {
    if (apply.isPending || disconnect.isPending) return;
    onClose();
  };

  let body;
  if (state.isPending) {
    body = <Spinner />;
  } else if (state.isError) {
    body = (
      <ErrorState
        compact
        description={catalogErrorText(state.error)}
        onRetry={() => void state.refetch()}
      />
    );
  } else if (applied) {
    body = <CatalogApplyResult result={applied} />;
  } else {
    body = (
      <>
        <SourceState source={source} />
        <div className="flex flex-col" style={{ gap: "0.125rem" }}>
          <label
            htmlFor={replaceId}
            className="flex items-center"
            style={{ gap: "0.5rem", fontSize: "0.75rem" }}
          >
            <input
              id={replaceId}
              type="checkbox"
              checked={replaceBuiltin}
              disabled={busy}
              onChange={(e) => {
                setReplace(e.target.checked);
              }}
              style={{ accentColor: "var(--accent)" }}
              data-testid="ws-catalog-replace"
            />
            {t("catalog.replaceBuiltin")}
          </label>
          <p className="hint" style={{ marginLeft: "1.5rem" }}>
            {t("catalog.replaceBuiltinHint")}
          </p>
        </div>
        {check.isPending && <CatalogCheckPending />}
        {check.isError && (
          <CatalogFlowError
            error={check.error}
            onRecheck={runCheck}
            rechecking={busy}
          />
        )}
        {apply.isError && (
          <CatalogFlowError
            error={apply.error}
            onRecheck={runCheck}
            rechecking={busy}
          />
        )}
        {(toggle.error ?? disconnect.error) && (
          <Notice
            tone="err"
            role="alert"
            text={catalogErrorText(toggle.error ?? disconnect.error)}
          />
        )}
        {report && (
          <CatalogCheckReport
            check={report}
            footer={
              hasBuiltinConflict(report) && !replaceBuiltin ? (
                <Notice
                  tone="info"
                  role="status"
                  text={t("catalog.builtinConflict")}
                />
              ) : undefined
            }
          />
        )}
      </>
    );
  }

  return (
    <>
      <Modal
        isOpen={!confirming}
        onClose={close}
        title={t("catalog.title")}
        description={t("catalog.lead")}
        width={640}
        footer={
          applied ? (
            <Button onClick={close} data-testid="ws-catalog-done">
              {t("catalog.done")}
            </Button>
          ) : (
            <>
              {source && (
                <>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => {
                      toggle.mutate(!source.enabled);
                    }}
                    data-testid="ws-catalog-toggle"
                  >
                    {source.enabled ? (
                      <PowerOff size="0.75rem" />
                    ) : (
                      <Power size="0.75rem" />
                    )}
                    {source.enabled
                      ? t("catalog.disable")
                      : t("catalog.enable")}
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => {
                      disconnect.reset();
                      setConfirming(true);
                    }}
                    data-testid="ws-catalog-disconnect"
                  >
                    <Unplug size="0.75rem" />
                    {t("catalog.disconnect")}
                  </Button>
                </>
              )}
              <Button
                variant="secondary"
                disabled={busy || state.isPending}
                onClick={runCheck}
                data-testid="ws-catalog-check"
              >
                {check.isPending ? (
                  <Spinner size="sm" />
                ) : (
                  <SearchCheck size="0.75rem" />
                )}
                {t("catalog.check")}
              </Button>
              <Button
                disabled={!report?.ok || busy}
                onClick={() => {
                  if (report) apply.mutate(report.revision);
                }}
                data-testid="ws-catalog-apply"
              >
                {apply.isPending && <Spinner size="sm" />}
                {apply.isPending ? tc("flow.applying") : tc("flow.apply")}
              </Button>
            </>
          )
        }
      >
        <div className="flex flex-col" style={{ gap: "0.75rem" }}>
          {body}
        </div>
      </Modal>
      <Modal
        isOpen={confirming}
        onClose={() => {
          if (!disconnect.isPending) setConfirming(false);
        }}
        title={t("catalog.disconnectTitle")}
        description={t("catalog.disconnectLead")}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirming(false);
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={disconnect.isPending}
              onClick={() => {
                disconnect.mutate(undefined, {
                  onSettled: () => {
                    check.reset();
                    setConfirming(false);
                  },
                });
              }}
              data-testid="ws-catalog-disconnect-confirm"
            >
              {t("catalog.disconnect")}
            </Button>
          </>
        }
      />
    </>
  );
};

/**
 * «Подключить к каталогу этой Студии» (template-studio.md, 10.3, локально): папка рабочего
 * пространства становится источником каталога, выпущенные версии её паков появляются в
 * мастере проекта. Тот же отчёт «Проверить», что в админке установки.
 */
export const ConnectCatalogDialog = ({
  workspaceId,
  isOpen,
  onClose,
}: {
  workspaceId: string;
  isOpen: boolean;
  onClose: () => void;
}) =>
  isOpen ? <ConnectFlow workspaceId={workspaceId} onClose={onClose} /> : null;

import { useEffect, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  CatalogApplyResult,
  CatalogCheckPending,
  CatalogCheckReport,
  CatalogFlowError,
  useApplySource,
  useCheckSource,
  type CatalogSource,
} from "@entities/pack-catalog";
import { Button, Modal, Spinner } from "@shared/ui";

const CheckFlow = ({
  source,
  onClose,
}: {
  source: CatalogSource;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const { t: tc } = useTranslation("packCatalog");
  const check = useCheckSource();
  const apply = useApplySource();
  const started = useRef(false);
  const { mutate: runCheck } = check;

  const recheck = () => {
    apply.reset();
    runCheck(source.id);
  };

  // Проверка стартует, как только окно открыто; ref не даёт строгому режиму запустить её дважды.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    runCheck(source.id);
  }, [runCheck, source.id]);

  const busy = check.isPending || apply.isPending;
  const close = () => {
    if (apply.isPending) return;
    onClose();
  };
  const report = check.data;
  const applied = apply.data;

  return (
    <Modal
      isOpen
      onClose={close}
      title={t("check.title", { name: source.label })}
      width={680}
      footer={
        applied ? (
          <Button onClick={close} data-testid="pc-check-done">
            {t("common.done")}
          </Button>
        ) : (
          <>
            <Button
              variant="secondary"
              onClick={close}
              disabled={apply.isPending}
            >
              {t("common.close")}
            </Button>
            {!check.isPending && (
              <Button
                variant="secondary"
                onClick={recheck}
                disabled={busy}
                data-testid="pc-check-again"
              >
                <RefreshCw size="0.75rem" />
                {tc("flow.again")}
              </Button>
            )}
            <Button
              disabled={!report?.ok || busy}
              onClick={() => {
                if (!report) return;
                apply.mutate({ id: source.id, revision: report.revision });
              }}
              data-testid="pc-apply"
            >
              {apply.isPending && <Spinner size="sm" />}
              {apply.isPending ? tc("flow.applying") : tc("flow.apply")}
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col" style={{ gap: "0.75rem" }}>
        {applied ? (
          <CatalogApplyResult result={applied} />
        ) : (
          <>
            {check.isPending && <CatalogCheckPending />}
            {check.isError && (
              <CatalogFlowError
                error={check.error}
                onRecheck={recheck}
                rechecking={busy}
              />
            )}
            {apply.isError && (
              <CatalogFlowError
                error={apply.error}
                onRecheck={recheck}
                rechecking={busy}
              />
            )}
            {report && <CatalogCheckReport check={report} />}
          </>
        )}
      </div>
    </Modal>
  );
};

/** «Проверить» и «Применить» источника: отчёт проверки, затем итог применения. */
export const CheckDialog = ({
  source,
  onClose,
}: {
  source: CatalogSource | null;
  onClose: () => void;
}) =>
  source ? (
    <CheckFlow key={source.id} source={source} onClose={onClose} />
  ) : null;

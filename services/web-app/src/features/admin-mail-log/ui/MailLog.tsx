import { useCallback, useState } from "react";
import { useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { toast, useListQueryState } from "@shared/lib";
import {
  MAIL_LOG_LIST,
  useMailLog,
  useMailLogSummary,
} from "../api/mailLogQueries";
import type { MailLogEntry } from "../api/schemas";
import { parseMailId } from "../lib/mailLog";
import { useMinuteNow } from "../lib/when";
import { MailLogCard } from "./MailLogCard";
import { MailLogView } from "./MailLogView";
import { ResendBatchDialog } from "./ResendBatchDialog";

/** Параметр адреса с открытым письмом: ссылку на карточку можно переслать другому админу. */
export const MAIL_PARAM = "mail";

/**
 * Раздел «Письма» (/admin/mail): журнал по курсору сервера с фильтрами в адресе, сводка за
 * сутки (опрос раз в минуту) и карточка письма по `?mail=<id>`.
 */
export const MailLog = () => {
  const { t } = useTranslation("adminMail");
  const state = useListQueryState(MAIL_LOG_LIST);
  const log = useMailLog(state);
  const summary = useMailLogSummary();
  const [params, setParams] = useSearchParams();
  const openId = parseMailId(params.get(MAIL_PARAM));
  const [refreshing, setRefreshing] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const now = useMinuteNow();

  const setOpenId = useCallback(
    (id: number | null) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (id === null) next.delete(MAIL_PARAM);
          else next.set(MAIL_PARAM, String(id));
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const refresh = () => {
    setRefreshing(true);
    Promise.all([log.refresh(), summary.refetch()])
      .catch(() => {
        toast.error(t("loadFailed"));
      })
      .finally(() => {
        setRefreshing(false);
      });
  };

  const rows = log.items;
  const row: MailLogEntry | null =
    openId === null ? null : (rows.find((r) => r.id === openId) ?? null);

  return (
    <>
      <MailLogView
        state={state}
        rows={rows}
        loading={log.isFetching && !log.isLoadingMore}
        failed={log.isError && rows.length === 0}
        failedMore={log.query.isFetchNextPageError}
        pagination={log.pagination}
        summary={summary.data ?? null}
        now={now}
        selectedId={openId}
        refreshing={refreshing}
        onOpen={(entry) => {
          setOpenId(entry.id);
        }}
        onRefresh={refresh}
        onRetry={() => {
          void log.refetch();
        }}
        onRetryMore={log.loadMore}
        onResendBatch={() => {
          setBatchOpen(true);
        }}
      />
      <MailLogCard
        id={openId}
        row={row}
        onClose={() => {
          setOpenId(null);
        }}
        onOpen={setOpenId}
      />
      <ResendBatchDialog
        open={batchOpen}
        onClose={() => {
          setBatchOpen(false);
        }}
        params={state.params}
        filtered={state.isFiltered}
      />
    </>
  );
};

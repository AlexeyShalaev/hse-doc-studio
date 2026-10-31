import type { SyncStatusView } from "@entities/git-sync";

/** Итог последней выгрузки PDF на сервер Студии в виде, удобном панели. */
export type PdfUploadStatus = {
  last: {
    docId: string;
    at: string;
    ok: boolean;
    error: string | null;
    message: string | null;
  } | null;
};

/** null: проект не с сервера Студии или выгрузка выключена, панель про PDF молчит. */
export const pdfUploadStatus = (
  status: SyncStatusView | undefined,
): PdfUploadStatus | null => {
  const upload = status?.pdf_upload;
  if (!upload?.available || !upload.enabled) return null;
  const last = upload.last;
  return {
    last: last
      ? {
          docId: last.doc_id,
          at: last.at,
          ok: last.ok,
          error: last.error ?? null,
          message: last.message ?? null,
        }
      : null,
  };
};

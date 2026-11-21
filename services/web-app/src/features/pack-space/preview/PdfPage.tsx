import { useState } from "react";
import { Maximize2, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PackPreviewBuild } from "@entities/pack-studio";
import { Button, Modal, PdfViewer } from "@shared/ui";

/**
 * Готовая страница: PDF, число страниц, «Журнал сборки» и «Во весь экран». Смотрит тот самый PDF,
 * который собрал сервер; адрес берётся из `useDocumentPreview` (в галерее подменяется).
 */
// data: и blob: адрес не принимает запрос (?v=), а его содержимое и так не меняется.
const keyFor = (url: string, build: PackPreviewBuild): string | undefined =>
  /^(data|blob):/.test(url) ? undefined : build.id;

export const PdfPage = ({
  build,
  url,
  onLog,
}: {
  build: PackPreviewBuild;
  url: string;
  onLog: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const [full, setFull] = useState(false);
  const key = keyFor(url, build);
  const refresh = key === undefined ? {} : { refreshKey: key };
  return (
    <div className="sp-pv-page" data-testid="sp-pv-page">
      <div className="sp-pv-meta">
        <span>
          {build.pages !== null
            ? t("preview.pages", { count: build.pages })
            : ""}
        </span>
        <span className="sp-pv-row">
          <Button
            size="xs"
            variant="ghost"
            onClick={onLog}
            data-testid="sp-pv-log"
          >
            <ScrollText size="0.6875rem" aria-hidden="true" />
            {t("preview.log")}
          </Button>
          <Button
            size="xs"
            variant="ghost"
            onClick={() => {
              setFull(true);
            }}
            title={t("preview.full")}
            aria-label={t("preview.full")}
            data-testid="sp-pv-full"
          >
            <Maximize2 size="0.6875rem" aria-hidden="true" />
            {t("preview.full")}
          </Button>
        </span>
      </div>
      <div className="sp-pv-viewer">
        <PdfViewer
          url={url}
          {...refresh}
          ariaLabel={build.document}
          initialFit
        />
      </div>
      <Modal
        isOpen={full}
        onClose={() => {
          setFull(false);
        }}
        title={t("preview.title")}
        width={980}
      >
        <div className="sp-pv-viewer-full" data-testid="sp-pv-full-view">
          <PdfViewer url={url} {...refresh} ariaLabel={build.document} />
        </div>
      </Modal>
    </div>
  );
};

import { useState } from "react";
import { GitCompare, HardDriveDownload, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { diffHunks, diffLines, type DiffLine } from "@shared/lib";
import { Button, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type StaleFileBannerProps = {
  /** Текст файла сейчас (с сервера в ответе 409); null: файл удалён. */
  diskContent: string | null;
  /** Несохранённый буфер: геттер, буфер живёт в редакторе. */
  getBuffer: () => string;
  onTakeDisk: () => void;
  onKeepMine: () => void;
  busy: boolean;
};

const SIGN = { add: "+", del: "−", context: " " } as const;

/**
 * Файл поменяли с тех пор, как его открыли (запись с If-Match получила
 * stale_file). Ничего не теряется: «Взять их версию» заменяет буфер текстом
 * с диска, «Оставить мою» пишет буфер поверх их версии, «Сравнить» показывает разницу.
 */
export const StaleFileBanner = ({
  diskContent,
  getBuffer,
  onTakeDisk,
  onKeepMine,
  busy,
}: StaleFileBannerProps) => {
  const { t } = useTranslation("packStudio");
  const [hunks, setHunks] = useState<DiffLine[][] | null>(null);
  return (
    <div data-testid="stale-banner">
      <Notice
        tone="warn"
        role="alert"
        text={diskContent === null ? t("stale.deleted") : t("stale.title")}
        action={
          <span className="flex" style={{ gap: "0.375rem", flexWrap: "wrap" }}>
            {diskContent !== null && (
              <Button
                size="xs"
                variant="secondary"
                onClick={onTakeDisk}
                disabled={busy}
              >
                <HardDriveDownload size="0.6875rem" />
                {t("stale.takeDisk")}
              </Button>
            )}
            <Button
              size="xs"
              variant="secondary"
              onClick={onKeepMine}
              disabled={busy}
              data-testid="stale-keep-mine"
            >
              <Save size="0.6875rem" />
              {t("stale.keepMine")}
            </Button>
            {diskContent !== null && (
              <Button
                size="xs"
                variant="ghost"
                onClick={() => {
                  setHunks(diffHunks(diffLines(diskContent, getBuffer())));
                }}
              >
                <GitCompare size="0.6875rem" />
                {t("stale.compare")}
              </Button>
            )}
          </span>
        }
      />
      <Modal
        isOpen={hunks !== null}
        onClose={() => {
          setHunks(null);
        }}
        title={t("stale.diffTitle")}
        description={t("stale.diffLegend")}
        width={860}
      >
        <div className="ps-diff">
          {(hunks ?? []).length === 0 ? (
            <p className="ps-pane-empty">{t("stale.diffEmpty")}</p>
          ) : (
            (hunks ?? []).map((hunk, hunkIndex) => (
              <div key={hunkIndex} className="ps-diff-hunk">
                {hunk.map((line, lineIndex) => (
                  <div
                    key={lineIndex}
                    className="ps-diff-line mono"
                    data-kind={line.kind}
                  >
                    <span className="dim">{line.leftNo ?? ""}</span>
                    <span className="dim">{line.rightNo ?? ""}</span>
                    <span>{SIGN[line.kind]}</span>
                    <span className="ps-diff-text">{line.text}</span>
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </Modal>
    </div>
  );
};

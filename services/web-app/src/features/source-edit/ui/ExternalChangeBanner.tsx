import { useState } from "react";
import {
  AlertTriangle,
  GitCompare,
  HardDriveDownload,
  Save,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Modal } from "@shared/ui/Modal";
import {
  diffHunks,
  diffLines,
  type DiffLine,
  type DiffLineKind,
} from "@shared/lib";

export type ExternalChangeBannerProps = {
  /** Содержимое, лежащее на диске сейчас (правка снаружи). */
  diskContent: string;
  /** Несохранённый буфер редактора. Геттер, а не строка: буфер живёт в ref
   *  редактора, и читать его на рендере нельзя — берём в момент открытия. */
  getBufferContent: () => string;
  onTakeDisk: () => void;
  onKeepMine: () => void;
  busy?: boolean;
};

const KIND_STYLE: Record<DiffLineKind, { bg: string; sign: string }> = {
  add: { bg: "var(--c-ok-soft, rgba(46,160,67,0.12))", sign: "+" },
  del: { bg: "var(--c-err-soft, rgba(248,81,73,0.12))", sign: "−" },
  context: { bg: "transparent", sign: " " },
};

/**
 * Файл правили и здесь, и снаружи — потерять нельзя ни ту, ни другую сторону.
 *
 * Автосохранение на это время остановлено (см. SourceEditor), поэтому баннер —
 * единственный выход из состояния: пока пользователь не выбрал, на диск ничего
 * не пишется. «Сравнить» показывает, что именно разошлось: без этого выбор
 * «взять с диска / оставить своё» — гадание.
 */
export const ExternalChangeBanner = ({
  diskContent,
  getBufferContent,
  onTakeDisk,
  onKeepMine,
  busy = false,
}: ExternalChangeBannerProps) => {
  const { t } = useTranslation("sourceEdit");
  // Дифф считается один раз при открытии окна: буфер живёт в ref редактора,
  // и читать его во время рендера нельзя.
  const [hunks, setHunks] = useState<DiffLine[][] | null>(null);

  return (
    <>
      <div
        className="flex items-center"
        style={{
          gap: "0.625rem",
          padding: "0.5rem 0.75rem",
          borderBottom: "1px solid var(--c-warn)",
          background: "var(--c-warn-soft, rgba(210,153,34,0.12))",
          fontSize: "0.75rem",
        }}
      >
        <AlertTriangle
          size="0.875rem"
          style={{ color: "var(--c-warn)", flexShrink: 0 }}
        />
        <span style={{ flex: 1, minWidth: 0 }}>
          {t("externalChange.title")}
        </span>
        <button
          type="button"
          className="btn xs"
          onClick={onTakeDisk}
          disabled={busy}
        >
          <HardDriveDownload size="0.6875rem" />
          {t("externalChange.takeDisk")}
        </button>
        <button
          type="button"
          className="btn xs"
          onClick={onKeepMine}
          disabled={busy}
        >
          <Save size="0.6875rem" />
          {t("externalChange.keepMine")}
        </button>
        <button
          type="button"
          className="btn xs ghost"
          onClick={() => {
            setHunks(diffHunks(diffLines(diskContent, getBufferContent())));
          }}
        >
          <GitCompare size="0.6875rem" />
          {t("externalChange.compare")}
        </button>
      </div>

      <Modal
        isOpen={hunks !== null}
        onClose={() => {
          setHunks(null);
        }}
        title={t("externalChange.diffTitle")}
        width={860}
      >
        <div
          style={{
            fontSize: "0.71875rem",
            color: "var(--fg-2)",
            marginBottom: "0.625rem",
          }}
        >
          {t("externalChange.diffLegend")}
        </div>
        <div
          style={{
            maxHeight: "60vh",
            overflow: "auto",
            border: "1px solid var(--border)",
            borderRadius: "0.375rem",
          }}
        >
          {(hunks ?? []).length === 0 ? (
            <div
              style={{
                padding: "0.75rem",
                fontSize: "0.75rem",
                color: "var(--fg-2)",
              }}
            >
              {t("externalChange.diffEmpty")}
            </div>
          ) : (
            (hunks ?? []).map((hunk, hunkIndex) => (
              <div
                key={hunkIndex}
                style={{
                  borderTop:
                    hunkIndex > 0 ? "1px solid var(--border)" : undefined,
                }}
              >
                {hunk.map((line, lineIndex) => {
                  const style = KIND_STYLE[line.kind];
                  return (
                    <div
                      key={lineIndex}
                      className="mono"
                      style={{
                        display: "flex",
                        gap: "0.5rem",
                        padding: "1px 0.5rem",
                        fontSize: "0.6875rem",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        background: style.bg,
                      }}
                    >
                      <span
                        className="dim"
                        style={{
                          width: "2.125rem",
                          textAlign: "right",
                          flexShrink: 0,
                        }}
                      >
                        {line.leftNo ?? ""}
                      </span>
                      <span
                        className="dim"
                        style={{
                          width: "2.125rem",
                          textAlign: "right",
                          flexShrink: 0,
                        }}
                      >
                        {line.rightNo ?? ""}
                      </span>
                      <span style={{ flexShrink: 0 }}>{style.sign}</span>
                      <span style={{ minWidth: 0 }}>{line.text}</span>
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </Modal>
    </>
  );
};

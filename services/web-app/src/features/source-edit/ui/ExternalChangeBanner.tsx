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
          gap: 10,
          padding: "8px 12px",
          borderBottom: "1px solid var(--c-warn)",
          background: "var(--c-warn-soft, rgba(210,153,34,0.12))",
          fontSize: 12,
        }}
      >
        <AlertTriangle
          size={14}
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
          <HardDriveDownload size={11} />
          {t("externalChange.takeDisk")}
        </button>
        <button
          type="button"
          className="btn xs"
          onClick={onKeepMine}
          disabled={busy}
        >
          <Save size={11} />
          {t("externalChange.keepMine")}
        </button>
        <button
          type="button"
          className="btn xs ghost"
          onClick={() => {
            setHunks(diffHunks(diffLines(diskContent, getBufferContent())));
          }}
        >
          <GitCompare size={11} />
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
        <div style={{ fontSize: 11.5, color: "var(--fg-2)", marginBottom: 10 }}>
          {t("externalChange.diffLegend")}
        </div>
        <div
          style={{
            maxHeight: "60vh",
            overflow: "auto",
            border: "1px solid var(--border)",
            borderRadius: 6,
          }}
        >
          {(hunks ?? []).length === 0 ? (
            <div style={{ padding: 12, fontSize: 12, color: "var(--fg-2)" }}>
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
                        gap: 8,
                        padding: "1px 8px",
                        fontSize: 11,
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        background: style.bg,
                      }}
                    >
                      <span
                        className="dim"
                        style={{ width: 34, textAlign: "right", flexShrink: 0 }}
                      >
                        {line.leftNo ?? ""}
                      </span>
                      <span
                        className="dim"
                        style={{ width: 34, textAlign: "right", flexShrink: 0 }}
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

import {
  useImperativeHandle,
  useRef,
  useState,
  type DragEvent,
  type Ref,
} from "react";
import { UploadCloud } from "lucide-react";

// Область «перетащи файл или выбери»: пунктирная рамка с кнопкой и скрытый
// input. Сам файл не читает, а отдаёт вызывающему. Если нужно выбрать другой
// файл, пока рамка спрятана (`showZone={false}`), окно выбора открывает `open()`.

export type FileDropZoneHandle = { open: () => void };

export type FileDropZoneProps = {
  /** Атрибут accept скрытого input, например ".bundle,.hseenc". */
  accept: string;
  /** Подходит ли файл; без проверки подходит любой. */
  isAcceptable?: (file: File) => boolean;
  onFile: (file: File) => void;
  /** Файл выбран, но не подошёл (чужое расширение). */
  onReject?: (file: File) => void;
  /** Неактивная рамка: «Перетащи файл сюда или». */
  title: string;
  /** Подчёркнутая часть-приглашение: «выбери на компьютере». */
  action: string;
  /** Текст, пока файл над рамкой. */
  activeTitle: string;
  hint?: string;
  /** Имя скрытого input для скринридера. */
  inputLabel: string;
  /** Нельзя выбирать (идёт загрузка). */
  disabled?: boolean;
  /** Показывать рамку; без неё остаётся только input и `open()`. */
  showZone?: boolean;
  ref?: Ref<FileDropZoneHandle>;
  testId?: string;
  inputTestId?: string;
};

export const FileDropZone = ({
  accept,
  isAcceptable,
  onFile,
  onReject,
  title,
  action,
  activeTitle,
  hint,
  inputLabel,
  disabled = false,
  showZone = true,
  ref,
  testId,
  inputTestId,
}: FileDropZoneProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const open = (): void => {
    if (!disabled) inputRef.current?.click();
  };
  useImperativeHandle(ref, () => ({ open }));

  const pick = (picked: File | null | undefined): void => {
    if (!picked || disabled) return;
    if (isAcceptable && !isAcceptable(picked)) {
      onReject?.(picked);
      return;
    }
    onFile(picked);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragging(false);
    pick(event.dataTransfer.files[0]);
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        disabled={disabled}
        data-testid={inputTestId}
        aria-label={inputLabel}
        onChange={(event) => {
          pick(event.target.files?.[0]);
          // Тот же файл можно выбрать повторно.
          event.target.value = "";
        }}
      />
      {showZone && (
        <div
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-disabled={disabled}
          aria-label={`${title} ${action}`}
          data-testid={testId}
          onClick={open}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              open();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => {
            setDragging(false);
          }}
          onDrop={onDrop}
          className="flex flex-col items-center justify-center"
          style={{
            gap: 6,
            padding: "28px 16px",
            borderRadius: "var(--r-3)",
            border: `1.5px dashed ${dragging ? "var(--accent)" : "var(--border-strong)"}`,
            background: dragging ? "var(--accent-soft)" : "var(--bg-1)",
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.6 : 1,
            textAlign: "center",
            transition: "background 120ms, border-color 120ms",
          }}
        >
          <UploadCloud
            size={24}
            aria-hidden="true"
            style={{ color: dragging ? "var(--accent)" : "var(--fg-3)" }}
          />
          <span style={{ fontSize: 13, color: "var(--fg-0)" }}>
            {dragging ? (
              activeTitle
            ) : (
              <>
                {title}{" "}
                <span style={{ color: "var(--accent)", fontWeight: 500 }}>
                  {action}
                </span>
              </>
            )}
          </span>
          {hint && (
            <span className="dim" style={{ fontSize: 11.5 }}>
              {hint}
            </span>
          )}
        </div>
      )}
    </>
  );
};

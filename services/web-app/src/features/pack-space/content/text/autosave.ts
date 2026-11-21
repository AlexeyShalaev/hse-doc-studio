import { PackStaleFileError } from "@entities/pack-studio";

// Движок автосохранения одного файла (pack-studio-ux.md, 5.5): правка пишется сама через
// `delayMs` без ввода, запись с `If-Match`, конфликт не теряет текст. Это обычный класс без React:
// он переживает размонтирование (смена документа не обрывает запись) и проверяется таблицей тестов.

export const AUTOSAVE_DELAY_MS = 1500;

/** `clean`: ничего не меняли; `waiting`: правка ждёт записи; `saving`; `saved`: записано; `failed`: сбой. */
export type AutosaveStatus =
  "clean" | "waiting" | "saving" | "saved" | "failed";

export type AutosaveConflict = {
  /** Текст на диске сейчас; `null`: файл удалён. */
  diskContent: string | null;
  diskEtag: string | null;
};

export type AutosaveSnapshot = {
  /** Текст в редакторе. */
  text: string;
  /** Отличается от записанного. */
  dirty: boolean;
  status: AutosaveStatus;
  conflict: AutosaveConflict | null;
  error: unknown;
};

export type AutosaveOptions = {
  initial: { content: string; etag: string | null };
  write: (text: string, ifMatch: string | null) => Promise<{ etag: string }>;
  /** После каждой удачной записи (кэш запросов, git, проверки). Вызывается и после размонтирования. */
  onWritten?: (text: string, etag: string) => void;
  delayMs?: number;
};

export class FileAutosaver {
  private text: string;
  private saved: { content: string; etag: string | null };
  private timer: ReturnType<typeof setTimeout> | null = null;
  private busy = false;
  private closed = false;
  private wrote = false;
  private status: AutosaveStatus = "clean";
  private conflict: AutosaveConflict | null = null;
  private error: unknown = null;
  private snapshot: AutosaveSnapshot;
  private readonly listeners = new Set<() => void>();

  constructor(private readonly options: AutosaveOptions) {
    this.text = options.initial.content;
    this.saved = { ...options.initial };
    this.snapshot = this.build();
  }

  readonly getSnapshot = (): AutosaveSnapshot => this.snapshot;

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /** Новый текст из редактора. */
  edit(next: string): void {
    this.text = next;
    this.error = null;
    this.reschedule();
  }

  /** Записать сейчас (Ctrl+S, уход с экрана, «Повторить»). */
  async flush(): Promise<void> {
    this.clearTimer();
    if (this.busy || this.conflict || this.text === this.saved.content) return;
    this.busy = true;
    this.status = "saving";
    this.error = null;
    this.emit();
    const text = this.text;
    try {
      const version = await this.options.write(text, this.saved.etag);
      this.saved = { content: text, etag: version.etag };
      this.wrote = true;
      this.options.onWritten?.(text, version.etag);
    } catch (error) {
      this.busy = false;
      if (error instanceof PackStaleFileError) {
        this.conflict = {
          diskContent: error.diskContent,
          diskEtag: error.diskEtag,
        };
        this.status = "waiting";
      } else {
        this.error = error;
        this.status = "failed";
      }
      this.emit();
      return;
    }
    this.busy = false;
    // Пока писали, человек печатал дальше: хвост уходит следующей записью.
    if (this.text !== this.saved.content) {
      if (this.closed) await this.flush();
      else this.reschedule();
      return;
    }
    this.status = "saved";
    this.emit();
  }

  /** Конфликт: взять текст с диска, правка отбрасывается. Возвращает новый текст редактора. */
  takeDisk(): string {
    const disk = this.conflict?.diskContent ?? "";
    this.text = disk;
    this.saved = { content: disk, etag: this.conflict?.diskEtag ?? null };
    this.conflict = null;
    this.clearTimer();
    this.status = this.wrote ? "saved" : "clean";
    this.emit();
    return disk;
  }

  /** Конфликт: оставить свой текст и записать поверх чужого. */
  keepMine(): void {
    if (!this.conflict) return;
    this.saved = { ...this.saved, etag: this.conflict.diskEtag };
    this.conflict = null;
    void this.flush();
  }

  /** Экран закрывается: записать хвост и больше не ждать. */
  close(): void {
    this.closed = true;
    void this.flush();
  }

  /** Экран снова открыт (повторный монтаж в StrictMode). */
  open(): void {
    this.closed = false;
  }

  private reschedule(): void {
    this.clearTimer();
    if (this.busy || this.conflict) {
      this.emit();
      return;
    }
    if (this.text === this.saved.content) {
      this.status = this.wrote ? "saved" : "clean";
      this.emit();
      return;
    }
    this.status = "waiting";
    this.timer = setTimeout(() => {
      void this.flush();
    }, this.options.delayMs ?? AUTOSAVE_DELAY_MS);
    this.emit();
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }

  private build(): AutosaveSnapshot {
    return {
      text: this.text,
      dirty: this.text !== this.saved.content,
      status: this.status,
      conflict: this.conflict,
      error: this.error,
    };
  }

  private emit(): void {
    this.snapshot = this.build();
    for (const listener of this.listeners) listener();
  }
}

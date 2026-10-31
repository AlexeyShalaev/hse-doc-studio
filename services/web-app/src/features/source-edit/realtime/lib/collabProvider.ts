import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import * as awarenessProtocol from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";

// Клиент протокола y-websocket для комнаты совместной правки (infra/collab/protocol.py).
// Свой, а не y-websocket: нужны коды закрытия сервера (отказ не повторяется), кадр «сбросить на диск»
// с подтверждением, события сервера и эпоха комнаты.

const MSG_SYNC = 0;
const MSG_AWARENESS = 1;
const MSG_FLUSH = 9;
const MSG_FLUSH_ACK = 10;
const MSG_EVENT = 11;

export type CollabStatus = "connecting" | "connected" | "offline" | "refused";

/** Почему сервер отказал: повторять подключение бессмысленно, пользователю нужно объяснение. */
export type CollabRefusal =
  "auth" | "forbidden" | "not_found" | "unsupported" | "busy" | "too_large";

const REFUSALS: Readonly<Record<number, CollabRefusal>> = {
  4401: "auth",
  4403: "forbidden",
  4404: "not_found",
  4415: "unsupported",
  4429: "busy",
  1009: "too_large",
  1008: "forbidden",
};

export type CollabPeer = {
  clientId: number;
  name: string;
  color: string;
  writable: boolean;
};

export type CollabSnapshot = {
  status: CollabStatus;
  /** Первый обмен состоянием после подключения завершён: можно показывать текст. */
  synced: boolean;
  /** Хотя бы один обмен состоянием уже был: текст можно показывать и при обрыве связи. */
  everSynced: boolean;
  canWrite: boolean;
  refusal: CollabRefusal | null;
  peers: CollabPeer[];
  /** Сервер сообщил об ошибке записи или размере (`save_failed`, `too_large`, `file_gone`). */
  problem: string | null;
};

export type CollabServerEvent =
  | {
      type: "hello";
      epoch: string;
      can_write: boolean;
      color: string;
      name: string;
    }
  /** Эпоха комнаты сменилась: родословная документа на сервере пересобрана, локальная копия не годится. */
  | { type: "reset" }
  | { type: "read_only" }
  | { type: "role"; can_write: boolean }
  | { type: "external"; conflicts: number }
  | { type: "review" }
  | { type: "error"; code: string };

export type SocketLike = {
  binaryType: string;
  readyState: number;
  send: (data: Uint8Array) => void;
  close: (code?: number, reason?: string) => void;
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  onerror: (() => void) | null;
};

export type CollabOptions = {
  url: () => string;
  createSocket?: (url: string) => SocketLike;
  /** Имя на случай, пока сервер не прислал проверенное. */
  localName?: string;
  baseDelayMs?: number;
  maxDelayMs?: number;
  flushTimeoutMs?: number;
};

const OPEN = 1;
const DEFAULT_BASE_MS = 500;
const DEFAULT_MAX_MS = 15_000;
const DEFAULT_FLUSH_MS = 8_000;

const frame = (build: (encoder: encoding.Encoder) => void): Uint8Array => {
  const encoder = encoding.createEncoder();
  build(encoder);
  return encoding.toUint8Array(encoder);
};

export class CollabProvider {
  readonly doc = new Y.Doc();
  readonly text = this.doc.getText("text");
  readonly awareness = new awarenessProtocol.Awareness(this.doc);

  private socket: SocketLike | null = null;
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;
  private state: CollabSnapshot = {
    status: "connecting",
    synced: false,
    everSynced: false,
    canWrite: true,
    refusal: null,
    peers: [],
    problem: null,
  };
  private epoch: string | null = null;
  private readonly listeners = new Set<() => void>();
  private readonly eventListeners = new Set<
    (event: CollabServerEvent) => void
  >();
  private pendingFlush: ((ok: boolean) => void) | null = null;
  private readonly opts: Required<
    Omit<CollabOptions, "createSocket" | "localName">
  > &
    Pick<CollabOptions, "createSocket" | "localName">;

  constructor(options: CollabOptions) {
    this.opts = {
      baseDelayMs: DEFAULT_BASE_MS,
      maxDelayMs: DEFAULT_MAX_MS,
      flushTimeoutMs: DEFAULT_FLUSH_MS,
      ...options,
    };
    this.doc.on("update", this.onDocUpdate);
    this.awareness.on("update", this.onAwarenessUpdate);
    this.awareness.on("change", this.refreshPeers);
    if (typeof window !== "undefined") {
      window.addEventListener("online", this.onOnline);
    }
    this.connect();
  }

  // ── подписки ────────────────────────────────────────────────────────────

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  readonly getSnapshot = (): CollabSnapshot => this.state;

  onEvent(listener: (event: CollabServerEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => {
      this.eventListeners.delete(listener);
    };
  }

  private patch(next: Partial<CollabSnapshot>): void {
    this.state = { ...this.state, ...next };
    this.listeners.forEach((listener) => {
      listener();
    });
  }

  // ── соединение ──────────────────────────────────────────────────────────

  private connect(): void {
    if (this.destroyed) return;
    this.timer = null;
    this.patch({
      status: this.state.status === "offline" ? "offline" : "connecting",
    });
    const create =
      this.opts.createSocket ??
      ((url: string): SocketLike =>
        new WebSocket(url) as unknown as SocketLike);
    let socket: SocketLike;
    try {
      socket = create(this.opts.url());
    } catch {
      this.scheduleReconnect();
      return;
    }
    socket.binaryType = "arraybuffer";
    this.socket = socket;
    socket.onopen = () => {
      this.send(
        frame((e) => {
          encoding.writeVarUint(e, MSG_SYNC);
          syncProtocol.writeSyncStep1(e, this.doc);
        }),
      );
      const local = this.awareness.getLocalState();
      if (local !== null) this.broadcastAwareness([this.doc.clientID]);
    };
    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer)
        this.onFrame(new Uint8Array(event.data));
    };
    socket.onerror = () => undefined;
    socket.onclose = (event) => {
      if (this.socket !== socket) return;
      this.onClosed(event.code);
    };
  }

  private onClosed(code: number): void {
    this.socket = null;
    this.settleFlush(false);
    const others = [...this.awareness.getStates().keys()].filter(
      (id) => id !== this.doc.clientID,
    );
    awarenessProtocol.removeAwarenessStates(this.awareness, others, this);
    const refusal = REFUSALS[code];
    if (refusal) {
      this.patch({ status: "refused", refusal, synced: false });
      return;
    }
    this.patch({ status: "offline", synced: false });
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.destroyed || this.timer !== null) return;
    const delay = Math.min(
      this.opts.maxDelayMs,
      this.opts.baseDelayMs * 2 ** this.attempt,
    );
    this.attempt += 1;
    this.timer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  private readonly onOnline = (): void => {
    if (this.state.status !== "offline" || this.destroyed) return;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.connect();
  };

  private send(data: Uint8Array): void {
    if (this.socket?.readyState === OPEN) this.socket.send(data);
  }

  // ── входящие кадры ──────────────────────────────────────────────────────

  private onFrame(data: Uint8Array): void {
    const decoder = decoding.createDecoder(data);
    const kind = decoding.readVarUint(decoder);
    if (kind === MSG_SYNC) this.onSync(decoder);
    else if (kind === MSG_AWARENESS) {
      awarenessProtocol.applyAwarenessUpdate(
        this.awareness,
        decoding.readVarUint8Array(decoder),
        this,
      );
    } else if (kind === MSG_FLUSH_ACK) {
      const ack = JSON.parse(new TextDecoder().decode(data.subarray(1))) as {
        ok: boolean;
      };
      this.settleFlush(ack.ok);
    } else if (kind === MSG_EVENT) {
      this.onServerEvent(
        JSON.parse(
          new TextDecoder().decode(data.subarray(1)),
        ) as CollabServerEvent,
      );
    }
  }

  private onSync(decoder: decoding.Decoder): void {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MSG_SYNC);
    const type = syncProtocol.readSyncMessage(decoder, encoder, this.doc, this);
    if (encoding.length(encoder) > 1) this.send(encoding.toUint8Array(encoder));
    if (type === syncProtocol.messageYjsSyncStep2 && !this.state.synced) {
      this.attempt = 0;
      this.patch({
        status: "connected",
        synced: true,
        everSynced: true,
        refusal: null,
      });
    }
  }

  private onServerEvent(event: CollabServerEvent): void {
    if (event.type === "hello") {
      const reset = this.epoch !== null && this.epoch !== event.epoch;
      this.epoch = event.epoch;
      this.patch({ canWrite: event.can_write });
      this.awareness.setLocalStateField("user", {
        name: event.name,
        color: event.color,
        colorLight: `${event.color}33`,
      });
      if (reset) this.emit({ type: "reset" });
    } else if (event.type === "role") {
      this.patch({ canWrite: event.can_write });
    } else if (event.type === "error") {
      this.patch({ problem: event.code });
    }
    this.emit(event);
  }

  private emit(event: CollabServerEvent): void {
    this.eventListeners.forEach((listener) => {
      listener(event);
    });
  }

  // ── исходящие ───────────────────────────────────────────────────────────

  private readonly onDocUpdate = (
    update: Uint8Array,
    origin: unknown,
  ): void => {
    if (origin === this || !this.state.canWrite) return;
    this.send(
      frame((e) => {
        encoding.writeVarUint(e, MSG_SYNC);
        syncProtocol.writeUpdate(e, update);
      }),
    );
  };

  private readonly onAwarenessUpdate = (
    changes: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown,
  ): void => {
    if (origin === this) return;
    this.broadcastAwareness([
      ...changes.added,
      ...changes.updated,
      ...changes.removed,
    ]);
  };

  private broadcastAwareness(ids: number[]): void {
    this.send(
      frame((e) => {
        encoding.writeVarUint(e, MSG_AWARENESS);
        encoding.writeVarUint8Array(
          e,
          awarenessProtocol.encodeAwarenessUpdate(this.awareness, ids),
        );
      }),
    );
  }

  private readonly refreshPeers = (): void => {
    const peers: CollabPeer[] = [];
    this.awareness.getStates().forEach((state, clientId) => {
      if (clientId === this.doc.clientID) return;
      const user = state.user as { name?: string; color?: string } | undefined;
      if (!user?.name) return;
      peers.push({
        clientId,
        name: user.name,
        color: user.color ?? "#868e96",
        writable: state.writable !== false,
      });
    });
    peers.sort((a, b) => a.clientId - b.clientId);
    this.patch({ peers });
  };

  /** Записать набранное на диск и дождаться подтверждения; false: нет связи, ошибка записи или время вышло. */
  flush(): Promise<boolean> {
    if (this.socket?.readyState !== OPEN || !this.state.synced)
      return Promise.resolve(false);
    this.settleFlush(false);
    return new Promise<boolean>((resolve) => {
      const timeout = setTimeout(() => {
        this.settleFlush(false);
      }, this.opts.flushTimeoutMs);
      this.pendingFlush = (ok) => {
        clearTimeout(timeout);
        resolve(ok);
      };
      this.send(Uint8Array.of(MSG_FLUSH));
    });
  }

  private settleFlush(ok: boolean): void {
    const pending = this.pendingFlush;
    this.pendingFlush = null;
    pending?.(ok);
  }

  destroy(): void {
    this.destroyed = true;
    if (this.timer !== null) clearTimeout(this.timer);
    if (typeof window !== "undefined")
      window.removeEventListener("online", this.onOnline);
    this.settleFlush(false);
    awarenessProtocol.removeAwarenessStates(
      this.awareness,
      [this.doc.clientID],
      "destroy",
    );
    const socket = this.socket;
    this.socket = null;
    socket?.close(1000, "bye");
    this.awareness.destroy();
    this.doc.destroy();
    this.listeners.clear();
    this.eventListeners.clear();
  }
}

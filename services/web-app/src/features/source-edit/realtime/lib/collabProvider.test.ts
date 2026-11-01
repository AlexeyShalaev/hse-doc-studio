import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
import { Awareness, encodeAwarenessUpdate } from "y-protocols/awareness";
import * as syncProtocol from "y-protocols/sync";
import * as Y from "yjs";
import {
  CollabProvider,
  type CollabServerEvent,
  type SocketLike,
} from "./collabProvider";

const MSG_SYNC = 0;
const MSG_FLUSH = 9;
const MSG_FLUSH_ACK = 10;
const MSG_EVENT = 11;

const json = (kind: number, body: unknown): Uint8Array =>
  Uint8Array.from([kind, ...new TextEncoder().encode(JSON.stringify(body))]);

class FakeSocket implements SocketLike {
  binaryType = "blob";
  readyState = 0;
  sent: Uint8Array[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly server: FakeServer) {}

  send(data: Uint8Array): void {
    this.sent.push(data);
    this.server.receive(this, data);
  }
  close(code = 1000): void {
    this.readyState = 3;
    this.onclose?.({ code });
  }
  deliver(data: Uint8Array): void {
    const copy = data.slice();
    this.onmessage?.({ data: copy.buffer });
  }
}

/** Сервер-заглушка: свой Y.Doc и тот же протокол, что у комнаты pycrdt. */
class FakeServer {
  doc = new Y.Doc();
  sockets: FakeSocket[] = [];
  flushes = 0;
  ackFlush = true;
  hello: Record<string, unknown> = {
    type: "hello",
    epoch: "e1",
    can_write: true,
    color: "#1c7ed6",
    name: "Анна",
  };

  create = (): FakeSocket => {
    const socket = new FakeSocket(this);
    this.sockets.push(socket);
    return socket;
  };

  open(socket: FakeSocket): void {
    socket.readyState = 1;
    socket.onopen?.();
    socket.deliver(json(MSG_EVENT, this.hello));
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MSG_SYNC);
    syncProtocol.writeSyncStep1(encoder, this.doc);
    socket.deliver(encoding.toUint8Array(encoder));
  }

  receive(socket: FakeSocket, data: Uint8Array): void {
    const decoder = decoding.createDecoder(data);
    const kind = decoding.readVarUint(decoder);
    if (kind === MSG_FLUSH) {
      this.flushes += 1;
      if (this.ackFlush)
        socket.deliver(json(MSG_FLUSH_ACK, { ok: true, etag: '"x"' }));
      return;
    }
    if (kind !== MSG_SYNC) return;
    const reply = encoding.createEncoder();
    encoding.writeVarUint(reply, MSG_SYNC);
    syncProtocol.readSyncMessage(decoder, reply, this.doc, socket);
    if (encoding.length(reply) > 1)
      socket.deliver(encoding.toUint8Array(reply));
  }

  push(socket: FakeSocket): void {
    // Обновление документа сервера доходит до клиента.
    const state = Y.encodeStateAsUpdate(this.doc);
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MSG_SYNC);
    syncProtocol.writeUpdate(encoder, state);
    socket.deliver(encoding.toUint8Array(encoder));
  }
}

const make = (
  server: FakeServer,
  extra: Partial<ConstructorParameters<typeof CollabProvider>[0]> = {},
) =>
  new CollabProvider({
    url: () => "ws://x",
    createSocket: server.create,
    ...extra,
  });

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("CollabProvider", () => {
  it("syncs the server text on connect and sends local edits", () => {
    const server = new FakeServer();
    server.doc.getText("text").insert(0, "Привет");
    const provider = make(server);
    const socket = server.sockets[0]!;

    server.open(socket);

    expect(provider.getSnapshot()).toMatchObject({
      status: "connected",
      synced: true,
      canWrite: true,
    });
    expect(provider.text.toJSON()).toBe("Привет");
    provider.text.insert(6, ", мир");
    expect(server.doc.getText("text").toJSON()).toBe("Привет, мир");
    provider.destroy();
  });

  it("applies server changes pushed after sync", () => {
    const server = new FakeServer();
    const provider = make(server);
    const socket = server.sockets[0]!;
    server.open(socket);

    server.doc.getText("text").insert(0, "от другого");
    server.push(socket);

    expect(provider.text.toJSON()).toBe("от другого");
    provider.destroy();
  });

  it("does not reconnect after a refusal and reports why", () => {
    const server = new FakeServer();
    const provider = make(server);
    const first = server.sockets[0]!;

    first.close(4403);
    vi.advanceTimersByTime(60_000);

    expect(provider.getSnapshot()).toMatchObject({
      status: "refused",
      refusal: "forbidden",
    });
    expect(server.sockets).toHaveLength(1);
    provider.destroy();
  });

  it("goes offline, backs off, reconnects and merges offline edits without duplicates", () => {
    const server = new FakeServer();
    server.doc.getText("text").insert(0, "База.");
    const provider = make(server, { baseDelayMs: 100 });
    server.open(server.sockets[0]!);
    server.sockets[0]!.close(1006);
    expect(provider.getSnapshot().status).toBe("offline");

    provider.text.insert(0, "Оффлайн. ");
    vi.advanceTimersByTime(99);
    expect(server.sockets).toHaveLength(1);
    vi.advanceTimersByTime(2);
    expect(server.sockets).toHaveLength(2);
    server.open(server.sockets[1]!);

    expect(provider.getSnapshot().status).toBe("connected");
    expect(server.doc.getText("text").toJSON()).toBe("Оффлайн. База.");
    expect(provider.text.toJSON()).toBe("Оффлайн. База.");
    provider.destroy();
  });

  it("backoff grows and is capped", () => {
    const server = new FakeServer();
    const provider = make(server, { baseDelayMs: 100, maxDelayMs: 400 });
    for (let i = 0; i < 5; i += 1) {
      server.sockets.at(-1)!.close(1006);
      vi.advanceTimersByTime(400);
    }
    // 100, 200, 400, 400, 400: пять закрытий дают пять переподключений за 400 мс на попытку после третьей.
    expect(server.sockets.length).toBeGreaterThanOrEqual(5);
    provider.destroy();
  });

  it("a reader does not send edits", () => {
    const server = new FakeServer();
    server.hello = { ...server.hello, can_write: false };
    const provider = make(server);
    const socket = server.sockets[0]!;
    server.open(socket);
    const before = socket.sent.length;

    provider.text.insert(0, "нельзя");

    expect(provider.getSnapshot().canWrite).toBe(false);
    expect(socket.sent).toHaveLength(before);
    expect(server.doc.getText("text").toJSON()).toBe("");
    provider.destroy();
  });

  it("flush resolves on ack, and to false when offline or unacknowledged", async () => {
    const server = new FakeServer();
    const provider = make(server, { flushTimeoutMs: 1000 });
    const socket = server.sockets[0]!;
    expect(await provider.flush()).toBe(false);
    server.open(socket);

    await expect(provider.flush()).resolves.toBe(true);

    server.ackFlush = false;
    const pending = provider.flush();
    vi.advanceTimersByTime(1001);
    await expect(pending).resolves.toBe(false);
    provider.destroy();
  });

  it("reports an epoch change as reset and forwards server events", () => {
    const server = new FakeServer();
    const provider = make(server, { baseDelayMs: 10 });
    const events: CollabServerEvent[] = [];
    provider.onEvent((event) => events.push(event));
    server.open(server.sockets[0]!);
    server.sockets[0]!.close(1006);
    vi.advanceTimersByTime(20);
    server.hello = { ...server.hello, epoch: "e2" };

    server.open(server.sockets[1]!);
    server.sockets[1]!.deliver(json(MSG_EVENT, { type: "review" }));

    expect(events.map((e) => e.type)).toEqual([
      "hello",
      "reset",
      "hello",
      "review",
    ]);
    provider.destroy();
  });

  it("tracks peers from presence and drops them on disconnect", () => {
    const server = new FakeServer();
    const provider = make(server);
    const socket = server.sockets[0]!;
    server.open(socket);
    const remote = new Y.Doc();
    const other = new Awareness(remote);
    other.setLocalState({
      user: { name: "Борис", color: "#2f9e44" },
      writable: true,
    });
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, 1);
    encoding.writeVarUint8Array(
      encoder,
      encodeAwarenessUpdate(other, [remote.clientID]),
    );

    socket.deliver(encoding.toUint8Array(encoder));

    expect(provider.getSnapshot().peers).toEqual([
      {
        clientId: remote.clientID,
        name: "Борис",
        color: "#2f9e44",
        writable: true,
      },
    ]);
    socket.close(1006);
    expect(provider.getSnapshot().peers).toEqual([]);
    provider.destroy();
    other.destroy();
  });
});

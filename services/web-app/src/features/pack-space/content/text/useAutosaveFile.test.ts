import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PackStaleFileError } from "@entities/pack-studio";
import { AUTOSAVE_DELAY_MS, FileAutosaver } from "./autosave";

// Движок автосохранения (его оболочка `useAutosaveFile` только подписывает на него React):
// дебаунс, конфликт, сбой сети, правка во время записи, уход с экрана.

type Write = (
  text: string,
  ifMatch: string | null,
) => Promise<{ etag: string }>;

const make = (write: Write) => {
  const onWritten = vi.fn();
  const saver = new FileAutosaver({
    initial: { content: "a", etag: "e0" },
    write,
    onWritten,
  });
  return { saver, onWritten };
};

const ok = (): Write =>
  vi.fn((text: string) => Promise.resolve({ etag: `e-${text}` }));

describe("FileAutosaver", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("пишет через 1,5 секунды после последней правки, одним запросом", async () => {
    const write = ok();
    const { saver, onWritten } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 1);
    saver.edit("abc");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 1);
    expect(write).not.toHaveBeenCalled();
    expect(saver.getSnapshot().status).toBe("waiting");
    await vi.advanceTimersByTimeAsync(1);
    expect(write).toHaveBeenCalledExactlyOnceWith("abc", "e0");
    expect(onWritten).toHaveBeenCalledWith("abc", "e-abc");
    expect(saver.getSnapshot()).toMatchObject({
      status: "saved",
      dirty: false,
      text: "abc",
    });
  });

  it("возврат к записанному тексту отменяет запись", async () => {
    const write = ok();
    const { saver } = make(write);
    saver.edit("ab");
    saver.edit("a");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 2);
    expect(write).not.toHaveBeenCalled();
    expect(saver.getSnapshot().status).toBe("clean");
  });

  it("следующая запись идёт с новым etag", async () => {
    const write = ok();
    const { saver } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    saver.edit("abc");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(write).toHaveBeenLastCalledWith("abc", "e-ab");
  });

  it("правка во время записи уходит следующей записью, ничего не теряется", async () => {
    let release: () => void = () => undefined;
    const write = vi
      .fn<Write>()
      .mockImplementationOnce(
        (text) =>
          new Promise((resolve) => {
            release = () => {
              resolve({ etag: `e-${text}` });
            };
          }),
      )
      .mockImplementation((text) => Promise.resolve({ etag: `e-${text}` }));
    const { saver } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(saver.getSnapshot().status).toBe("saving");
    saver.edit("abc");
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(write).toHaveBeenCalledTimes(1);
    expect(saver.getSnapshot()).toMatchObject({
      status: "waiting",
      dirty: true,
    });
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(write).toHaveBeenLastCalledWith("abc", "e-ab");
    expect(saver.getSnapshot().status).toBe("saved");
  });

  it("конфликт: текст остаётся в редакторе, запись замирает до выбора", async () => {
    const write = vi
      .fn<Write>()
      .mockRejectedValueOnce(new PackStaleFileError("диск", "e9"))
      .mockImplementation((text) => Promise.resolve({ etag: `e-${text}` }));
    const { saver } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(saver.getSnapshot().conflict).toEqual({
      diskContent: "диск",
      diskEtag: "e9",
    });
    expect(saver.getSnapshot().text).toBe("ab");
    saver.edit("abc");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 2);
    expect(write).toHaveBeenCalledTimes(1);

    saver.keepMine();
    await vi.advanceTimersByTimeAsync(0);
    expect(write).toHaveBeenLastCalledWith("abc", "e9");
    expect(saver.getSnapshot()).toMatchObject({
      conflict: null,
      status: "saved",
    });
  });

  it("конфликт: «Взять их версию» заменяет текст и не пишет", async () => {
    const write = vi
      .fn<Write>()
      .mockRejectedValueOnce(new PackStaleFileError("диск", "e9"));
    const { saver } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(saver.takeDisk()).toBe("диск");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 2);
    expect(write).toHaveBeenCalledTimes(1);
    expect(saver.getSnapshot()).toMatchObject({
      conflict: null,
      dirty: false,
      text: "диск",
    });
    saver.edit("диск!");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(write).toHaveBeenLastCalledWith("диск!", "e9");
  });

  it("сбой сети: правка остаётся, следующая правка и «Повторить» пишут снова", async () => {
    const write = vi
      .fn<Write>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new Error("offline"))
      .mockImplementation((text) => Promise.resolve({ etag: `e-${text}` }));
    const { saver } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(saver.getSnapshot()).toMatchObject({
      status: "failed",
      dirty: true,
    });
    saver.edit("abc");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    expect(saver.getSnapshot().status).toBe("failed");
    await saver.flush();
    expect(write).toHaveBeenCalledTimes(3);
    expect(saver.getSnapshot()).toMatchObject({
      status: "saved",
      dirty: false,
    });
  });

  it("уход с экрана дописывает хвост сразу, не дожидаясь паузы", async () => {
    const write = ok();
    const { saver } = make(write);
    saver.edit("ab");
    saver.close();
    await vi.advanceTimersByTimeAsync(0);
    expect(write).toHaveBeenCalledExactlyOnceWith("ab", "e0");
  });

  it("уход с экрана во время записи дописывает и то, что набрали после", async () => {
    let release: () => void = () => undefined;
    const write = vi
      .fn<Write>()
      .mockImplementationOnce(
        (text) =>
          new Promise((resolve) => {
            release = () => {
              resolve({ etag: `e-${text}` });
            };
          }),
      )
      .mockImplementation((text) => Promise.resolve({ etag: `e-${text}` }));
    const { saver } = make(write);
    saver.edit("ab");
    await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS);
    saver.edit("abc");
    saver.close();
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(write).toHaveBeenLastCalledWith("abc", "e-ab");
  });

  it("без правок уход с экрана ничего не пишет", async () => {
    const write = ok();
    const { saver } = make(write);
    saver.close();
    await vi.advanceTimersByTimeAsync(0);
    expect(write).not.toHaveBeenCalled();
  });
});

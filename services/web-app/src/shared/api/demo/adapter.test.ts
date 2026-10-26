import axios, { type AxiosAdapter } from "axios";
import { describe, expect, it, vi } from "vitest";
import { installDemoAdapter } from "./adapter";
import { createDemoRouter, demoJson } from "./router";

describe("installDemoAdapter", () => {
  it("forward() отдаёт обработчику разобранный JSON настоящего бэкенда", async () => {
    const raw: AxiosAdapter = (config) =>
      Promise.resolve({
        data: '{"disk_usage_warn_gb":10}',
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      });
    const client = axios.create({ adapter: raw });
    installDemoAdapter(
      client,
      createDemoRouter([
        {
          method: "GET",
          pattern: "/settings",
          handler: async (req) => {
            const data: unknown = (await req.forward()).data;
            return demoJson({ kind: typeof data, data });
          },
        },
      ]),
    );

    const response = await client.get("/settings");

    expect(response.data).toEqual({
      kind: "object",
      data: { disk_usage_warn_gb: 10 },
    });
  });
});

const client = () => {
  const instance = axios.create({ baseURL: "/api" });
  installDemoAdapter(
    instance,
    createDemoRouter([
      {
        method: "POST",
        pattern: "/upload",
        handler: () => demoJson({ ok: 1 }),
      },
    ]),
    { uploadStepMs: 1 },
  );
  return instance;
};

const form = () => {
  const data = new FormData();
  data.append("file", new File(["0123456789"], "a.bundle"));
  return data;
};

describe("демо-транспорт: отправка файла", () => {
  it("сообщает ход загрузки от начала до конца", async () => {
    const onUploadProgress = vi.fn();
    await client().post("/upload", form(), { onUploadProgress });
    const events = onUploadProgress.mock.calls as unknown as [
      { loaded: number; total: number },
    ][];
    const percents = events.map(([event]) =>
      Math.round((event.loaded / event.total) * 100),
    );
    expect(percents.length).toBeGreaterThan(1);
    expect(percents).toEqual([...percents].sort((a, b) => a - b));
    expect(percents.at(-1)).toBe(100);
  });

  it("прерывает отправку по сигналу", async () => {
    const controller = new AbortController();
    const onUploadProgress = vi.fn(() => {
      controller.abort();
    });
    await expect(
      client().post("/upload", form(), {
        onUploadProgress,
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ name: "CanceledError" });
    expect(onUploadProgress).toHaveBeenCalledTimes(1);
  });

  it("не прикидывается загрузкой там, где файла нет", async () => {
    const onUploadProgress = vi.fn();
    const response = await client().post(
      "/upload",
      { a: 1 },
      { onUploadProgress },
    );
    expect(response.data).toEqual({ ok: 1 });
    expect(onUploadProgress).not.toHaveBeenCalled();
  });
});

import axios, { type AxiosAdapter } from "axios";
import { describe, expect, it } from "vitest";
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

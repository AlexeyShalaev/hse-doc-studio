import axios, {
  type AxiosAdapter,
  type InternalAxiosRequestConfig,
} from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setUnauthorizedHandler } from "@shared/api/session";
import { systemApi, systemClient } from "./systemApi";

const answer =
  (status: number, body: unknown): AxiosAdapter =>
  (config: InternalAxiosRequestConfig) => {
    const response = {
      data: body,
      status,
      statusText: "",
      headers: {},
      config,
    };
    return status >= 400
      ? Promise.reject(
          new axios.AxiosError("x", "ERR_BAD_REQUEST", config, {}, response),
        )
      : Promise.resolve(response);
  };

describe("systemClient", () => {
  const original = systemClient.defaults.adapter ?? ["xhr", "fetch"];

  beforeEach(() => {
    setUnauthorizedHandler(null);
  });
  afterEach(() => {
    systemClient.defaults.adapter = original;
    setUnauthorizedHandler(null);
    vi.restoreAllMocks();
  });

  it("401 опроса будит обработчик конца сессии", async () => {
    const handler = vi.fn(() => Promise.resolve());
    setUnauthorizedHandler(handler);
    systemClient.defaults.adapter = answer(401, {});
    await expect(systemApi.getRunnerHealth()).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("500 обработчик конца сессии не будит", async () => {
    const handler = vi.fn(() => Promise.resolve());
    setUnauthorizedHandler(handler);
    systemClient.defaults.adapter = answer(500, {});
    await expect(systemApi.getRunnerHealth()).rejects.toBeTruthy();
    expect(handler).not.toHaveBeenCalled();
  });
});

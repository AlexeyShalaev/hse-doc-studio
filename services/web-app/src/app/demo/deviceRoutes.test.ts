import { describe, expect, it } from "vitest";
import { createDemoRouter } from "@shared/api/demo";
import {
  AccountDevicesSchema,
  LocalDeviceSchema,
  ProjectPeopleSchema,
  ProjectStudiosSchema,
  StudioLinkSchema,
} from "@entities/connected-device";
import {
  FetchBuildResponseSchema,
  LocalBuildsSchema,
  ProjectBuildsSchema,
} from "@entities/project-build";
import { cloudDeviceDemoRoutes, localDeviceDemoRoutes } from "./deviceRoutes";

// Демо отдаёт то, что принимают схемы настоящего контракта: иначе интерфейс, проверенный на демо, сломается вживую.

const call = async (
  routes: typeof cloudDeviceDemoRoutes,
  method: "GET" | "POST" | "PUT" | "DELETE",
  path: string,
  body: unknown = null,
) => {
  const found = createDemoRouter(routes).match(method, path);
  if (found === null) throw new Error(`no demo route: ${method} ${path}`);
  return found.handler({
    method,
    path,
    params: found.params,
    query: {},
    body,
    forward: () => Promise.reject(new Error("no backend")),
  });
};

describe("демо подключённых Студий", () => {
  it("облако: устройства, Студии проекта и сборки по схемам контракта", async () => {
    const accounts = await call(
      cloudDeviceDemoRoutes,
      "GET",
      "/account/devices",
    );
    expect(() => AccountDevicesSchema.parse(accounts?.data)).not.toThrow();
    const studios = await call(
      cloudDeviceDemoRoutes,
      "GET",
      "/projects/p1/studios",
    );
    expect(() => ProjectStudiosSchema.parse(studios?.data)).not.toThrow();
    const people = await call(
      cloudDeviceDemoRoutes,
      "POST",
      "/projects/p1/presence",
      {
        session_id: "tab-demo-0001",
        activity: "viewing",
        doc_id: null,
      },
    );
    expect(() => ProjectPeopleSchema.parse(people?.data)).not.toThrow();
    const builds = await call(
      cloudDeviceDemoRoutes,
      "GET",
      "/projects/p1/builds",
    );
    expect(() => ProjectBuildsSchema.parse(builds?.data)).not.toThrow();
    const forgot = await call(
      cloudDeviceDemoRoutes,
      "DELETE",
      "/account/devices/x",
    );
    expect(forgot?.status).toBe(204);
  });

  it("локальная Студия: имя, связь с облаком, сборки и получение", async () => {
    const device = await call(localDeviceDemoRoutes, "PUT", "/device", {
      name: "Офисный Mac",
    });
    expect(LocalDeviceSchema.parse(device?.data).name).toBe("Офисный Mac");
    const reset = await call(localDeviceDemoRoutes, "PUT", "/device", {
      name: null,
    });
    expect(LocalDeviceSchema.parse(reset?.data).custom).toBe(false);
    const link = await call(localDeviceDemoRoutes, "GET", "/git/studio-link");
    expect(() => StudioLinkSchema.parse(link?.data)).not.toThrow();
    const builds = await call(
      localDeviceDemoRoutes,
      "GET",
      "/projects/p1/git/builds",
    );
    expect(() => LocalBuildsSchema.parse(builds?.data)).not.toThrow();
    const fetched = await call(
      localDeviceDemoRoutes,
      "POST",
      "/projects/p1/git/builds/fetch",
      { doc_id: "tz", force: false, auto: false },
    );
    expect(() => FetchBuildResponseSchema.parse(fetched?.data)).not.toThrow();
  });
});

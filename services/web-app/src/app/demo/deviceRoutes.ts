import { demoJson, demoNoContent } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import {
  demoAccountDevices,
  demoCloudBuilds,
  demoLocalBuilds,
  demoProjectStudios,
  demoStudioLink,
} from "./deviceData";

// Демо подключённых Студий и сборок (docs/design/connected-devices.md). Облако: свои устройства, Студии проекта,
// статус сборок. Локальная Студия: имя устройства, связь с облаком, сборки и получение готового PDF.

const BUILDS = demoCloudBuilds;

/** Маршруты облака: подключаются к серверному демо. */
export const cloudDeviceDemoRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/account/devices",
    handler: () => demoJson(demoAccountDevices()),
  },
  {
    method: "DELETE",
    pattern: "/account/devices/:id",
    handler: () => demoNoContent(),
  },
  {
    method: "GET",
    pattern: "/projects/:id/studios",
    handler: () => demoJson(demoProjectStudios()),
  },
  {
    method: "GET",
    pattern: "/projects/:id/builds",
    handler: () => demoJson(BUILDS()),
  },
];

let localName: string | null = "MacBook Анны";

/** Маршруты локальной Студии: подключаются к демо git. */
export const localDeviceDemoRoutes: DemoRoute[] = [
  {
    method: "GET",
    pattern: "/device",
    handler: () =>
      demoJson({
        device_id: "e1123c9cadb64dafd48432897072a826",
        name: localName ?? "MacBook-Air-Anna",
        default_name: "MacBook-Air-Anna",
        custom: localName !== null,
      }),
  },
  {
    method: "PUT",
    pattern: "/device",
    handler: (req) => {
      const name = (req.body as { name?: string | null } | undefined)?.name;
      localName = name ? name : null;
      return demoJson({
        device_id: "e1123c9cadb64dafd48432897072a826",
        name: localName ?? "MacBook-Air-Anna",
        default_name: "MacBook-Air-Anna",
        custom: localName !== null,
      });
    },
  },
  {
    method: "GET",
    pattern: "/git/studio-link",
    handler: (req) => {
      const id = req.query.project_id;
      return demoJson(demoStudioLink(typeof id === "string" ? id : null));
    },
  },
  {
    method: "GET",
    pattern: "/projects/:id/git/builds",
    handler: () => demoJson(demoLocalBuilds()),
  },
  {
    method: "POST",
    pattern: "/projects/:id/git/builds/fetch",
    handler: (req) => {
      const docId = (req.body as { doc_id?: string | null } | undefined)
        ?.doc_id;
      return demoJson({
        items: [
          {
            doc_id: docId ?? "tz",
            status: "downloaded",
            code: null,
            size: 812_000,
          },
        ],
      });
    },
  },
];

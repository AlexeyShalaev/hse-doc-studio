import { demoError, demoJson } from "@shared/api/demo";
import type { DemoResponse, DemoRoute } from "@shared/api/demo";
import { normalizeDeviceCode } from "@shared/ui/DeviceCodeCard";
import type {
  DeviceAuthorizationInfo,
  GitScope,
  ProjectGitRemote,
} from "@entities/git-server";
import { effectiveRole } from "./projectAccess";
import type { ServerDemoWorld } from "./world";

// Сервер как git-remote в демо (раздел 10.11–10.12): страница /device с живыми
// кодами и адрес клонирования проекта. Состояние кодов на мир: при смене
// сценария коды снова ждут решения.

const DEMO_ORIGIN = "https://studio.example.org";
const MINUTE = 60_000;

type DemoDevice = DeviceAuthorizationInfo;

const at = (offsetMs: number): string =>
  new Date(Date.now() + offsetMs).toISOString();

const seedDevices = (): Record<string, DemoDevice> => {
  const base: DemoDevice = {
    user_code: "BCDF-2345",
    client_name: "Студия на MacBook Анны",
    client_kind: "desktop",
    requested_scopes: ["git:read", "git:write"],
    granted_scopes: null,
    client_ip: "203.0.113.7",
    requested_at: at(-2 * MINUTE),
    expires_at: at(8 * MINUTE),
    status: "pending",
  };
  return {
    "BCDF-2345": base,
    "HJKL-3456": {
      ...base,
      user_code: "HJKL-3456",
      client_name: "git на сервере лаборатории",
      client_kind: "cli",
      requested_scopes: ["git:read"],
      client_ip: null,
    },
    "XKCD-7777": {
      ...base,
      user_code: "XKCD-7777",
      requested_at: at(-20 * MINUTE),
      expires_at: at(-10 * MINUTE),
    },
    "QRST-2468": {
      ...base,
      user_code: "QRST-2468",
      status: "approved",
      granted_scopes: ["git:read", "git:write"],
    },
  };
};

const devicesByWorld = new WeakMap<
  ServerDemoWorld,
  Record<string, DemoDevice>
>();

const devicesOf = (world: ServerDemoWorld): Record<string, DemoDevice> => {
  let found = devicesByWorld.get(world);
  if (!found) {
    found = seedDevices();
    devicesByWorld.set(world, found);
  }
  return found;
};

const str = (value: unknown): string =>
  typeof value === "string" ? value : "";

const unauth = (): DemoResponse =>
  demoError(401, "auth_required", "Authentication required");

const expired = (device: DemoDevice): boolean =>
  device.status === "pending" && Date.parse(device.expires_at) <= Date.now();

const view = (device: DemoDevice): DemoDevice =>
  expired(device) ? { ...device, status: "expired" } : device;

export const createGitRemoteRoutes = (
  getWorld: () => ServerDemoWorld,
): DemoRoute[] => {
  const signedIn = (): boolean => getWorld().bootstrap.user !== null;
  const find = (raw: unknown): DemoDevice | undefined => {
    const code = normalizeDeviceCode(str(raw));
    return code ? devicesOf(getWorld())[code] : undefined;
  };
  return [
    {
      method: "GET",
      pattern: "/account/device/:code",
      handler: (req) => {
        if (!signedIn()) return unauth();
        const device = find(req.params.code);
        if (!device) return demoError(404, "device_code_invalid", "Unknown");
        if (expired(device)) {
          return demoError(410, "device_code_expired", "The code expired");
        }
        return demoJson(view(device));
      },
    },
    {
      method: "POST",
      pattern: "/account/device/:code",
      handler: (req) => {
        if (!signedIn()) return unauth();
        const device = find(req.params.code);
        const body = (req.body ?? {}) as Record<string, unknown>;
        const decision = str(body.decision);
        if (!device) return demoError(404, "device_code_invalid", "Unknown");
        if (expired(device)) {
          return demoError(410, "device_code_expired", "The code expired");
        }
        if (device.status !== "pending") {
          return demoError(409, "device_code_used", "The code was used");
        }
        if (decision === "deny") {
          device.status = "denied";
          return demoJson(device);
        }
        const scopes = Array.isArray(body.scopes)
          ? (body.scopes as GitScope[])
          : [];
        const granted = [...new Set<GitScope>(["git:read", ...scopes])].sort();
        if (!granted.every((s) => device.requested_scopes.includes(s))) {
          return demoError(422, "device_scope_invalid", "Scope not requested");
        }
        device.status = "approved";
        device.granted_scopes = granted;
        return demoJson(device);
      },
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/git-remote",
      handler: (req) => {
        const world = getWorld();
        const user = world.bootstrap.user;
        if (!user) return unauth();
        const project = world.projects.find(
          (p) => p.summary.id === req.params.projectId,
        );
        const role = project ? effectiveRole(world, project, user.id) : null;
        if (!project || !role) {
          return demoError(404, "not_found", "Project not found or no access");
        }
        const enabled = world.bootstrap.capabilities.git_remote;
        const body: ProjectGitRemote = enabled
          ? {
              enabled: true,
              clone_url: `${DEMO_ORIGIN}/git/${project.summary.id}.git`,
              can_push: role === "owner" || role === "editor",
              branch: "master",
            }
          : { enabled: false, clone_url: null, can_push: false, branch: null };
        return demoJson(body);
      },
    },
  ];
};

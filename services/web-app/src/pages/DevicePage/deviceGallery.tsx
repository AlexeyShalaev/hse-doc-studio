import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import type { DeviceAuthorizationInfo } from "@entities/git-server";
import { DeviceView, type DeviceViewState } from "./DeviceView";

const NOW = Date.parse("2026-11-01T09:42:00Z");
const noop = () => undefined;

const INFO: DeviceAuthorizationInfo = {
  user_code: "BCDF-2345",
  client_name: "Студия на MacBook Анны",
  client_kind: "desktop",
  requested_scopes: ["git:read", "git:write"],
  granted_scopes: null,
  client_ip: "203.0.113.7",
  requested_at: "2026-11-01T09:40:00Z",
  expires_at: "2026-11-01T09:50:00Z",
  status: "pending",
};

const entry = (
  id: string,
  title: string,
  state: DeviceViewState,
): GalleryEntry => ({
  id,
  title,
  frame: "page",
  width: 640,
  render: () => (
    <DeviceView
      state={state}
      now={NOW}
      onCode={noop}
      onApprove={noop}
      onDeny={noop}
      onRetry={noop}
      onOtherCode={noop}
    />
  ),
});

/** Страница /device: вход Студии на компьютере в git сервера (раздел 10.11). */
export const getDeviceGallery = (): GalleryGroup[] => [
  {
    id: "device",
    title: "Подтверждение входа устройства (git)",
    description:
      "Живые коды демо-мира: BCDF-2345 ждёт, HJKL-3456 просит только чтение, XKCD-7777 истёк, QRST-2468 использован.",
    entries: [
      entry("enter", "Код не указан в адресе", { kind: "enter" }),
      entry("loading", "Проверяем код", { kind: "loading" }),
      entry("pending", "Ждёт решения", { kind: "pending", info: INFO }),
      entry("pending_read", "CLI просит только чтение", {
        kind: "pending",
        info: {
          ...INFO,
          client_name: "git на сервере лаборатории",
          client_kind: "cli",
          requested_scopes: ["git:read"],
          client_ip: null,
        },
      }),
      entry("approved", "Разрешено", { kind: "result", result: "approved" }),
      entry("denied", "Отклонено", { kind: "result", result: "denied" }),
      entry("expired", "Код истёк", { kind: "result", result: "expired" }),
      entry("invalid", "Код не найден", { kind: "result", result: "invalid" }),
      entry("used", "Код уже использован", { kind: "result", result: "used" }),
      entry("error", "Сервер не ответил", { kind: "error" }),
    ],
  },
];

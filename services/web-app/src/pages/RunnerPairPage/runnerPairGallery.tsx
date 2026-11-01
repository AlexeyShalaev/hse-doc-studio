import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import type { RunnerPairingInfo } from "@entities/runner";
import { RunnerPairView, type RunnerPairViewState } from "./RunnerPairView";

const NOW = Date.parse("2026-10-30T09:42:00Z");
const noop = () => undefined;

const INFO: RunnerPairingInfo = {
  user_code: "BCDF-2345",
  name: "MacBook Анны",
  host_kind: "desktop",
  requested_at: "2026-10-30T09:40:00Z",
  expires_at: "2026-10-30T09:50:00Z",
  client_ip: "203.0.113.7",
  status: "pending",
};

const entry = (
  id: string,
  title: string,
  state: RunnerPairViewState,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "page",
  width: 640,
  render: () => (
    <RunnerPairView
      state={state}
      now={NOW}
      onCode={noop}
      onApprove={noop}
      onDeny={noop}
      onRetry={noop}
      onOtherCode={noop}
    />
  ),
  ...extra,
});

/** Страница подтверждения кода из Студии: ввод, запрос и все итоги. */
export const getRunnerPairGallery = (): GalleryGroup[] => [
  {
    id: "runner-pair",
    title: "Подтверждение сопряжения",
    description:
      "Живые коды демо-мира: BCDF-2345 ждёт, LMNP-6789 упирается в предел, XKCD-7777 истёк, QRST-2468 использован.",
    entries: [
      entry("enter", "Код не указан в адресе", { kind: "enter" }),
      entry("loading", "Проверяем код", { kind: "loading" }),
      entry("pending", "Ждёт решения", { kind: "pending", info: INFO }),
      entry("pending_cli", "Консольный раннер без IP", {
        kind: "pending",
        info: {
          ...INFO,
          name: "Сервер в лаборатории",
          host_kind: "cli",
          client_ip: null,
        },
      }),
      entry("approved", "Подключено", { kind: "result", result: "approved" }),
      entry("denied", "Отклонено", { kind: "result", result: "denied" }),
      entry("expired", "Код истёк", { kind: "result", result: "expired" }),
      entry("invalid", "Код не найден", { kind: "result", result: "invalid" }),
      entry("used", "Код уже использован", { kind: "result", result: "used" }),
      entry("disabled", "Личные раннеры выключены", {
        kind: "result",
        result: "disabled",
      }),
      entry("limit", "Предел раннеров", { kind: "result", result: "limit" }),
      entry("error", "Сервер не ответил", { kind: "error" }),
    ],
  },
];

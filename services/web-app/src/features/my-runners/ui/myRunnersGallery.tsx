import type { MyRunner, MyRunnerToken } from "@entities/runner";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { DialogLauncher } from "@shared/ui/StateGallery";
import { ConnectRunnerDialog } from "./ConnectRunnerDialog";
import { MyRunnersSection } from "./MyRunnersSection";
import { MyRunnersView } from "./MyRunnersView";
import { ReconnectDialog, RenameDialog, RotatedDialog } from "./RunnerDialogs";

const W = 760;
const noop = () => undefined;
// Время галереи постоянно: «был в сети … назад» не меняется между снимками.
const NOW = Date.parse("2026-10-30T10:00:00Z");
const at = (secondsAgo: number) =>
  new Date(NOW - secondsAgo * 1000).toISOString();

const base: MyRunner = {
  id: "r-mac",
  name: "MacBook Анны",
  state: "online",
  host_kind: "desktop",
  tags: ["ai", "archive:7z", "pack", "tex"],
  concurrency: 1,
  ai_concurrency: 2,
  version: "0.3.0",
  created_at: at(2 * 86400),
  last_seen_at: at(8),
  last_seen_ip: "203.0.113.7",
  paused: false,
  paused_by: null,
  revoked: false,
  running_jobs: 1,
  ai_endpoints: [{ name: "ollama", flavor: "ollama" }],
  features: ["ai_relay", "ai_slots", "announce", "offline"],
};

const RUNNERS: MyRunner[] = [
  base,
  {
    ...base,
    id: "r-home",
    name: "Домашний сервер",
    host_kind: "cli",
    state: "paused",
    paused: true,
    paused_by: "owner",
    concurrency: 2,
    running_jobs: 0,
    last_seen_at: at(20),
    last_seen_ip: "198.51.100.8",
    tags: ["ai", "pack", "tex"],
    ai_endpoints: [{ name: "vllm", flavor: "openai" }],
  },
  {
    ...base,
    id: "r-work",
    name: "Рабочий ПК",
    state: "stale",
    running_jobs: 0,
    ai_concurrency: 0,
    ai_endpoints: [],
    tags: ["pack", "tex"],
    last_seen_at: at(180),
  },
  {
    ...base,
    id: "r-old",
    name: "Старый ноутбук",
    host_kind: "cli",
    state: "offline",
    version: "0.1.4",
    running_jobs: 0,
    ai_concurrency: 0,
    ai_endpoints: [],
    features: [],
    tags: ["pack", "tex"],
    last_seen_at: at(2 * 86400),
    last_seen_ip: null,
  },
  {
    ...base,
    id: "r-gone",
    name: "Ноутбук в общежитии",
    host_kind: "cli",
    state: "revoked",
    revoked: true,
    running_jobs: 0,
    ai_endpoints: [],
    last_seen_at: at(6 * 86400),
  },
];

const TOKENS: MyRunnerToken[] = [
  {
    id: "t1",
    label: "Сервер на даче",
    created_at: at(3600),
    expires_at: new Date(NOW + 23 * 3600 * 1000).toISOString(),
    used: false,
    revoked: false,
  },
];

const view = (extra: Partial<Parameters<typeof MyRunnersView>[0]> = {}) => (
  <MyRunnersView
    status="ready"
    runners={RUNNERS}
    tokens={TOKENS}
    enabled
    serverVersion="0.3.0"
    now={NOW}
    onConnect={noop}
    onRename={noop}
    onTogglePause={noop}
    onRotate={noop}
    onReconnect={noop}
    onRevoke={noop}
    onRevokeToken={noop}
    {...extra}
  />
);

const entry = (
  id: string,
  title: string,
  render: GalleryEntry["render"],
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({ id, title, frame: "window", width: W, render, ...extra });

const dialog = (
  label: string,
  node: (isOpen: boolean, close: () => void) => React.ReactNode,
) => (
  <DialogLauncher label={label}>
    {({ isOpen, close }) => node(isOpen, close)}
  </DialogLauncher>
);

/** «Мои раннеры»: все состояния списка и диалогов. */
export const getMyRunnersGallery = (): GalleryGroup[] => [
  {
    id: "my-runners",
    title: "Настройки: мои раннеры",
    description:
      "Свои машины, которые собирают свои проекты: в сети, на паузе, давно не отвечал, не в сети, отозван, выключены админом.",
    entries: [
      entry("all_states", "Раннеры во всех состояниях и токен", () => view()),
      entry("with_revoked", "Показаны отозванные", () =>
        view({ startShowRevoked: true }),
      ),
      entry("empty", "Раннеров пока нет", () =>
        view({ runners: [], tokens: [] }),
      ),
      entry("offline", "Единственный раннер не в сети", () =>
        view({
          runners: [
            {
              ...base,
              state: "offline",
              running_jobs: 0,
              last_seen_at: at(7200),
            },
          ],
          tokens: [],
        }),
      ),
      entry("disabled", "Личные раннеры выключены администратором", () =>
        view({
          enabled: false,
          runners: RUNNERS.map((r) =>
            r.revoked ? r : { ...r, state: "disabled" as const },
          ),
          tokens: [],
        }),
      ),
      entry("paused_by_admin", "Приостановлен администратором", () =>
        view({
          runners: [
            {
              ...base,
              state: "paused",
              paused: true,
              paused_by: "admin",
              running_jobs: 0,
            },
          ],
          tokens: [],
        }),
      ),
      entry("loading", "Загрузка", () => view({ status: "loading" })),
      entry("error", "Список не загрузился", () =>
        view({ status: "error", onRetry: noop }),
      ),
      entry("live", "Живой раздел: все состояния", () => <MyRunnersSection />, {
        scenario: "runners_ready",
      }),
      entry(
        "live_none",
        "Живой раздел: раннеров нет",
        () => <MyRunnersSection />,
        {
          scenario: "runners_none",
        },
      ),
      entry(
        "live_disabled",
        "Живой раздел: выключены админом",
        () => <MyRunnersSection />,
        { scenario: "runners_disabled" },
      ),
    ],
  },
  {
    id: "my-runners-dialogs",
    title: "Настройки: подключение раннера",
    entries: [
      entry("connect_studio", "Подключить: Студия на компьютере", () =>
        dialog("Открыть", (isOpen, close) => (
          <ConnectRunnerDialog
            isOpen={isOpen}
            onClose={close}
            onPairCode={noop}
            onCreateToken={noop}
          />
        )),
      ),
      entry("connect_server", "Подключить: сервер, форма токена", () =>
        dialog("Открыть", (isOpen, close) => (
          <ConnectRunnerDialog
            isOpen={isOpen}
            initialTab="server"
            onClose={close}
            onPairCode={noop}
            onCreateToken={noop}
          />
        )),
      ),
      entry("connect_limit", "Подключить: предел раннеров", () =>
        dialog("Открыть", (isOpen, close) => (
          <ConnectRunnerDialog
            isOpen={isOpen}
            initialTab="server"
            error="Достигнут предел личных раннеров. Отзовите ненужный раннер или неиспользованный токен."
            onClose={close}
            onPairCode={noop}
            onCreateToken={noop}
          />
        )),
      ),
      entry("connect_created", "Подключить: токен показан один раз", () =>
        dialog("Открыть", (isOpen, close) => (
          <ConnectRunnerDialog
            isOpen={isOpen}
            created={{
              token: TOKENS[0] ?? {
                id: "t",
                label: "",
                created_at: at(0),
                expires_at: at(0),
                used: false,
                revoked: false,
              },
              secret: "hsrt_Q2xvdWRSdW5uZXJUb2tlbkV4YW1wbGUx",
              command:
                "HSE_RUNNER__API_URL=https://studio.example.org HSE_RUNNER__TOKEN=hsrt_Q2xvdWRSdW5uZXJUb2tlbkV4YW1wbGUx hse-doc-studio runner",
              docker_command:
                "docker run -d --name hse-runner --restart unless-stopped -v /var/run/docker.sock:/var/run/docker.sock -e HSE_RUNNER__TOKEN=hsrt_Q2xvdWRSdW5uZXJUb2tlbkV4YW1wbGUx ghcr.io/alexeyshalaev/hse-doc-studio:0.3.0 hse-doc-studio runner",
            }}
            onClose={close}
            onPairCode={noop}
            onCreateToken={noop}
          />
        )),
      ),
      entry("rename", "Переименовать", () =>
        dialog("Открыть", (isOpen, close) => (
          <RenameDialog
            runner={isOpen ? base : null}
            onSave={noop}
            onClose={close}
          />
        )),
      ),
      entry("rotated", "Новый токен после смены", () =>
        dialog("Открыть", (isOpen, close) => (
          <RotatedDialog
            rotated={
              isOpen
                ? {
                    runner: RUNNERS[1] ?? base,
                    runner_token: "hsrn_Um90YXRlZFJ1bm5lclRva2VuRXhhbXBsZTI",
                    command:
                      "HSE_RUNNER__API_URL=https://studio.example.org HSE_RUNNER__RUNNER_TOKEN=hsrn_Um90YXRlZFJ1bm5lclRva2VuRXhhbXBsZTI hse-doc-studio runner",
                  }
                : null
            }
            onClose={close}
          />
        )),
      ),
      entry("reconnect", "Студия: подключить заново", () =>
        dialog("Открыть", (isOpen, close) => (
          <ReconnectDialog runner={isOpen ? base : null} onClose={close} />
        )),
      ),
    ],
  },
];

import type { RemoteRunnerStatus } from "@entities/runner";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import { RemoteRunnerSection } from "./RemoteRunnerSection";
import { RemoteRunnerView, type CloudModelCandidate } from "./RemoteRunnerView";

const NOW = Date.parse("2026-10-30T09:42:00Z");
const noop = () => undefined;

const OLLAMA: CloudModelCandidate = {
  providerId: "6a5b4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
  name: "Ollama",
  flavor: "ollama",
  url: "http://localhost:11434/v1",
  defaultName: "ollama",
};
const LM_STUDIO: CloudModelCandidate = {
  providerId: "7b6c5d4e-3f2a-4b1c-8d9e-0f1a2b3c4d5e",
  name: "LM Studio",
  flavor: "openai",
  url: "http://192.168.1.20:1234/v1",
  defaultName: "lm-studio",
};

const ONLINE: RemoteRunnerStatus = {
  enabled: true,
  server_url: "https://studio.example.org",
  paired: true,
  runner_id: "4f1c2b3a5d6e47f89a0b1c2d3e4f5a6b",
  runner_name: "MacBook Анны",
  state: "online",
  detail_code: null,
  running_jobs: 1,
  concurrency: 1,
  yield_to_local: true,
  docker: "ok",
  tex_image: "ready",
  ai_endpoints: [
    {
      name: "ollama",
      provider_id: OLLAMA.providerId,
      flavor: "ollama",
      url: OLLAMA.url,
    },
  ],
  pairing: null,
};
const OFF: RemoteRunnerStatus = {
  ...ONLINE,
  enabled: false,
  paired: false,
  runner_id: null,
  runner_name: null,
  server_url: null,
  state: "off",
  running_jobs: 0,
  ai_endpoints: [],
};

const entry = (
  id: string,
  title: string,
  status: RemoteRunnerStatus,
  extra: Partial<GalleryEntry> = {},
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: 720,
  render: () => (
    <RemoteRunnerView
      status={status}
      candidates={[OLLAMA, LM_STUDIO]}
      now={NOW}
      detailText={
        status.detail_code === "remote_runner_unreachable"
          ? "Сервер не ответил. Проверьте адрес и подключение к сети."
          : status.detail_code
      }
      onToggle={noop}
      onPair={noop}
      onToken={noop}
      onCancelPairing={noop}
      onUnpair={noop}
      onConcurrency={noop}
      onYield={noop}
      onModels={noop}
    />
  ),
  ...extra,
});

/** «Облачные сборки» локальной Студии: каждое состояние подключения. */
export const getRemoteRunnerGallery = (): GalleryGroup[] => [
  {
    id: "remote-runner",
    title: "Локальная Студия: облачные сборки",
    description:
      "Студия собирает облачные проекты человека своим Docker: переключатель, код сопряжения, состояния, проверки и модели для облака.",
    entries: [
      entry("off", "Выключено", OFF),
      entry("unpaired", "Включено, не подключено", {
        ...OFF,
        enabled: true,
        state: "unpaired",
      }),
      entry("pairing", "Ждём подтверждения кода", {
        ...OFF,
        enabled: true,
        state: "pairing",
        server_url: "https://studio.example.org",
        pairing: {
          user_code: "BCDF-2345",
          verification_uri_complete:
            "https://studio.example.org/settings/runners/pair?code=BCDF-2345",
          expires_at: "2026-10-30T09:50:00Z",
        },
      }),
      entry("connecting", "Подключаемся", {
        ...ONLINE,
        state: "connecting",
        running_jobs: 0,
      }),
      entry("online", "В сети, берёт сборки", ONLINE),
      entry("paused", "На паузе на сайте", {
        ...ONLINE,
        state: "paused",
        running_jobs: 0,
      }),
      entry("offline", "Сервер недоступен", {
        ...ONLINE,
        state: "offline",
        running_jobs: 0,
        detail_code: "remote_runner_unreachable",
      }),
      entry("revoked", "Раннер отозван на сервере", {
        ...ONLINE,
        state: "revoked",
        paired: false,
        running_jobs: 0,
      }),
      entry("disabled", "Личные раннеры выключены на сервере", {
        ...ONLINE,
        state: "disabled",
        running_jobs: 0,
      }),
      entry("docker_missing", "Нет Docker и образа", {
        ...ONLINE,
        docker: "missing",
        tex_image: "missing",
        running_jobs: 0,
      }),
      entry("image_missing", "Нет образа TeX", {
        ...ONLINE,
        tex_image: "missing",
        running_jobs: 0,
      }),
      {
        id: "live_off",
        title: "Живой раздел: от выключенного до подключения",
        note: "Включите, нажмите «Подключить»: через несколько секунд Студия подключится.",
        frame: "window",
        width: 720,
        scenario: "local_remote_off",
        render: () => <RemoteRunnerSection />,
      },
      {
        id: "live_online",
        title: "Живой раздел: в сети",
        frame: "window",
        width: 720,
        scenario: "local_remote_online",
        render: () => <RemoteRunnerSection />,
      },
    ],
  },
];

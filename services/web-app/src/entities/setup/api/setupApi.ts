import { z } from "zod";
import { apiClient } from "@shared/api";

/**
 * Состояние установки: готово ли приложение работать и что мешает.
 *
 * Коды причин намеренно машиночитаемые — тексты живут в словарях интерфейса.
 * Бэкенд не знает языка пользователя настолько, чтобы объяснять ему, как чинить
 * его же установку.
 */
export const SetupCheckSchema = z.object({
  id: z.string(),
  severity: z.enum(["ok", "warning", "blocker"]),
  code: z.string(),
  context: z.record(z.string(), z.string()).default({}),
});

export const SetupStatusSchema = z.object({
  // false — интерфейс обязан показать мастер вместо рабочего экрана.
  is_ready: z.boolean(),
  deployment_mode: z.enum(["all-in-one", "standard", "native"]),
  checks: z.array(SetupCheckSchema).default([]),
  // Имя compose-проекта, если контейнер поднят им. Такую установку мастер не
  // чинит сам: следующий `docker compose up -d` вернул бы старую конфигурацию,
  // и человек решил бы, что приложение забыло его папку.
  compose_project: z.string().nullish(),
  can_self_apply: z.boolean().default(true),
  // Версия — единственное, что стартовый экран может сказать о себе сам:
  // «О программе» за мастером ещё не доступна.
  app_version: z.string().default(""),
});

export const ProbeEntrySchema = z.object({
  name: z.string(),
  is_dir: z.boolean(),
});

export const ProbeFolderSchema = z.object({
  status: z.enum(["ok", "mount_failed", "docker_unavailable", "timeout"]),
  // Есть ли такая папка — ОТДЕЛЬНО от «пустая». Несуществующий путь и пустой
  // каталог выглядели бы одинаково, если проверять монтированием напрямую.
  exists: z.boolean().default(false),
  // Содержимое: по нему человек узнаёт своё место на диске и ходит вглубь.
  entries: z.array(ProbeEntrySchema).default([]),
  is_empty: z.boolean().default(false),
  writable: z.boolean().default(false),
  // Папка похожа на каталог данных прежней установки — проекты и настройки
  // подхватятся, и об этом надо сказать явно, а не молчать.
  looks_like_install: z.boolean().default(false),
  // Место на диске с этой папкой: на первой же сборке докер скачивает образ
  // TeX Live в несколько гигабайт, и узнать об их отсутствии посреди сборки
  // куда хуже, чем при выборе папки.
  free_bytes: z.number().nullish(),
  total_bytes: z.number().nullish(),
  reason: z.string().nullish(),
  detail: z.string().nullish(),
});

export const ApplySetupSchema = z.object({
  // true — приложение уже пересоздаётся, соединение вот-вот оборвётся.
  applied: z.boolean(),
  error_code: z.string().nullish(),
  probe: ProbeFolderSchema.nullish(),
});

export type ProbeEntry = z.infer<typeof ProbeEntrySchema>;
export type SetupCheck = z.infer<typeof SetupCheckSchema>;
export type SetupStatus = z.infer<typeof SetupStatusSchema>;
export type ProbeFolderResult = z.infer<typeof ProbeFolderSchema>;
export type ApplySetupResult = z.infer<typeof ApplySetupSchema>;

export const setupApi = {
  status: async (): Promise<SetupStatus> => {
    // Без тоста: этим запросом мастер ждёт возвращения сервера, который сам же
    // и попросил пересоздать. Обрыв связи здесь — часть сценария, а не сбой, и
    // красное «Network Error» поверх экрана «ждём, когда оно вернётся» только
    // пугает. Отказ по-прежнему возвращается вызывающему.
    const response = await apiClient.get<unknown>("/setup/status", {
      silentError: true,
    });
    return SetupStatusSchema.parse(response.data);
  },

  probeFolder: async (hostPath: string): Promise<ProbeFolderResult> => {
    const response = await apiClient.post<unknown>("/setup/probe-folder", {
      host_path: hostPath,
    });
    return ProbeFolderSchema.parse(response.data);
  },

  environment: async (): Promise<SetupEnvironment> => {
    const response = await apiClient.get<unknown>("/setup/environment");
    return SetupEnvironmentSchema.parse(response.data);
  },

  apply: async (
    hostPath: string,
    fontsHostPath?: string | null,
    prefetchTexImage = true,
  ): Promise<ApplySetupResult> => {
    const response = await apiClient.post<unknown>("/setup/apply", {
      host_path: hostPath,
      fonts_host_path: fontsHostPath ?? null,
      prefetch_tex_image: prefetchTexImage,
    });
    return ApplySetupSchema.parse(response.data);
  },
};

export const DockerEngineSchema = z.object({
  server_version: z.string(),
  os_type: z.string(),
  operating_system: z.string(),
  architecture: z.string(),
  // Ресурсы КОНТЕЙНЕРОВ, а не всей машины: на Docker Desktop это квота
  // виртуальной машины, и она же определяет скорость сборок.
  cpus: z.number(),
  memory_bytes: z.number(),
});

export const ContainerMountSchema = z.object({
  source: z.string(),
  destination: z.string(),
  read_only: z.boolean(),
});

export const ContainerRuntimeSchema = z.object({
  image: z.string(),
  published_ports: z.array(z.string()).default([]),
  mounts: z.array(ContainerMountSchema).default([]),
  socket_mounted: z.boolean(),
  group_add: z.array(z.string()).default([]),
  restart_policy: z.string(),
  network_mode: z.string(),
});

export const HostFontsSchema = z.object({
  // Каталог, из которого приложение возьмёт шрифты пользователя. null — ни
  // одно стандартное место не подошло, и путь нужно указать руками.
  directory: z.string().nullish(),
  count: z.number().default(0),
});

export const TexImageSchema = z.object({
  image: z.string(),
  present: z.boolean(),
});

export const SetupEnvironmentSchema = z.object({
  engine: DockerEngineSchema.nullish(),
  container: ContainerRuntimeSchema.nullish(),
  fonts: HostFontsSchema.nullish(),
  tex: TexImageSchema.nullish(),
});

export type DockerEngine = z.infer<typeof DockerEngineSchema>;
export type ContainerRuntime = z.infer<typeof ContainerRuntimeSchema>;
export type HostFonts = z.infer<typeof HostFontsSchema>;
export type SetupEnvironment = z.infer<typeof SetupEnvironmentSchema>;

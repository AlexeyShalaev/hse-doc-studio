// Команды установки локальной Студии с подставленным адресом сервера.
// Скрипты deploy/install.sh и install.ps1 понимают HSE_STUDIO_CONNECT: после
// запуска они открывают экран подключения к этому серверу, а не главную.

import { DEFAULT_LOCAL_PORT } from "./paths";

export const INSTALL_OSES = ["macos", "windows", "linux"] as const;
export type InstallOs = (typeof INSTALL_OSES)[number];

export type InstallInput = {
  os: InstallOs;
  /** `https://raw.githubusercontent.com/<repo>/master/deploy` */
  installBaseUrl: string;
  /** Образ без тега. */
  image: string;
  serverUrl: string;
  port: number;
  /** Тег образа; null значит latest. */
  tag: string | null;
  lang: "ru" | "en";
};

/** ОС посетителя по user agent; всё незнакомое считаем Linux. */
export const detectInstallOs = (userAgent: string): InstallOs => {
  const ua = userAgent.toLowerCase();
  if (ua.includes("windows")) return "windows";
  if (ua.includes("mac os") || ua.includes("macintosh")) return "macos";
  return "linux";
};

const shQuote = (value: string): string => `'${value.replace(/'/g, `'\\''`)}'`;
const psQuote = (value: string): string => `'${value.replace(/'/g, "''")}'`;

/** Одна строка: скачать скрипт и запустить его с адресом этого сервера. */
export const installCommand = (input: InstallInput): string => {
  const vars: [string, string][] = [
    ["HSE_STUDIO_LANG", input.lang],
    ["HSE_STUDIO_CONNECT", input.serverUrl],
  ];
  if (input.port !== DEFAULT_LOCAL_PORT)
    vars.push(["PORT", String(input.port)]);
  if (input.tag) vars.push(["TAG", input.tag]);
  if (input.os === "windows") {
    const env = vars
      .map(([name, value]) => `$env:${name}=${psQuote(value)}; `)
      .join("");
    return `${env}irm ${input.installBaseUrl}/install.ps1 | iex`;
  }
  const env = vars
    .map(([name, value]) =>
      name === "HSE_STUDIO_CONNECT"
        ? `${name}=${shQuote(value)}`
        : `${name}=${value}`,
    )
    .join(" ");
  return `curl -fsSL ${input.installBaseUrl}/install.sh | ${env} sh`;
};

/** Без скриптов: тот же контейнер, что поднимает install.sh (deploy/README.md). */
export const manualCommand = (input: InstallInput): string => {
  const group =
    input.os === "linux"
      ? `--group-add "$(stat -c '%g' /var/run/docker.sock)"`
      : "--group-add 0";
  return [
    "docker run -d --name hse-doc-studio --restart unless-stopped",
    `-p ${String(input.port)}:8000`,
    "-v /var/run/docker.sock:/var/run/docker.sock",
    group,
    "--add-host=host.docker.internal:host-gateway",
    "-e HSE_STUDIO__SERVER__PORT=8000",
    `${input.image}:${input.tag ?? "latest"}`,
  ].join(" ");
};

/** Куда идти за Docker на этой ОС. */
export const DOCKER_DOWNLOAD: Record<InstallOs, string> = {
  macos: "https://docs.docker.com/desktop/setup/install/mac-install/",
  windows: "https://docs.docker.com/desktop/setup/install/windows-install/",
  linux: "https://docs.docker.com/engine/install/",
};

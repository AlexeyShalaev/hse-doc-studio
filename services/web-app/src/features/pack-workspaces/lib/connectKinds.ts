/** Три пути подключения пространства (pack-studio-ux.md, 5.1). */
export type ConnectKind = "official" | "git" | "folder";

/**
 * Какие пути доступны здесь. Официальные шаблоны есть, когда установка знает их
 * репозиторий и пространство над ним ещё не открыто (открытое уже в списке);
 * папка на диске только там, где Студия видит файловую систему.
 */
export const availableConnectKinds = (opts: {
  officialAvailable: boolean;
  allowFolder: boolean;
}): ConnectKind[] => [
  ...(opts.officialAvailable ? (["official"] as const) : []),
  "git",
  ...(opts.allowFolder ? (["folder"] as const) : []),
];

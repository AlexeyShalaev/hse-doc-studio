import { useEffect } from "react";
import { readUi, writeUi } from "../context/memory";
import { useSpace } from "../context/SpaceContext";

// Версия, где человек был в каждом шаблоне. Только удобство (память браузера): без неё смена
// пака или шаблона открывает версию по умолчанию, а с изменениями версию с изменениями.

const keyOf = (pack: string, template: string): string =>
  `nav.last.${pack}/${template}`;

export const readLastVersion = (
  workspaceId: string,
  pack: string,
  template: string,
): string | null => {
  const value = readUi(workspaceId, keyOf(pack, template));
  return typeof value === "string" ? value : null;
};

export const writeLastVersion = (
  workspaceId: string,
  pack: string,
  template: string,
  version: string,
): void => {
  writeUi(workspaceId, keyOf(pack, template), version);
};

/** Запоминает открытую версию шаблона при каждой смене места. */
export const useRememberVersion = (): void => {
  const { workspace, versionRef } = useSpace();
  const { pack, template, version } = versionRef;
  useEffect(() => {
    writeLastVersion(workspace.id, pack, template, version);
  }, [workspace.id, pack, template, version]);
};

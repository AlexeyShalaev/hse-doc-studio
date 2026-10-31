/** Адрес сокета комнаты файла: тот же origin, что у API, схема ws или wss. */
export const collabUrl = (
  apiBase: string,
  projectId: string,
  path: string,
  location: Pick<Location, "protocol" | "host"> = window.location,
): string => {
  const root =
    apiBase !== "" ? apiBase : `${location.protocol}//${location.host}`;
  const url = new URL(root);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `${url.pathname.replace(/\/$/, "")}/api/collab/v1/projects/${encodeURIComponent(projectId)}/room`;
  url.search = new URLSearchParams({ path }).toString();
  return url.toString();
};

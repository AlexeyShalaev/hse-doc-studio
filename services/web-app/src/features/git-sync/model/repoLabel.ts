// Короткое имя репозитория для заголовка панели: «владелец/репозиторий» без
// схемы, хоста и «.git»; для ссылок без пути (папка на диске) возвращает всё,
// что осталось от адреса.
export const repoLabel = (displayUrl: string): string => {
  const cleaned = displayUrl.replace(/\.git\/?$/i, "").replace(/\/+$/, "");
  try {
    const url = new URL(cleaned);
    const path = url.pathname.replace(/^\/+/, "");
    if (url.protocol === "file:") return decodeURIComponent(url.pathname);
    return path !== "" ? decodeURIComponent(path) : url.host;
  } catch {
    return cleaned;
  }
};

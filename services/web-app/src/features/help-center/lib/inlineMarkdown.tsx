import { Fragment, type ReactNode } from "react";

/**
 * Тот же минимум разметки, что у шагов на сайте справки: **жирный**, *курсив*, `код` и [ссылки](…).
 * Строит React-узлы, а не вставляет HTML: текст справки ничего не исполнит в приложении.
 * Ссылки на статьи (`/help/...`) открываются в новой вкладке, чтобы не уводить с экрана.
 */
const TOKEN = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

export const renderInline = (text: string): ReactNode[] =>
  text.split(TOKEN).map((part, index) => {
    const key = `${index}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={key}>{part.slice(1, -1)}</code>;
    }
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) {
      const href = link[2] ?? "";
      const safe = href.startsWith("/") || href.startsWith("https://");
      return safe ? (
        <a key={key} href={href} target="_blank" rel="noreferrer">
          {link[1]}
        </a>
      ) : (
        <Fragment key={key}>{link[1]}</Fragment>
      );
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    return <Fragment key={key}>{part}</Fragment>;
  });

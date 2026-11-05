import { useTranslation } from "react-i18next";
import { AlertTriangle, ChevronRight } from "lucide-react";
import { shortReason } from "@entities/compile";
import { getDocMeta } from "@entities/document";
import type { DocumentItem } from "./lib/buildDocSections";

/** Форма анкеты в объёме, нужном блоку «Сейчас». */
export type NowFormLike = {
  id: string;
  title: Record<string, string>;
  complete: boolean;
  required_for_pack: boolean;
};

export type NowBlockProps = {
  documents: DocumentItem[];
  forms: NowFormLike[];
  lang: "ru" | "en";
  onSelectDoc: (docId: string) => void;
  onOpenForm: (formId: string) => void;
};

// Больше трёх строк блок «Сейчас» превращается во второй список документов и
// перестаёт отвечать на свой единственный вопрос — «за что взяться прямо
// сейчас». Остальное всё равно видно ниже, в самом списке.
const MAX_ITEMS = 3;

type NowItem = {
  key: string;
  label: string;
  /** Причина под названием: почему упала сборка (первое предложение пояснения сервера). */
  reason?: string;
  /** Полный текст для подсказки. */
  full?: string;
  onOpen: () => void;
};

/**
 * «Сейчас» — короткий список того, что мешает сдать работу: упавшие сборки и
 * незаполненные обязательные анкеты. На чистом проекте не рендерится вовсе
 * (возвращает null), чтобы не превращаться в постоянный пустой заголовок.
 */
export const NowBlock = ({
  documents,
  forms,
  lang,
  onSelectDoc,
  onOpenForm,
}: NowBlockProps) => {
  const { t } = useTranslation("workbench");

  const items: NowItem[] = [];

  for (const doc of documents) {
    if (items.length >= MAX_ITEMS) break;
    const hasErrors = doc.status === "err" || (doc.errors ?? 0) > 0;
    if (!hasErrors) continue;
    const meta = getDocMeta(doc.id, doc, lang);
    const failure = doc.last_compile_error ?? null;
    items.push({
      key: `doc:${doc.id}`,
      label: t("now.buildError", { doc: meta.code }),
      ...(failure
        ? { reason: shortReason(failure.message), full: failure.message }
        : {}),
      onOpen: () => {
        onSelectDoc(doc.id);
      },
    });
  }

  for (const form of forms) {
    if (items.length >= MAX_ITEMS) break;
    if (!form.required_for_pack || form.complete) continue;
    const title = form.title[lang] ?? form.title.ru ?? form.title.en ?? form.id;
    items.push({
      key: `form:${form.id}`,
      label: t("now.formIncomplete", { form: title }),
      onOpen: () => {
        onOpenForm(form.id);
      },
    });
  }

  if (items.length === 0) return null;

  return (
    <div className="now-block">
      <span className="now-title">{t("now.title")}</span>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className="now-item"
          onClick={item.onOpen}
          // Панель узкая, и в командном проекте две одноимённые анкеты разных
          // авторов обрезаются в одинаковый текст. Полная строка — в подсказке.
          title={item.full ? `${item.label}: ${item.full}` : item.label}
          data-testid={
            item.key.startsWith("doc:") ? `now-${item.key}` : undefined
          }
        >
          <AlertTriangle
            size="0.6875rem"
            style={{ flexShrink: 0, color: "var(--c-warn)" }}
          />
          <span className="now-item-text">
            <span className="now-item-label">{item.label}</span>
            {item.reason && (
              <span
                data-testid="now-reason"
                style={{
                  fontSize: "0.65625rem",
                  color: "var(--fg-3)",
                  lineHeight: 1.35,
                  whiteSpace: "normal",
                  overflowWrap: "anywhere",
                }}
              >
                {item.reason}
              </span>
            )}
          </span>
          <ChevronRight
            size="0.6875rem"
            style={{ flexShrink: 0, color: "var(--fg-3)" }}
          />
        </button>
      ))}
    </div>
  );
};

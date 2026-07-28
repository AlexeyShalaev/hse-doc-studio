import { useTranslation } from "react-i18next";
import { AlertTriangle, ChevronRight } from "lucide-react";
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

type NowItem = { key: string; label: string; onOpen: () => void };

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
    items.push({
      key: `doc:${doc.id}`,
      label: t("now.buildError", { doc: meta.code }),
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
          title={item.label}
        >
          <AlertTriangle
            size={11}
            style={{ flexShrink: 0, color: "var(--c-warn)" }}
          />
          <span className="flex-1 truncate" style={{ textAlign: "left" }}>
            {item.label}
          </span>
          <ChevronRight
            size={11}
            style={{ flexShrink: 0, color: "var(--fg-3)" }}
          />
        </button>
      ))}
    </div>
  );
};

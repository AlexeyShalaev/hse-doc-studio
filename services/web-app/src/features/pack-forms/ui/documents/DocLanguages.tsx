import { AlertTriangle, Check, Languages, Split } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PackModelDocument } from "@entities/pack-studio";
import { Button } from "@shared/ui";
import { fileGroups, isSource, translatable } from "../../lib/documents";
import { langName } from "../../lib/langName";
import { useModelEditor } from "../../model/modelEditor";

/**
 * Таблица «файл, ru, en» папки документа по грамматике суффиксов (5.3):
 * файл для всех языков, редакции по языкам, смешение (ошибка линтера).
 * «Создать перевод» копирует редакцию языка по умолчанию в `<stem>.<код>.<ext>`.
 */
export const DocLanguages = ({
  doc,
  langs,
}: {
  doc: PackModelDocument;
  langs: string[];
}) => {
  const { t, i18n } = useTranslation("packForms");
  const { act, readOnly, busy } = useModelEditor();
  const groups = fileGroups(doc.files).filter((g) => isSource(g.bare));
  const defaultLang = langs[0] ?? "ru";
  const others = langs.slice(1);
  if (groups.length === 0) {
    return <p className="pf-empty">{t("languages.noSources")}</p>;
  }
  return (
    <div className="pf-langs" data-testid={`pf-langs-${doc.id}`}>
      <table className="pf-table">
        <thead>
          <tr>
            <th scope="col">{t("languages.file")}</th>
            {langs.map((lang) => (
              <th key={lang} scope="col" title={lang}>
                {langName(lang, i18n.language)}
              </th>
            ))}
            {!readOnly && (
              <th scope="col" aria-label={t("languages.actions")} />
            )}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const shared = "" in group.byLang;
            const mixed = shared && langs.some((l) => l in group.byLang);
            return (
              <tr key={group.bare}>
                <td className="mono pf-file">
                  {group.bare.split("/").slice(1).join("/") || group.bare}
                  {mixed && (
                    <span className="pf-warn" title={t("languages.mixed")}>
                      <AlertTriangle
                        size="0.75rem"
                        aria-label={t("languages.mixed")}
                      />
                    </span>
                  )}
                </td>
                {shared && !mixed ? (
                  <td colSpan={langs.length} className="pf-shared">
                    {t("languages.shared")}
                  </td>
                ) : (
                  langs.map((lang) => (
                    <td key={lang}>
                      {lang in group.byLang ? (
                        <Check
                          size="0.75rem"
                          aria-label={t("languages.present")}
                        />
                      ) : (
                        <span className="pf-missing-lang">
                          {t("languages.missing")}
                        </span>
                      )}
                    </td>
                  ))
                )}
                {!readOnly && (
                  <td>
                    {shared && !mixed && others.length > 0 && (
                      <Button
                        size="xs"
                        variant="ghost"
                        disabled={busy}
                        title={t("languages.splitHint", {
                          lang: langName(defaultLang, i18n.language),
                        })}
                        data-testid={`pf-split-${group.bare}`}
                        onClick={() => {
                          void act({
                            action: "add_translation",
                            document: doc.id,
                            lang: others[0] ?? "",
                            files: [group.bare],
                          });
                        }}
                      >
                        <Split size="0.6875rem" />
                        {t("languages.split")}
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {!readOnly && (
        <div className="pf-card-actions">
          {others.map((lang) => (
            <Button
              key={lang}
              size="xs"
              variant="secondary"
              disabled={busy || !translatable(doc, lang, defaultLang)}
              title={
                translatable(doc, lang, defaultLang)
                  ? t("languages.translateHint", {
                      from: langName(defaultLang, i18n.language),
                      lang: langName(lang, i18n.language),
                    })
                  : t("languages.translateNone", {
                      lang: langName(lang, i18n.language),
                    })
              }
              data-testid={`pf-translate-${doc.id}-${lang}`}
              onClick={() => {
                void act({ action: "add_translation", document: doc.id, lang });
              }}
            >
              <Languages size="0.6875rem" />
              {t("languages.translate", {
                lang: langName(lang, i18n.language),
              })}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
};

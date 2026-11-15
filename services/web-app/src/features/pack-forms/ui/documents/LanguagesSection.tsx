import { useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button } from "@shared/ui";
import { LANG_CODE, isBundle, versionLangs } from "../../lib/documents";
import { asRecord, has, pickLocalized, setOp } from "../../lib/raw";
import { useModelEditor } from "../../model/modelEditor";
import { FormBlock, OrderButtons } from "../kit";
import { DocLanguages } from "./DocLanguages";

const useLang = () => {
  const { i18n } = useTranslation();
  return i18n.language.startsWith("en") ? "en" : "ru";
};

/**
 * Языки версии (`langs`, первый по умолчанию) и файлы документов по языкам
 * с «Создать перевод» (5.3; T12).
 */
export const LanguagesSection = () => {
  const { t } = useTranslation("packForms");
  const { model, edit, readOnly, busy } = useModelEditor();
  const lang = useLang();
  const data = asRecord(model.manifest.data);
  const declared = has(data, "langs");
  const langs = versionLangs(data);
  const [draft, setDraft] = useState("");
  const code = draft.trim().toLowerCase();
  const valid = LANG_CODE.test(code) && !langs.includes(code);
  const write = (next: string[]) => {
    void edit("version.yaml", [setOp(["langs"], next)]);
  };
  // Удалить язык можно, только если ни один документ не держит файлов с его кодом.
  const used = (code: string) =>
    model.documents.some((d) => d.files.some((f) => f.lang === code));

  return (
    <div className="pf-section" data-testid="pf-languages">
      <FormBlock title={t("languages.title")} lead={t("languages.lead")}>
        {!declared && <p className="pf-hint">{t("languages.undeclared")}</p>}
        <ol className="pf-list compact">
          {langs.map((code, i) => (
            <li key={code} className="pf-item" data-testid={`pf-lang-${code}`}>
              <div className="pf-item-head">
                <span className="mono pf-id">{code}</span>
                <span className="pf-item-sub">
                  {i === 0 && (
                    <Badge variant="info">{t("languages.default")}</Badge>
                  )}
                </span>
                {!readOnly && (
                  <OrderButtons
                    index={i}
                    count={langs.length}
                    label={code}
                    disabled={busy}
                    onMove={(to) => {
                      const next = [...langs];
                      next.splice(i, 1);
                      next.splice(to, 0, code);
                      write(next);
                    }}
                    deleteDisabledReason={
                      langs.length === 1
                        ? t("languages.lastOne")
                        : used(code)
                          ? t("languages.inUse")
                          : undefined
                    }
                    onDelete={() => {
                      write(langs.filter((c) => c !== code));
                    }}
                  />
                )}
              </div>
            </li>
          ))}
        </ol>
        {!readOnly && (
          <div className="pf-inline-add">
            <input
              className="input pf-input mono"
              value={draft}
              placeholder={t("languages.newCode")}
              aria-label={t("languages.newCode")}
              data-testid="pf-lang-new"
              onChange={(e) => {
                setDraft(e.target.value);
              }}
            />
            <Button
              size="xs"
              variant="secondary"
              disabled={!valid || busy}
              data-testid="pf-lang-add"
              onClick={() => {
                write([...langs, code]);
                setDraft("");
              }}
            >
              <Plus size="0.6875rem" />
              {t("languages.add")}
            </Button>
          </div>
        )}
      </FormBlock>
      <FormBlock
        title={t("languages.filesTitle")}
        lead={t("languages.filesLead")}
      >
        {model.documents.filter(isBundle).map((doc) => (
          <section key={doc.id} className="pf-item">
            <div className="pf-item-head">
              <span className="mono pf-id">{doc.id}</span>
              <span className="pf-item-label truncate">
                {pickLocalized(asRecord(doc.data).name, lang, "")}
              </span>
            </div>
            <DocLanguages doc={doc} langs={langs} />
          </section>
        ))}
      </FormBlock>
    </div>
  );
};

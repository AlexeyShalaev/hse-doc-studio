import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Section, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useMailPreview } from "../api/adminSettingsQueries";

const LANGS = ["ru", "en"] as const;
type Lang = (typeof LANGS)[number];

/** Один образец письма: тема, письмо глазами клиента (iframe без скриптов) и его текстовая часть. */
export const MailPreviewSection = () => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const [template, setTemplate] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>("ru");
  const [showText, setShowText] = useState(false);
  const preview = useMailPreview(template, lang);
  const data = preview.data;
  const current = template ?? data?.template ?? "";

  return (
    <Section
      id="admin-mail-preview"
      testId="admin-mail-preview"
      title={t("mailPreview.title")}
      description={t("mailPreview.sub")}
    >
      <div className="adm-setting-extra">
        <div
          className="adm-fields-row"
          style={{ alignItems: "center", flexWrap: "wrap" }}
        >
          <div style={{ minWidth: "16.25rem", flex: 1 }}>
            <Select
              id={`${uid}-template`}
              ariaLabel={t("mailPreview.template")}
              value={current}
              isDisabled={!data}
              onValueChange={setTemplate}
              options={(data?.templates ?? []).map((id) => ({
                value: id,
                label: t(`mailPreview.names.${id}`, { defaultValue: id }),
              }))}
            />
          </div>
          <div style={{ width: "6rem" }}>
            <Select
              id={`${uid}-lang`}
              ariaLabel={t("mailPreview.language")}
              value={lang}
              onValueChange={(value) => {
                setLang(value as Lang);
              }}
              options={LANGS.map((id) => ({
                value: id,
                label: id.toUpperCase(),
              }))}
            />
          </div>
          {preview.isFetching && <Spinner size="sm" />}
        </div>
        {preview.isError && (
          <Notice tone="err" role="alert" text={t("mailPreview.failed")} />
        )}
        {data && (
          <>
            <p className="adm-field-note" data-testid="mail-preview-subject">
              <strong>{t("mailPreview.subject")}:</strong> {data.subject}
            </p>
            <iframe
              title={t("mailPreview.frame")}
              data-testid="mail-preview-frame"
              // Без allow-scripts и allow-same-origin: письмо не может ни выполнить код, ни дотянуться до страницы.
              sandbox=""
              srcDoc={data.html}
              style={{
                width: "100%",
                height: "40rem",
                border: "1px solid var(--border)",
                borderRadius: "0.5rem",
                background: "#fff",
              }}
            />
            <button
              type="button"
              className="adm-field-note"
              aria-expanded={showText}
              onClick={() => {
                setShowText((v) => !v);
              }}
              style={{ background: "none", border: 0, padding: 0 }}
            >
              {showText ? t("mailPreview.hideText") : t("mailPreview.showText")}
            </button>
            {showText && (
              <pre
                className="mono"
                data-testid="mail-preview-text"
                style={{
                  margin: 0,
                  padding: "0.75rem",
                  fontSize: "0.75rem",
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  border: "1px solid var(--border)",
                  borderRadius: "0.5rem",
                }}
              >
                {data.text}
              </pre>
            )}
          </>
        )}
      </div>
    </Section>
  );
};

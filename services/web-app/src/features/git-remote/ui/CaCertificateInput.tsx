import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileDropZone } from "@shared/ui/FileDropZone";
import { Textarea } from "@shared/ui/Textarea";
import { pemCount, pemProblem, readFileText } from "../lib/pem";

export type CaCertificateInputProps = {
  value: string;
  onChange: (value: string) => void;
  /** Файл не удалось прочитать. */
  onReadError: () => void;
  idPrefix?: string;
};

// Сертификат центра выдачи: файл (.pem, .crt, .cer) или текст. Закрытый ключ
// отсекается сразу: ему здесь не место.
export const CaCertificateInput = ({
  value,
  onChange,
  onReadError,
  idPrefix = "ca",
}: CaCertificateInputProps) => {
  const { t } = useTranslation("gitAccess");
  const [fileName, setFileName] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const problem = pemProblem(value);
  const message =
    problem && problem !== "empty" && (touched || problem === "private_key")
      ? t(`tls.ca.problem.${problem}`)
      : null;

  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      <FileDropZone
        accept=".pem,.crt,.cer"
        title={t("tls.ca.drop.title")}
        action={t("tls.ca.drop.action")}
        activeTitle={t("tls.ca.drop.active")}
        inputLabel={t("tls.ca.drop.input")}
        testId={`${idPrefix}-drop`}
        inputTestId={`${idPrefix}-file`}
        onFile={(file) => {
          setTouched(true);
          setFileName(file.name);
          void readFileText(file).then(onChange).catch(onReadError);
        }}
      />
      {fileName && (
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("tls.ca.fromFile", { name: fileName })}
        </span>
      )}
      <Textarea
        label={t("tls.ca.paste")}
        value={value}
        isMono
        rows={6}
        spellCheck={false}
        autoComplete="off"
        placeholder="-----BEGIN CERTIFICATE-----"
        data-testid={`${idPrefix}-text`}
        onChange={(event) => {
          onChange(event.target.value);
          setFileName(null);
        }}
        onBlur={() => {
          setTouched(true);
        }}
        {...(message ? { error: message } : {})}
      />
      {problem === null && (
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t("tls.ca.count", { count: pemCount(value) })}
        </span>
      )}
    </div>
  );
};

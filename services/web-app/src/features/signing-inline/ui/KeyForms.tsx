import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input } from "@shared/ui";
import type { KeyCreateInput, KeyImportInput } from "../model/useInline";
import { FilePick } from "./FilePick";

type FormProps<T> = {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (input: T) => void;
};

const Footer = ({
  busy,
  ready,
  submit,
  onCancel,
}: {
  busy: boolean;
  ready: boolean;
  submit: string;
  onCancel: () => void;
}) => {
  const { t } = useTranslation("signing");
  return (
    <div className="sgi-row sgi-end">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled={busy}
        onClick={onCancel}
      >
        {t("key.cancel")}
      </Button>
      <Button
        type="submit"
        size="sm"
        disabled={busy || !ready}
        data-testid="signing-key-submit"
      >
        {busy ? t("actions.working") : submit}
      </Button>
    </div>
  );
};

/** Новый ключ OpenPGP прямо на странице: имя для плашки и пароль по желанию. */
export const KeyCreateForm = ({
  busy,
  defaultName,
  onCancel,
  onSubmit,
}: FormProps<KeyCreateInput> & { defaultName: string }) => {
  const { t } = useTranslation("signing");
  const [name, setName] = useState(defaultName);
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  return (
    <form
      className="sgi-form"
      data-testid="signing-key-create"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() !== "") onSubmit({ name, email, passphrase });
      }}
    >
      <Input
        id="signing-key-name"
        label={t("key.name")}
        value={name}
        required
        autoComplete="name"
        onChange={(event) => {
          setName(event.target.value);
        }}
      />
      <Input
        id="signing-key-email"
        label={t("key.email")}
        type="email"
        value={email}
        autoComplete="email"
        onChange={(event) => {
          setEmail(event.target.value);
        }}
      />
      <Input
        id="signing-key-passphrase"
        label={t("key.passphrase")}
        type="password"
        value={passphrase}
        autoComplete="new-password"
        hint={t("key.passphraseHint")}
        data-testid="signing-key-passphrase"
        onChange={(event) => {
          setPassphrase(event.target.value);
        }}
      />
      <Footer
        busy={busy}
        ready={name.trim() !== ""}
        submit={t("key.create")}
        onCancel={onCancel}
      />
    </form>
  );
};

/** Свой ключ файлом: OpenPGP (.asc, .gpg) или контейнер .p12 / .pfx. */
export const KeyImportForm = ({
  busy,
  onCancel,
  onSubmit,
}: FormProps<KeyImportInput>) => {
  const { t } = useTranslation("signing");
  const [file, setFile] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");
  return (
    <form
      className="sgi-form"
      data-testid="signing-key-import"
      onSubmit={(event) => {
        event.preventDefault();
        if (file) onSubmit({ file, passphrase });
      }}
    >
      <div className="sgi-row">
        <FilePick
          accept=".asc,.gpg,.pgp,.key,.p12,.pfx"
          disabled={busy}
          testId="signing-key-file"
          onFile={setFile}
        >
          {t("key.choose")}
        </FilePick>
        <span className="sgi-file-name">
          {file ? file.name : t("key.file")}
        </span>
      </div>
      <Input
        id="signing-key-file-pass"
        label={t("key.filePass")}
        type="password"
        value={passphrase}
        autoComplete="off"
        onChange={(event) => {
          setPassphrase(event.target.value);
        }}
      />
      <Footer
        busy={busy}
        ready={file !== null}
        submit={t("key.import")}
        onCancel={onCancel}
      />
    </form>
  );
};

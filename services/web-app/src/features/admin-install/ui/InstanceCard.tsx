import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  AdminInstanceSettings,
  UpdateAdminInstanceRequest,
} from "@entities/session";
import type { Failure } from "../lib/failure";
import { isLocked } from "../lib/locked";
import { HINT } from "../lib/styles";
import {
  isInsecureUrl,
  validateInstance,
  type InstanceDraft,
} from "../lib/validate";
import { LockedBadge, SettingsCard } from "./parts";
import { SaveRow } from "./SaveRow";

export type InstanceCardProps = {
  settings: AdminInstanceSettings;
  pending?: boolean;
  failure?: Failure | null;
  saved?: boolean;
  onSave: (patch: UpdateAdminInstanceRequest) => void;
};

const KEYS = ["name", "public_url", "docs_url"] as const;

const draftOf = (s: AdminInstanceSettings): InstanceDraft => ({
  name: s.name,
  public_url: s.public_url,
  docs_url: s.docs_url ?? "",
});

/** Название установки, публичный адрес и ссылка на документацию. */
export const InstanceCard = ({
  settings,
  pending = false,
  failure = null,
  saved = false,
  onSave,
}: InstanceCardProps) => {
  const { t } = useTranslation("adminInstall");
  const uid = useId();
  const [draft, setDraft] = useState<InstanceDraft>(draftOf(settings));
  const [touched, setTouched] = useState(false);
  const lock = (key: (typeof KEYS)[number]) =>
    isLocked(settings.fields, `instance.${key}`);
  const base = draftOf(settings);
  const changed = (key: (typeof KEYS)[number]) =>
    !lock(key) && draft[key] !== base[key];
  const dirty = KEYS.some(changed);
  const issues = validateInstance(draft);
  const relevant = KEYS.filter((k) => !lock(k) && issues[k]);

  const shown = (key: (typeof KEYS)[number]): { error?: string } => {
    const code = touched && !lock(key) ? issues[key] : undefined;
    return code ? { error: t(`instance.issue.${code}`) } : {};
  };

  const field = (
    key: (typeof KEYS)[number],
    label: string,
    hint: string,
    extra: Partial<React.ComponentProps<typeof Input>> = {},
  ) => (
    <div className="flex flex-col" style={{ gap: 6, minWidth: 0 }}>
      <Input
        id={`${uid}-${key}`}
        label={label}
        value={draft[key]}
        readOnly={lock(key)}
        hint={hint}
        onChange={(e) => {
          setDraft((d) => ({ ...d, [key]: e.target.value }));
        }}
        {...shown(key)}
        {...extra}
      />
      {lock(key) && <LockedBadge testId={`locked-instance-${key}`} />}
    </div>
  );

  return (
    <SettingsCard
      id="admin-instance"
      testId="admin-instance"
      title={t("instance.title")}
      sub={t("instance.sub")}
    >
      <form
        noValidate
        className="flex flex-col"
        style={{ gap: 14 }}
        data-testid="instance-form"
        onSubmit={(e) => {
          e.preventDefault();
          setTouched(true);
          if (!dirty || relevant.length > 0 || pending) return;
          onSave({
            name: changed("name") ? draft.name.trim() : null,
            public_url: changed("public_url") ? draft.public_url.trim() : null,
            docs_url: changed("docs_url") ? draft.docs_url.trim() : null,
          });
        }}
      >
        {field("name", t("instance.name"), t("instance.nameHint"), {
          maxLength: 120,
        })}
        {field(
          "public_url",
          t("instance.publicUrl"),
          t("instance.publicUrlHint"),
          {
            placeholder: "https://studio.example.org",
            isMono: true,
            inputMode: "url",
          },
        )}
        {changed("public_url") &&
          !shown("public_url").error &&
          isInsecureUrl(draft.public_url) && (
            <Notice tone="warn" text={t("instance.insecure")} />
          )}
        {changed("public_url") && !issues.public_url && (
          <p style={HINT} data-testid="instance-url-impact">
            {t("instance.urlImpact")}
          </p>
        )}
        {field("docs_url", t("instance.docsUrl"), t("instance.docsUrlHint"), {
          placeholder: "https://docs.example.org",
          isMono: true,
          inputMode: "url",
        })}
        <SaveRow
          testId="instance"
          dirty={dirty}
          pending={pending}
          failure={failure}
          saved={saved}
          allLocked={KEYS.every(lock)}
        />
      </form>
    </SettingsCard>
  );
};

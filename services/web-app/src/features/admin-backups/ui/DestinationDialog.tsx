import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Modal, SettingRow, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import { backupsApi } from "../api/backupsApi";
import type { BackupDestination, CheckResult } from "../api/schemas";
import {
  OWN_S3_HINT,
  bodyFromDraft,
  draftOf,
  draftProblem,
  emptyDraft,
  withOwnS3,
  type DestinationDraft,
  type DraftField,
} from "../lib/destinationDraft";
import { failureKey, failureOf, type BackupFailure } from "../lib/failure";

const SERVER_FIELD: Record<string, DraftField> = {
  name: "name",
  endpoint: "endpoint",
  bucket: "bucket",
  prefix: "prefix",
  local_path: "localPath",
  access_key: "accessKey",
  secret_key: "secretKey",
};

/** Подсказка «как подключить своё S3»: готовые значения оверлея compose.backup-s3.yml. */
const OwnS3Hint = ({ onFill }: { onFill: () => void }) => {
  const { t } = useTranslation("adminBackups");
  const rows: [string, string][] = [
    [t("dialog.fields.endpoint"), OWN_S3_HINT.endpoint],
    [t("dialog.fields.region"), OWN_S3_HINT.region],
    [t("dialog.fields.bucket"), OWN_S3_HINT.bucket],
    [t("dialog.fields.pathStyle"), t("dialog.hint.on")],
  ];
  return (
    <details className="ops-hint" data-testid="backup-own-s3-hint">
      <summary>{t("dialog.hint.title")}</summary>
      <p className="form-hint">{t("dialog.hint.body")}</p>
      <pre className="form-hint" style={{ margin: 0 }}>
        docker compose -f docker-compose.yml -f compose.backup-s3.yml up -d
      </pre>
      <dl className="ops-facts">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <code>{value}</code>
            </dd>
          </div>
        ))}
        <div>
          <dt>{t("dialog.hint.keys")}</dt>
          <dd>
            <code>BACKUP_S3_ACCESS_KEY</code>, <code>BACKUP_S3_SECRET_KEY</code>
          </dd>
        </div>
      </dl>
      <p className="form-hint">{t("dialog.hint.separate")}</p>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={onFill}
        data-testid="backup-hint-fill"
      >
        {t("dialog.hint.fill")}
      </Button>
    </details>
  );
};

export type DestinationDialogProps = {
  /** null: новое назначение. */
  destination: BackupDestination | null;
  first: boolean;
  localRoot: string;
  saving: boolean;
  failure: BackupFailure | null;
  onSave: (draft: DestinationDraft) => void;
  onClose: () => void;
};

export const DestinationDialog = ({
  destination,
  first,
  localRoot,
  saving,
  failure,
  onSave,
  onClose,
}: DestinationDialogProps) => {
  const { t } = useTranslation("adminBackups");
  const editing = destination !== null;
  const [draft, setDraft] = useState<DestinationDraft>(
    destination ? draftOf(destination) : emptyDraft(first),
  );
  const [tried, setTried] = useState(false);
  const [check, setCheck] = useState<CheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkFailure, setCheckFailure] = useState<BackupFailure | null>(null);
  const problem = draftProblem(draft, editing);
  const serverField = failure?.field ? SERVER_FIELD[failure.field] : undefined;
  const invalid = (field: DraftField): boolean =>
    (tried && problem === field) || serverField === field;

  const set = (patch: Partial<DestinationDraft>) => {
    setDraft({ ...draft, ...patch });
    setCheck(null);
  };

  const runCheck = () => {
    setTried(true);
    if (problem !== null) return;
    setChecking(true);
    setCheckFailure(null);
    backupsApi
      .testForm(bodyFromDraft(draft), destination?.id ?? null)
      .then(setCheck)
      .catch((error: unknown) => {
        setCheckFailure(failureOf(error));
      })
      .finally(() => {
        setChecking(false);
      });
  };

  const field = (
    key: DraftField,
    label: string,
    node: ReactNode,
    hint?: string,
  ) => (
    <SettingRow
      label={label}
      hint={invalid(key) ? t(`dialog.invalid.${key}`) : hint}
      htmlFor={`bk-${key}`}
      layout="stacked"
    >
      {node}
    </SettingRow>
  );

  return (
    <Modal
      isOpen
      onClose={() => {
        if (!saving) onClose();
      }}
      title={editing ? t("dialog.editTitle") : t("dialog.createTitle")}
      width={620}
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={saving}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={runCheck}
            disabled={saving || checking}
            data-testid="backup-dest-check"
          >
            {checking && <Spinner size="sm" />}
            {t("dialog.check")}
          </Button>
          <button
            type="button"
            className="btn primary"
            disabled={saving}
            data-testid="backup-dest-save"
            onClick={() => {
              setTried(true);
              if (problem === null) onSave(draft);
            }}
          >
            {saving && <Spinner size="sm" />}
            {t("dialog.save")}
          </button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.625rem" }}
        data-testid="backup-dest-dialog"
      >
        {field(
          "name",
          t("dialog.fields.name"),
          <Input
            id="bk-name"
            value={draft.name}
            onChange={(e) => {
              set({ name: e.target.value });
            }}
            data-testid="backup-dest-name"
          />,
        )}
        <SettingRow
          label={t("dialog.fields.kind")}
          htmlFor="bk-kind"
          layout="stacked"
        >
          <div
            className="flex"
            style={{ gap: "0.5rem" }}
            role="radiogroup"
            aria-label={t("dialog.fields.kind")}
          >
            {(["s3", "local"] as const).map((kind) => (
              <button
                key={kind}
                type="button"
                role="radio"
                aria-checked={draft.kind === kind}
                className={draft.kind === kind ? "btn primary" : "btn"}
                disabled={editing}
                onClick={() => {
                  set({ kind });
                }}
                data-testid={`backup-kind-${kind}`}
              >
                {t(`kind.${kind}`)}
              </button>
            ))}
          </div>
        </SettingRow>
        {draft.kind === "s3" ? (
          <>
            {!editing && (
              <OwnS3Hint
                onFill={() => {
                  setDraft(withOwnS3(draft));
                }}
              />
            )}
            {field(
              "endpoint",
              t("dialog.fields.endpoint"),
              <Input
                id="bk-endpoint"
                value={draft.endpoint}
                placeholder="https://s3.example.org"
                onChange={(e) => {
                  set({ endpoint: e.target.value });
                }}
                data-testid="backup-dest-endpoint"
              />,
              t("dialog.hint.endpoint"),
            )}
            <SettingRow
              label={t("dialog.fields.region")}
              htmlFor="bk-region"
              layout="stacked"
            >
              <Input
                id="bk-region"
                value={draft.region}
                onChange={(e) => {
                  set({ region: e.target.value });
                }}
              />
            </SettingRow>
            {field(
              "bucket",
              t("dialog.fields.bucket"),
              <Input
                id="bk-bucket"
                value={draft.bucket}
                onChange={(e) => {
                  set({ bucket: e.target.value });
                }}
                data-testid="backup-dest-bucket"
              />,
            )}
            {field(
              "prefix",
              t("dialog.fields.prefix"),
              <Input
                id="bk-prefix"
                value={draft.prefix}
                placeholder="studio"
                onChange={(e) => {
                  set({ prefix: e.target.value });
                }}
              />,
              t("dialog.hint.prefix"),
            )}
            <SettingRow
              label={t("dialog.fields.pathStyle")}
              hint={t("dialog.hint.pathStyle")}
              htmlFor="bk-pathStyle"
            >
              <Switch
                id="bk-pathStyle"
                checked={draft.pathStyle}
                onChange={(pathStyle) => {
                  set({ pathStyle });
                }}
              />
            </SettingRow>
            {field(
              "accessKey",
              t("dialog.fields.accessKey"),
              <Input
                id="bk-accessKey"
                autoComplete="off"
                value={draft.accessKey}
                placeholder={destination?.access_key_hint ?? ""}
                onChange={(e) => {
                  set({ accessKey: e.target.value });
                }}
                data-testid="backup-dest-access"
              />,
              editing ? t("dialog.hint.keepKey") : undefined,
            )}
            {field(
              "secretKey",
              t("dialog.fields.secretKey"),
              <Input
                id="bk-secretKey"
                type="password"
                autoComplete="new-password"
                value={draft.secretKey}
                placeholder={destination?.secret_key_set ? "••••••••" : ""}
                onChange={(e) => {
                  set({ secretKey: e.target.value });
                }}
                data-testid="backup-dest-secret"
              />,
              editing ? t("dialog.hint.keepKey") : t("dialog.hint.encrypted"),
            )}
          </>
        ) : (
          <>
            {field(
              "localPath",
              t("dialog.fields.localPath"),
              <Input
                id="bk-localPath"
                value={draft.localPath}
                placeholder="disk1"
                onChange={(e) => {
                  set({ localPath: e.target.value });
                }}
                data-testid="backup-dest-local"
              />,
              t("dialog.hint.localPath", { root: localRoot }),
            )}
            <Notice tone="warn" text={t("dialog.hint.localSame")} />
          </>
        )}
        <SettingRow
          label={t("dialog.fields.makeDefault")}
          hint={t("dialog.hint.makeDefault")}
          htmlFor="bk-makeDefault"
        >
          <Switch
            id="bk-makeDefault"
            checked={draft.makeDefault}
            disabled={destination?.is_default === true}
            onChange={(makeDefault) => {
              set({ makeDefault });
            }}
          />
        </SettingRow>
        {check && (
          <div data-testid="backup-dest-check-result" data-ok={check.ok}>
            <Notice
              tone={check.ok ? "info" : "err"}
              role={check.ok ? "status" : "alert"}
              text={
                check.ok
                  ? t("dialog.checkOk")
                  : t("dialog.checkFailed", { error: check.error ?? "" })
              }
            />
            {check.warnings.map((w) => (
              <Notice
                key={w}
                tone="warn"
                text={t(`warnings.${w}`, { defaultValue: w })}
              />
            ))}
          </div>
        )}
        {checkFailure && (
          <Notice
            tone="err"
            role="alert"
            text={t(failureKey(checkFailure.code))}
          />
        )}
        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
      </div>
    </Modal>
  );
};

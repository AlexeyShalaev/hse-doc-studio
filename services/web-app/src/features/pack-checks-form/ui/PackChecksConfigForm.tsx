import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackChecks,
  usePatchPackChecks,
  versionRefOf,
  type PackChecks,
  type PackChecksConfigRequest,
} from "@entities/pack-studio";
import { BlockHead, Check } from "@features/pack-submission-form/ui/kit";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { ErrorState, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { categoriesOf } from "../lib/params";
import "./checksForm.css";

export type PackChecksConfigFormProps = {
  workspaceId: string;
  /** `version.yaml` версии. */
  path: string;
  onSaved: (path: string) => void;
};

const DEFAULT = "default";
const OVERRIDES = ["info", "warn", "err", "skipped"] as const;

const configOf = (data: PackChecks): Required<PackChecksConfigRequest> => ({
  disabled_categories: [...data.config.disabled_categories],
  disabled: [...data.config.disabled],
  severity_override: Object.fromEntries(
    Object.entries(data.config.severity_override).filter(
      (entry): entry is [string, (typeof OVERRIDES)[number]] =>
        (OVERRIDES as readonly string[]).includes(entry[1]),
    ),
  ),
});

const toggled = (list: readonly string[], value: string, on: boolean) =>
  on ? [...new Set([...list, value])] : list.filter((v) => v !== value);

/**
 * `checks_version` версии формой (5.7): выключенные категории и правила, переопределение важности.
 * Каждая правка сразу пишется в `version.yaml` с `If-Match`.
 */
export const PackChecksConfigForm = ({
  workspaceId,
  path,
  onSaved,
}: PackChecksConfigFormProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const versionRef = useMemo(() => versionRefOf(path), [path]);
  const ref = versionRef ?? { pack: "", template: "", version: "" };
  const query = usePackChecks(workspaceId, versionRef);
  const patch = usePatchPackChecks(workspaceId, ref);
  const [error, setError] = useState<unknown>(null);

  if (versionRef === null) return null;
  if (query.isPending) {
    return (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner size="md" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <ErrorState
        description={packErrorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const data = query.data;
  const config = configOf(data);
  const disabled = data.config.read_only !== null || patch.isPending;
  const save = (next: Required<PackChecksConfigRequest>) => {
    patch.mutate(
      { kind: "config", body: next, etag: data.config.etag },
      {
        onSuccess: (result) => {
          setError(null);
          onSaved(result.config.path);
        },
        onError: (e) => {
          setError(e);
          if (e instanceof ApiError && e.code === "stale_file") {
            void query.refetch();
          }
        },
      },
    );
  };
  const categories = [
    ...new Set([...categoriesOf(data), ...config.disabled_categories]),
  ];
  const known = new Set(
    data.files.flatMap((f) => f.rules.flatMap((r) => (r.entry ? [r.entry.id] : []))),
  );
  const orphans = [
    ...config.disabled,
    ...Object.keys(config.severity_override),
  ].filter((id) => !known.has(id));

  return (
    <div className="psf-form pcf-form" data-testid="checks-config-form">
      {data.config.read_only !== null && (
        <Notice
          tone="info"
          role="status"
          text={
            data.config.read_only === "version_released"
              ? t("editor.readOnlyReleased")
              : t("editor.readOnlyRegistry")
          }
        />
      )}
      {error !== null && (
        <Notice tone="err" role="alert" text={packErrorText(error)} />
      )}
      <p className="hint">{t("checksForm.config.lead")}</p>
      <section className="psf-block" data-testid="checks-config-categories">
        <BlockHead
          title={t("checksForm.config.categories")}
          hint={t("checksForm.config.categoriesHint")}
          actions={patch.isPending ? <Spinner size="sm" /> : undefined}
        />
        {categories.length === 0 && (
          <p className="psf-muted">{t("checksForm.config.noCategories")}</p>
        )}
        <div className="pcf-categories">
          {categories.map((category) => (
            <Check
              key={category}
              label={t(`checksForm.category.${category}`, {
                defaultValue: category,
              })}
              checked={config.disabled_categories.includes(category)}
              disabled={disabled}
              onChange={(on) => {
                save({
                  ...config,
                  disabled_categories: toggled(
                    config.disabled_categories,
                    category,
                    on,
                  ),
                });
              }}
              testId={`category-${category}`}
            />
          ))}
        </div>
      </section>
      {data.files.map((file) => (
        <section className="psf-block" key={file.name}>
          <BlockHead
            title={pickLocalized(file.header.label, i18n.language, file.name)}
            hint={file.name}
          />
          <ul className="pcf-config-rules">
            {file.rules.flatMap((r) => {
              const rule = r.entry;
              if (!rule) return [];
              const override = config.severity_override[rule.id];
              return [
                <li key={rule.id} className="pcf-config-rule">
                  <span className="pcf-config-name">
                    {pickLocalized(rule.title, i18n.language, rule.id)}
                    <code className="mono pcf-id">{rule.id}</code>
                  </span>
                  <Check
                    label={t("checksForm.config.off")}
                    checked={config.disabled.includes(rule.id)}
                    disabled={disabled}
                    onChange={(on) => {
                      save({
                        ...config,
                        disabled: toggled(config.disabled, rule.id, on),
                      });
                    }}
                    testId={`disable-${rule.id}`}
                  />
                  <Select
                    value={override ?? DEFAULT}
                    onValueChange={(value) => {
                      const rest = Object.fromEntries(
                        Object.entries(config.severity_override).filter(
                          ([id]) => id !== rule.id,
                        ),
                      );
                      save({
                        ...config,
                        severity_override:
                          value === DEFAULT
                            ? rest
                            : {
                                ...rest,
                                [rule.id]: value as (typeof OVERRIDES)[number],
                              },
                      });
                    }}
                    isDisabled={disabled}
                    ariaLabel={t("checksForm.config.severity")}
                    options={[
                      {
                        value: DEFAULT,
                        label: t("checksForm.config.asRule", {
                          severity: t(
                            `checksForm.severity.${rule.default_severity}`,
                          ),
                        }),
                      },
                      ...OVERRIDES.map((s) => ({
                        value: s,
                        label: t(`checksForm.severity.${s}`),
                      })),
                    ]}
                  />
                </li>,
              ];
            })}
          </ul>
        </section>
      ))}
      {orphans.length > 0 && (
        <p className="hint pcf-warn">
          {t("checksForm.config.orphans", { ids: orphans.join(", ") })}
        </p>
      )}
    </div>
  );
};

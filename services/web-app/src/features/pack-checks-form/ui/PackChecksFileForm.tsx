import { useCallback, useMemo, useState } from "react";
import { Plus, Save, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackChecksForm,
  usePackPreviewOptions,
  usePatchPackChecksForm,
  versionRefOf,
  type PackChecksFile,
  type PackChecksHeader,
  type PackChecksOp,
  type PackPreviewBuild,
} from "@entities/pack-studio";
import {
  BlockHead,
  LocalizedFields,
} from "@features/pack-submission-form/ui/kit";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { Button, ErrorState, Input, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { categoriesOf, findingsByRule } from "../lib/params";
import { CheckOnPreview } from "./CheckOnPreview";
import { RuleCard, type RuleCtx } from "./RuleCard";
import "./checksForm.css";

export type PackChecksFileFormProps = {
  workspaceId: string;
  /** Файл правил `.../versions/<v>/checks/<имя>.yaml`. */
  path: string;
  onSaved: (path: string) => void;
};

const reasonOf = (error: unknown): string | null =>
  error instanceof ApiError && typeof error.data?.reason === "string"
    ? error.data.reason
    : null;

const HeaderEditor = ({
  file,
  disabled,
  apply,
}: {
  file: PackChecksFile;
  disabled: boolean;
  apply: (ops: PackChecksOp[]) => void;
}) => {
  const { t } = useTranslation("packStudio");
  const [draft, setDraft] = useState<PackChecksHeader>(file.header);
  const [seen, setSeen] = useState(file.header);
  if (seen !== file.header) {
    setSeen(file.header);
    setDraft(file.header);
  }
  const dirty = JSON.stringify(draft) !== JSON.stringify(file.header);
  return (
    <section className="psf-block" data-testid="checks-header">
      <BlockHead
        title={t("checksForm.header.title")}
        hint={t("checksForm.header.hint")}
      />
      <LocalizedFields
        label={t("checksForm.header.label")}
        value={draft.label}
        disabled={disabled}
        onChange={(label) => {
          setDraft({ ...draft, label });
        }}
        testId="checks-header-label"
      />
      <LocalizedFields
        label={t("checksForm.header.ref")}
        value={draft.ref}
        disabled={disabled}
        onChange={(ref) => {
          setDraft({ ...draft, ref });
        }}
      />
      <LocalizedFields
        label={t("checksForm.header.source")}
        value={draft.source ?? {}}
        disabled={disabled}
        onChange={(source) => {
          setDraft({ ...draft, source });
        }}
      />
      <Input
        label={t("checksForm.header.url")}
        value={draft.url ?? ""}
        isMono
        disabled={disabled}
        onChange={(e) => {
          setDraft({ ...draft, url: e.target.value || null });
        }}
      />
      {!disabled && (
        <div className="pcf-actions">
          <span className="pcf-spacer" />
          <Button
            size="xs"
            variant="ghost"
            disabled={!dirty}
            onClick={() => {
              setDraft(file.header);
            }}
          >
            <Undo2 size="0.6875rem" />
            {t("checksForm.rule.reset")}
          </Button>
          <Button
            size="xs"
            disabled={!dirty}
            onClick={() => {
              apply([{ op: "set_header", header: draft }]);
            }}
            data-testid="checks-header-save"
          >
            <Save size="0.6875rem" />
            {t("checksForm.rule.save")}
          </Button>
        </div>
      )}
    </section>
  );
};

const NewRule = ({
  prefix,
  engines,
  disabled,
  taken,
  onAdd,
}: {
  prefix: string;
  engines: readonly string[];
  disabled: boolean;
  taken: readonly string[];
  onAdd: (id: string, title: Record<string, string>, engine: string) => void;
}) => {
  const { t } = useTranslation("packStudio");
  const [id, setId] = useState(`${prefix}/`);
  const [title, setTitle] = useState<Record<string, string>>({});
  const [engine, setEngine] = useState("regex");
  const clash = taken.includes(id.trim());
  return (
    <section className="psf-block" data-testid="rule-new">
      <BlockHead title={t("checksForm.newRule.title")} />
      <Input
        label={t("checksForm.rule.id")}
        {...(clash ? { hint: t("checksForm.newRule.taken") } : {})}
        value={id}
        isMono
        disabled={disabled}
        onChange={(e) => {
          setId(e.target.value);
        }}
        data-testid="rule-new-id"
      />
      <LocalizedFields
        label={t("checksForm.rule.title")}
        value={title}
        disabled={disabled}
        onChange={setTitle}
        testId="rule-new-title"
      />
      <div className="pcf-actions">
        <Select
          value={engine}
          onValueChange={setEngine}
          isDisabled={disabled}
          ariaLabel={t("checksForm.rule.engine")}
          options={engines.map((e) => ({
            value: e,
            label: t(`checksForm.engine.${e}`, { defaultValue: e }),
          }))}
        />
        <Button
          size="xs"
          variant="secondary"
          disabled={
            disabled ||
            clash ||
            id.trim() === "" ||
            id.trim() === `${prefix}/` ||
            !title.ru?.trim()
          }
          onClick={() => {
            onAdd(id.trim(), title, engine);
            setId(`${prefix}/`);
            setTitle({});
          }}
          data-testid="rule-new-add"
        >
          <Plus size="0.6875rem" />
          {t("checksForm.newRule.add")}
        </Button>
      </div>
    </section>
  );
};

/**
 * Файл правил `checks/*.yaml` формой (template-studio.md, 5.7, срез T14): шапка (название группы,
 * ссылка на документ, источник), правила карточками и «Проверить на предпросмотре». Каждая правка
 * пишется в файл точечно с `If-Match`, как правка «Исходника».
 */
export const PackChecksFileForm = ({
  workspaceId,
  path,
  onSaved,
}: PackChecksFileFormProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const versionRef = useMemo(() => versionRefOf(path), [path]);
  const ref = versionRef ?? { pack: "", template: "", version: "" };
  const name = path.split("/").pop() ?? "";
  const query = usePackChecksForm(workspaceId, versionRef);
  const patch = usePatchPackChecksForm(workspaceId, ref);
  const options = usePackPreviewOptions(workspaceId, ref);
  const [error, setError] = useState<unknown>(null);
  const [build, setBuild] = useState<PackPreviewBuild | null>(null);
  const onBuild = useCallback((next: PackPreviewBuild | null) => {
    setBuild(next);
  }, []);

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
  const file = data.files.find((f) => f.name === name);
  if (!file) {
    return <p className="psf-muted">{t("checksForm.notFound")}</p>;
  }
  const prefix = name.replace(/\.yaml$/, "");
  const apply = (ops: PackChecksOp[]) => {
    patch.mutate(
      { kind: "file", name, body: { ops }, etag: file.etag },
      {
        onSuccess: (next) => {
          setError(null);
          onSaved(next.files.find((f) => f.name === name)?.path ?? path);
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
  const docName = (doc: string) => {
    const found = options.data?.documents.find((d) => d.id === doc);
    return found ? pickLocalized(found.name, i18n.language, doc) : doc;
  };
  const ctx: RuleCtx = {
    disabled: file.read_only !== null || patch.isPending,
    documents: data.documents,
    docName,
    engines: data.engines,
    structuralChecks: data.structural_checks,
    categories: categoriesOf(data),
    apply,
  };
  const ruleDocs = [
    ...new Set(
      file.rules.flatMap((r) =>
        r.entry ? (r.entry.applies_to ?? data.documents) : [],
      ),
    ),
  ];
  const byRule = findingsByRule(build?.checks);
  const checked = build?.status === "succeeded";
  const stale = error instanceof ApiError && error.code === "stale_file";

  return (
    <div className="psf-form pcf-form" data-testid="checks-file-form">
      {file.read_only !== null && (
        <Notice
          tone="info"
          role="status"
          text={
            file.read_only === "version_released"
              ? t("editor.readOnlyReleased")
              : t("editor.readOnlyRegistry")
          }
        />
      )}
      {error !== null && (
        <Notice
          tone={stale ? "warn" : "err"}
          role="alert"
          text={
            <span data-testid="checks-error">
              {stale ? t("submission.stale") : packErrorText(error)}
              {reasonOf(error) && (
                <span className="ps-preview-detail mono">
                  {reasonOf(error)}
                </span>
              )}
            </span>
          }
        />
      )}
      {file.error && (
        <p className="hint pcf-warn">
          {t("checksForm.fileError", { error: file.error })}
        </p>
      )}
      <p className="hint">{t("checksForm.lead")}</p>
      <datalist id="pcf-categories">
        {ctx.categories.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <HeaderEditor file={file} disabled={ctx.disabled} apply={apply} />
      <section className="psf-block">
        <BlockHead
          title={t("checksForm.run.title")}
          actions={patch.isPending ? <Spinner size="sm" /> : undefined}
        />
        <CheckOnPreview
          workspaceId={workspaceId}
          versionRef={ref}
          documents={ruleDocs}
          build={build}
          onBuild={onBuild}
        />
      </section>
      <h3 className="pcf-rules-head">
        {t("checksForm.rules", { count: file.rules.length })}
      </h3>
      <ol className="pcf-rules">
        {file.rules.map((indexed) =>
          indexed.entry ? (
            <RuleCard
              key={`${String(indexed.index)}:${indexed.entry.id}`}
              ctx={ctx}
              index={indexed.index}
              count={file.rules.length}
              rule={indexed.entry}
              paramsYaml={indexed.params_yaml}
              prefix={prefix}
              findings={byRule.get(indexed.entry.id)}
              checked={checked}
            />
          ) : (
            <li key={indexed.index} className="pcf-rule">
              <p className="hint pcf-warn">
                {t("submission.brokenEntry", { error: indexed.error ?? "" })}
              </p>
            </li>
          ),
        )}
      </ol>
      {file.read_only === null && (
        <NewRule
          prefix={prefix}
          engines={data.engines}
          disabled={ctx.disabled}
          taken={file.rules.flatMap((r) => (r.entry ? [r.entry.id] : []))}
          onAdd={(id, title, engine) => {
            apply([
              {
                op: "add_rule",
                rule: {
                  id,
                  title,
                  applies_to: null,
                  default_severity: "warn",
                  engine,
                  params:
                    engine === "structural" ? { check: "page_geometry" } : {},
                },
              },
            ]);
          }}
        />
      )}
    </div>
  );
};

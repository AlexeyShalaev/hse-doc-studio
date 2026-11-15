import { useCallback, useMemo, useState } from "react";
import { Plus, SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  PackStaleFileError,
  lintTargetOf,
  packErrorText,
  usePackLint,
  usePackPreviewOptions,
  usePackSubmission,
  usePackSubmissionRoutes,
  usePatchPackSubmission,
  versionRefOf,
  type PackSubmissionOp,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  effectiveCombination,
  exampleOf,
  selectionKey,
  usePreviewSelection,
  useSwitchText,
} from "@features/pack-preview";
import { ApiError } from "@shared/api";
import { pickLocalized } from "@shared/lib";
import { Button, ErrorState, Input, Select, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { RouteOrderCard } from "./RouteOrderCard";
import { ProfileCard } from "./ProfileCard";
import type { FormCtx } from "./entries";
import { LocalizedFields } from "./kit";
import "./submissionForm.css";

export type PackSubmissionFormProps = {
  workspaceId: string;
  /** `version.yaml` версии. */
  path: string;
  /** Меняется после каждой записи в пространстве: проверки и маршрут считаются заново. */
  lintEpoch: number;
  /** Правка записана в манифест (`path`). */
  onSaved: (path: string) => void;
};

const reasonOf = (error: unknown): string | null =>
  error instanceof ApiError && typeof error.data?.reason === "string"
    ? error.data.reason
    : null;

/** Переключатели комбинации те же, что у предпросмотра (6.2): выбор общий. */
const CombinationBar = ({
  workspaceId,
  versionRef,
}: {
  workspaceId: string;
  versionRef: PackVersionRef;
}) => {
  const { t } = useTranslation("packStudio");
  const text = useSwitchText();
  const options = usePackPreviewOptions(workspaceId, versionRef);
  const { selection, setSwitch } = usePreviewSelection(
    selectionKey(workspaceId, versionRef),
  );
  if (!options.data) return null;
  const opts = options.data;
  const combination = effectiveCombination(
    opts,
    exampleOf(opts, selection.example),
    selection.overrides,
  );
  return (
    <details className="sync-details psf-combo" data-testid="submission-combo">
      <summary>
        <SlidersHorizontal size="0.75rem" aria-hidden="true" />{" "}
        {t("submission.combo.title")}
      </summary>
      <p className="hint">{t("submission.combo.hint")}</p>
      <div className="ps-preview-switches">
        {opts.switches.map((sw) => (
          <div className="field" key={sw.id}>
            <label>{text.label(sw)}</label>
            <Select
              value={combination[sw.id] ?? sw.default}
              onValueChange={(value) => {
                setSwitch(sw.id, value);
              }}
              ariaLabel={text.label(sw)}
              options={sw.values.map((value) => ({
                value,
                label: text.value(sw, value),
              }))}
            />
          </div>
        ))}
      </div>
    </details>
  );
};

/** «Новая точка»: id и название; пунктов у неё пока нет. */
const NewProfile = ({
  disabled,
  taken,
  onAdd,
}: {
  disabled: boolean;
  taken: readonly string[];
  onAdd: (id: string, name: Record<string, string>) => void;
}) => {
  const { t } = useTranslation("packStudio");
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [name, setName] = useState<Record<string, string>>({});
  const clash = taken.includes(id.trim());
  if (!open) {
    return (
      <Button
        size="sm"
        variant="secondary"
        disabled={disabled}
        onClick={() => {
          setOpen(true);
        }}
        data-testid="profile-new"
      >
        <Plus size="0.75rem" />
        {t("submission.profile.add")}
      </Button>
    );
  }
  return (
    <div className="psf-block psf-new" data-testid="profile-new-form">
      <Input
        label={t("submission.head.id")}
        hint={
          clash ? t("submission.profile.idTaken") : t("submission.head.idHint")
        }
        value={id}
        isMono
        onChange={(e) => {
          setId(e.target.value);
        }}
        data-testid="profile-new-id"
      />
      <LocalizedFields
        label={t("submission.head.name")}
        value={name}
        onChange={setName}
        testId="profile-new-name"
      />
      <div className="psf-actions">
        <Button
          size="xs"
          variant="ghost"
          onClick={() => {
            setOpen(false);
          }}
        >
          {t("submission.profile.cancel")}
        </Button>
        <Button
          size="xs"
          disabled={disabled || id.trim() === "" || clash}
          onClick={() => {
            onAdd(id.trim(), name);
            setOpen(false);
            setId("");
            setName({});
          }}
          data-testid="profile-new-save"
        >
          {t("submission.profile.create")}
        </Button>
      </div>
    </div>
  );
};

/**
 * Форма точек сдачи версии (template-studio.md, 5.5-5.8, срез T13): профили сдачи, их
 * пункты, файлы сверх документов, порядок маршрута версии и точки, пресет `signing_slots`
 * и «Маршрут в этой комбинации». Каждая правка сразу пишется в `version.yaml` точечной
 * правкой с `If-Match`; тот же путь, что у правки «Исходника»: проверки, класс версии,
 * предпросмотр.
 */
export const PackSubmissionForm = ({
  workspaceId,
  path,
  lintEpoch,
  onSaved,
}: PackSubmissionFormProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const versionRef = useMemo(() => versionRefOf(path), [path]);
  const ref = versionRef ?? { pack: "", template: "", version: "" };
  const query = usePackSubmission(workspaceId, versionRef);
  const patch = usePatchPackSubmission(workspaceId, ref);
  const lint = usePackLint(workspaceId, lintTargetOf(path), String(lintEpoch));
  const options = usePackPreviewOptions(workspaceId, ref);
  const { selection } = usePreviewSelection(selectionKey(workspaceId, ref));
  const [error, setError] = useState<unknown>(null);
  const [open, setOpen] = useState<Record<number, boolean>>({ 0: true });
  const data = query.data;

  const combination = options.data
    ? effectiveCombination(
        options.data,
        exampleOf(options.data, selection.example),
        selection.overrides,
      )
    : {};
  const exampleId = options.data
    ? (exampleOf(options.data, selection.example)?.id ??
      options.data.default_example)
    : null;
  const routes = usePackSubmissionRoutes(
    workspaceId,
    versionRef,
    `${String(lintEpoch)}:${data?.etag ?? ""}`,
    { example: exampleId, combination },
    data !== undefined && options.data !== undefined,
  );

  const apply = useCallback(
    (ops: PackSubmissionOp[]) => {
      if (!data) return;
      patch.mutate(
        { body: { ops }, etag: data.etag },
        {
          onSuccess: (next) => {
            setError(null);
            onSaved(next.path);
          },
          onError: (e) => {
            setError(e);
            if (
              e instanceof PackStaleFileError ||
              (e instanceof ApiError && e.code === "stale_file")
            ) {
              void query.refetch();
            }
          },
        },
      );
    },
    [data, patch, onSaved, query],
  );

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
        description={
          <>
            {packErrorText(query.error)}
            {reasonOf(query.error) && (
              <span className="ps-preview-detail mono">
                {reasonOf(query.error)}
              </span>
            )}
          </>
        }
        onRetry={() => void query.refetch()}
      />
    );
  }

  const sub = query.data;
  const catalog = sub.slots.map((s) => s.id);
  const slotLabel = (slot: string) => {
    const found = sub.slots.find((s) => s.id === slot);
    return found ? pickLocalized(found.label, i18n.language, slot) : slot;
  };
  const docName = (doc: string) => {
    const found = options.data?.documents.find((d) => d.id === doc);
    return found ? pickLocalized(found.name, i18n.language, doc) : doc;
  };
  const ctx: FormCtx = {
    data: sub,
    disabled: sub.read_only !== null || patch.isPending,
    apply,
    slotLabel,
    docName,
  };
  const versionSteps = sub.route ?? sub.builtin_route;
  const versionLabel =
    sub.route === null
      ? t("submission.route.builtinName")
      : t("submission.route.versionName");
  const routeById = new Map(
    (routes.data?.profiles ?? []).map((route) => [route.id, route]),
  );
  const stale = error instanceof ApiError && error.code === "stale_file";

  return (
    <div className="psf-form" data-testid="submission-form">
      {sub.read_only !== null && (
        <Notice
          tone="info"
          role="status"
          text={
            sub.read_only === "version_released"
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
            <span data-testid="submission-error">
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
      <p className="hint">{t("submission.lead")}</p>
      <RouteOrderCard
        title={t("submission.route.versionTitle")}
        hint={t("submission.route.versionHint")}
        declared={sub.route}
        inherited={sub.builtin_route}
        inheritedLabel={t("submission.route.builtinName")}
        catalog={catalog}
        slotLabel={slotLabel}
        disabled={ctx.disabled}
        onSave={(steps) => {
          apply([{ op: "set_route", steps }]);
        }}
        testId="version-route"
      />
      <div className="psf-profiles-head">
        <h3>{t("submission.profiles")}</h3>
        {patch.isPending && <Spinner size="sm" />}
      </div>
      <CombinationBar workspaceId={workspaceId} versionRef={ref} />
      {routes.isError && (
        <p className="hint psf-warn">
          {t("submission.preview.failed", {
            reason: reasonOf(routes.error) ?? packErrorText(routes.error),
          })}
        </p>
      )}
      {sub.profiles.length === 0 && (
        <p className="psf-muted">{t("submission.noProfiles")}</p>
      )}
      <ol className="psf-profile-list">
        {sub.profiles.map((profile) => (
          <ProfileCard
            key={`${String(profile.index)}:${profile.id ?? ""}`}
            ctx={ctx}
            profile={profile}
            count={sub.profiles.length}
            open={open[profile.index] ?? false}
            onToggle={(next) => {
              setOpen((prev) => ({ ...prev, [profile.index]: next }));
            }}
            versionSteps={versionSteps}
            versionLabel={versionLabel}
            catalog={catalog}
            findings={lint.data?.findings ?? []}
            route={profile.id ? routeById.get(profile.id) : undefined}
            routeLoading={routes.isFetching}
          />
        ))}
      </ol>
      {sub.read_only === null && (
        <NewProfile
          disabled={ctx.disabled}
          taken={sub.profiles.flatMap((p) => (p.id ? [p.id] : []))}
          onAdd={(id, name) => {
            apply([{ op: "add_profile", head: { id, name } }]);
            setOpen((prev) => ({ ...prev, [sub.profiles.length]: true }));
          }}
        />
      )}
    </div>
  );
};

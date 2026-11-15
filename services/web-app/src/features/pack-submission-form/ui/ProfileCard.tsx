import { useState } from "react";
import { ChevronDown, ChevronUp, Save, Trash2, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  PackDiagnostic,
  PackProfileHead,
  PackProfileRoute,
  PackSubmissionProfile,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib";
import { Button, Input } from "@shared/ui";
import { LANGS, hintIssue, profileFindings } from "../lib/submission";
import type { Steps } from "../lib/routeSteps";
import {
  ExtrasEditor,
  ItemsEditor,
  PresetEditor,
  type FormCtx,
} from "./entries";
import { LocalizedFields } from "./kit";
import { RouteOrderCard } from "./RouteOrderCard";
import { RoutePreview } from "./RoutePreview";

type Head = {
  id: string;
  name: Record<string, string>;
  description: Record<string, string>;
  hint: Record<string, string>;
};

const headOf = (profile: PackSubmissionProfile): Head => ({
  id: profile.id ?? "",
  name: { ...profile.name },
  description: { ...profile.description },
  hint: { ...(profile.deadline_hint ?? {}) },
});

const filled = (value: Record<string, string>) =>
  LANGS.some((lang) => (value[lang] ?? "").trim() !== "");

/** Шапка профиля: id, название, описание и подсказка срока (5.5, 5.8); запись по кнопке. */
const HeadEditor = ({
  ctx,
  profile,
}: {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
}) => {
  const { t } = useTranslation("packStudio");
  const [draft, setDraft] = useState(() => headOf(profile));
  const [seen, setSeen] = useState(profile);
  if (seen !== profile) {
    setSeen(profile);
    setDraft(headOf(profile));
  }
  const dirty = JSON.stringify(draft) !== JSON.stringify(headOf(profile));
  const hintOn = filled(draft.hint);
  const issues = hintOn
    ? Object.fromEntries(
        LANGS.map((lang) => {
          const issue = hintIssue(draft.hint[lang] ?? "");
          return [lang, issue ? t(`submission.hintIssue.${issue}`) : null];
        }),
      )
    : undefined;
  const hasIssue = issues
    ? Object.values(issues).some((v) => v !== null)
    : false;
  const save = () => {
    const head: PackProfileHead = {
      id: draft.id.trim(),
      name: draft.name,
      description: draft.description,
      deadline_hint: hintOn ? draft.hint : null,
    };
    ctx.apply([{ op: "set_profile", profile: profile.index, head }]);
  };
  return (
    <section
      className="psf-block"
      data-testid={`head-${String(profile.index)}`}
    >
      <Input
        label={t("submission.head.id")}
        hint={t("submission.head.idHint")}
        value={draft.id}
        isMono
        disabled={ctx.disabled}
        onChange={(e) => {
          setDraft({ ...draft, id: e.target.value });
        }}
        data-testid={`head-${String(profile.index)}-id`}
      />
      <LocalizedFields
        label={t("submission.head.name")}
        value={draft.name}
        disabled={ctx.disabled}
        onChange={(name) => {
          setDraft({ ...draft, name });
        }}
        testId={`head-${String(profile.index)}-name`}
      />
      <LocalizedFields
        label={t("submission.head.description")}
        value={draft.description}
        disabled={ctx.disabled}
        multiline
        onChange={(description) => {
          setDraft({ ...draft, description });
        }}
      />
      <LocalizedFields
        label={t("submission.head.hint")}
        value={draft.hint}
        disabled={ctx.disabled}
        max={200}
        issues={issues}
        onChange={(hint) => {
          setDraft({ ...draft, hint });
        }}
        testId={`head-${String(profile.index)}-hint`}
      />
      <p className="hint">{t("submission.head.hintHint")}</p>
      {!ctx.disabled && (
        <div className="psf-actions">
          <Button
            size="xs"
            variant="ghost"
            disabled={!dirty}
            onClick={() => {
              setDraft(headOf(profile));
            }}
          >
            <Undo2 size="0.6875rem" />
            {t("submission.head.reset")}
          </Button>
          <Button
            size="xs"
            disabled={!dirty || hasIssue || draft.id.trim() === ""}
            onClick={save}
            data-testid={`head-${String(profile.index)}-save`}
          >
            <Save size="0.6875rem" />
            {t("submission.head.save")}
          </Button>
        </div>
      )}
    </section>
  );
};

export type ProfileCardProps = {
  ctx: FormCtx;
  profile: PackSubmissionProfile;
  count: number;
  open: boolean;
  onToggle: (open: boolean) => void;
  /** Порядок версии (или встроенный, если его нет) и его подпись. */
  versionSteps: Steps;
  versionLabel: string;
  catalog: readonly string[];
  findings: readonly PackDiagnostic[];
  route: PackProfileRoute | undefined;
  routeLoading: boolean;
};

/**
 * Профиль сдачи (контрольная точка) карточкой: шапка, пункты с подписями и способами,
 * файлы сверх документов, порядок маршрута точки, пресет `signing_slots` и «Маршрут в этой
 * комбинации». Находки линтера про профиль видны тут же.
 */
export const ProfileCard = ({
  ctx,
  profile,
  count,
  open,
  onToggle,
  versionSteps,
  versionLabel,
  catalog,
  findings,
  route,
  routeLoading,
}: ProfileCardProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const [confirm, setConfirm] = useState(false);
  const own = profileFindings(findings, profile);
  const name = pickLocalized(profile.name, i18n.language, profile.id ?? "");
  const errors = own.filter((f) => f.severity === "error").length;
  return (
    <li
      className="psf-profile"
      data-testid={`profile-${String(profile.index)}`}
    >
      <details
        open={open}
        onToggle={(e) => {
          onToggle(e.currentTarget.open);
        }}
      >
        <summary className="psf-profile-summary">
          <span className="psf-profile-name">
            {name !== "" ? name : t("submission.unnamed")}
          </span>
          <code className="mono psf-chip-id">{profile.id ?? "?"}</code>
          {(profile.error !== null || errors > 0) && (
            <span className="ps-mark ps-mark-warn">
              {t("submission.problems", {
                count: errors + (profile.error ? 1 : 0),
              })}
            </span>
          )}
        </summary>
        <div className="psf-profile-body">
          <div className="psf-actions psf-profile-actions">
            <Button
              size="xs"
              variant="ghost"
              disabled={ctx.disabled || profile.index === 0}
              onClick={() => {
                ctx.apply([
                  {
                    op: "move_profile",
                    profile: profile.index,
                    to: profile.index - 1,
                  },
                ]);
              }}
            >
              <ChevronUp size="0.6875rem" />
              {t("submission.profile.up")}
            </Button>
            <Button
              size="xs"
              variant="ghost"
              disabled={ctx.disabled || profile.index >= count - 1}
              onClick={() => {
                ctx.apply([
                  {
                    op: "move_profile",
                    profile: profile.index,
                    to: profile.index + 1,
                  },
                ]);
              }}
            >
              <ChevronDown size="0.6875rem" />
              {t("submission.profile.down")}
            </Button>
            {confirm ? (
              <>
                <span className="hint">
                  {t("submission.profile.removeConfirm")}
                </span>
                <Button
                  size="xs"
                  variant="danger"
                  disabled={ctx.disabled}
                  onClick={() => {
                    setConfirm(false);
                    ctx.apply([
                      { op: "remove_profile", profile: profile.index },
                    ]);
                  }}
                  data-testid={`profile-${String(profile.index)}-remove-yes`}
                >
                  {t("submission.profile.removeYes")}
                </Button>
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={() => {
                    setConfirm(false);
                  }}
                >
                  {t("submission.profile.removeNo")}
                </Button>
              </>
            ) : (
              <Button
                size="xs"
                variant="ghost"
                disabled={ctx.disabled}
                onClick={() => {
                  setConfirm(true);
                }}
                data-testid={`profile-${String(profile.index)}-remove`}
              >
                <Trash2 size="0.6875rem" />
                {t("submission.profile.remove")}
              </Button>
            )}
          </div>
          {profile.error && (
            <p className="hint psf-warn">
              {t("submission.profile.error", { error: profile.error })}
            </p>
          )}
          {own.length > 0 && (
            <ul
              className="psf-findings"
              data-testid={`profile-${String(profile.index)}-findings`}
            >
              {own.map((f) => (
                <li
                  key={`${f.check}-${f.message}`}
                  className={f.severity === "error" ? "psf-warn" : "psf-muted"}
                >
                  {f.message}
                </li>
              ))}
            </ul>
          )}
          <HeadEditor ctx={ctx} profile={profile} />
          <ItemsEditor ctx={ctx} profile={profile} />
          <ExtrasEditor ctx={ctx} profile={profile} />
          <RouteOrderCard
            title={t("submission.route.profileTitle")}
            hint={t("submission.route.profileHint")}
            declared={profile.signing_route}
            inherited={versionSteps}
            inheritedLabel={versionLabel}
            catalog={catalog}
            slotLabel={ctx.slotLabel}
            disabled={ctx.disabled}
            onSave={(steps) => {
              ctx.apply([
                { op: "set_profile_route", profile: profile.index, steps },
              ]);
            }}
            testId={`profile-${String(profile.index)}-route`}
          />
          <PresetEditor ctx={ctx} profile={profile} />
          <section className="psf-block psf-preview-block">
            <h4>{t("submission.preview.title")}</h4>
            <RoutePreview
              route={route}
              loading={routeLoading}
              unreadable={profile.error !== null && route === undefined}
              slotLabel={ctx.slotLabel}
              docName={ctx.docName}
            />
          </section>
        </div>
      </details>
    </li>
  );
};

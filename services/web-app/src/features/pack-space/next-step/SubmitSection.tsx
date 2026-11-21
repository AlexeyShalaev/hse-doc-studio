import { GitPullRequest } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Input, Textarea } from "@shared/ui";
import type { ChangesData } from "../changes/useChangesStatus";
import { ForkChoice } from "./ForkChoice";
import { LicenseConsent } from "./LicenseConsent";
import { NotesFields } from "./NotesFields";
import { NumberDialog } from "./NumberDialog";
import { Outcome, Progress } from "./Progress";
import { ReleaseOption } from "./ReleaseOption";
import { BlockerText } from "./SubmitPrimary";
import type { SubmitController } from "./useSubmit";

/**
 * Раздел отправки внутри панели «Изменения» (pack-studio-ux.md, 5.6): заметки к версии, галочка
 * «Выпустить версию», куда уйдёт запрос, название и описание, согласие с лицензией, ход отправки.
 * Кнопка отправки в подвале панели (`SubmitPrimary`), состояние у обоих общее (`useSubmit`).
 */
export const SubmitSection = ({
  c,
  data,
  onAccess,
  onOpenFile,
}: {
  c: SubmitController;
  data: ChangesData;
  onAccess: () => void;
  onOpenFile: (path: string) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const [numberOpen, setNumberOpen] = useState(false);
  if (!c.available) return null;
  const { state } = c;
  const git = data.raw.git;
  const { request } = data.status;
  const requestLabel = request.kind === "open" ? request.label : null;
  const lock = c.running;
  return (
    <section className="sp-ch-section sp-sb" data-testid="sp-sb">
      {c.stateLoading && (
        <p className="sp-ch-muted" role="status">
          {t("changes.submit.loading")}
        </p>
      )}
      <NotesFields c={c} />
      <ReleaseOption
        c={c}
        onNumber={() => {
          setNumberOpen(true);
        }}
      />
      <div className="sp-ch-banner" data-testid="sp-sb-where">
        <GitPullRequest size="1rem" aria-hidden="true" />
        <div className="sp-ch-banner-text">
          <span>
            {requestLabel
              ? t("changes.submit.where.update", { label: requestLabel })
              : t("changes.submit.where.new", { base: git?.base_branch ?? "" })}
          </span>
          {git?.workspace.service_access && (
            <span>{t("changes.submit.where.service")}</span>
          )}
          {git?.workspace.fork_url && (
            <span>
              {t("changes.submit.where.viaFork", {
                url: git.workspace.fork_url,
              })}
            </span>
          )}
        </div>
      </div>
      {requestLabel === null && (
        <details className="sp-sb-more" data-testid="sp-sb-request">
          <summary>{t("changes.submit.request.summary")}</summary>
          <div className="sp-sb-more-body">
            <Input
              label={t("changes.submit.request.title")}
              hint={t("changes.submit.request.titleHint")}
              value={c.title}
              maxLength={200}
              disabled={lock}
              onChange={(e) => {
                c.setTitle(e.target.value);
              }}
              data-testid="sp-sb-title"
            />
            <Textarea
              label={t("changes.submit.request.description")}
              hint={t("changes.submit.request.descriptionHint")}
              value={c.description}
              rows={3}
              maxLength={20_000}
              disabled={lock}
              onChange={(e) => {
                c.setDescription(e.target.value);
              }}
              data-testid="sp-sb-description"
            />
          </div>
        </details>
      )}
      {c.consent && (
        <LicenseConsent
          info={c.consent}
          checked={c.accepted}
          disabled={lock}
          onChange={c.setAccepted}
        />
      )}
      {c.needsAck && (
        <label className="sp-sb-choice" data-testid="sp-sb-ack">
          <input
            type="checkbox"
            checked={c.ack}
            disabled={lock}
            onChange={(e) => {
              c.setAck(e.target.checked);
            }}
            data-testid="sp-sb-ack-input"
          />
          <span className="sp-sb-choice-text">
            <span>{t("changes.submit.ack.label")}</span>
            <span className="sp-sb-choice-hint">
              {t("changes.submit.ack.hint")}
            </span>
          </span>
        </label>
      )}
      {c.impactPending && (
        <p
          className="sp-ch-muted"
          role="status"
          data-testid="sp-sb-impact-wait"
        >
          {t("changes.submit.impactWaiting")}
        </p>
      )}
      <ForkChoice
        c={c}
        serviceAccess={git?.workspace.service_access ?? false}
      />
      <Progress c={c} onAccess={onAccess} onOpenFile={onOpenFile} />
      <Outcome c={c} onAccess={onAccess} />
      <BlockerText c={c} />
      {state && (
        <NumberDialog
          workspaceId={data.raw.workspace.id}
          state={state}
          isOpen={numberOpen}
          beforeMove={c.notes.flush}
          onClose={() => {
            setNumberOpen(false);
          }}
        />
      )}
    </section>
  );
};

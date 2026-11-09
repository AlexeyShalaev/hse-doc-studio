import { useTranslation } from "react-i18next";
import { Download, KeyRound, Upload } from "lucide-react";
import { signingPdfUrl } from "@entities/signing-route";
import { pickLocalized } from "@shared/lib";
import { Button } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { InlinePlan } from "../model/inlinePlan";
import type { SignWay } from "../model/types";
import { FilePick } from "./FilePick";
import type { BlockProps } from "./ImageBlock";
import { KeyCreateForm, KeyImportForm } from "./KeyForms";

type EsignProps = BlockProps & { plan: InlinePlan };

const CERT_ACCEPT = ".cer,.crt,.pem,.asc";
const SIGNATURE_ACCEPT = ".asc,.sig,.p7s";

/** «Создать ключ OpenPGP» и «Импортировать ключ» с формой прямо в блоке. */
const KeyMaker = ({ ctx, ui, model }: BlockProps) => {
  const { t } = useTranslation("signing");
  const { panel } = ui.state;
  if (panel === "key-create")
    return (
      <KeyCreateForm
        busy={model.busy}
        defaultName={
          ctx.task.steps.flat().find((person) => person.me)?.name ?? ""
        }
        onCancel={() => {
          ui.patch({ panel: null });
        }}
        onSubmit={(input) => {
          void model.createKey(input);
        }}
      />
    );
  if (panel === "key-import")
    return (
      <KeyImportForm
        busy={model.busy}
        onCancel={() => {
          ui.patch({ panel: null });
        }}
        onSubmit={(input) => {
          void model.importKey(input);
        }}
      />
    );
  return (
    <div className="sgi-row">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled={model.busy}
        onClick={() => {
          ui.patch({ panel: "key-create", failure: null, nudge: null });
        }}
        data-testid="signing-key-new"
      >
        <KeyRound size="0.8125rem" aria-hidden />
        {t("esign.create")}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled={model.busy}
        onClick={() => {
          ui.patch({ panel: "key-import", failure: null, nudge: null });
        }}
        data-testid="signing-key-import-open"
      >
        <Upload size="0.8125rem" aria-hidden />
        {t("esign.import")}
      </Button>
    </div>
  );
};

/** Запрет хранить ключи на сервере: что это значит и чем подписать вместо ключа Студии. */
const NoServerKeys = ({ plan }: { plan: InlinePlan }) => {
  const { t } = useTranslation("signing");
  return (
    <div data-testid="signing-no-server-keys">
      <Notice
        tone="info"
        text={
          plan.method === "pades"
            ? t("esign.padesNoKeys")
            : plan.needsSign
              ? t("esign.noServerKeys")
              : t("esign.noServerKeysPlate")
        }
      />
    </div>
  );
};

/** Откуда взять данные плашки, пока её ещё можно менять: ключ Студии, КриптоПро или файл. */
const PlateSources = ({ ctx, ui, model, plan }: EsignProps) => {
  const { t } = useTranslation("signing");
  const forming =
    ui.state.panel === "key-create" || ui.state.panel === "key-import";
  return (
    <div className="sgi-block" data-testid="signing-plate-sources">
      {plan.serverKeys ? (
        <>
          {!forming &&
            plan.keys.map((key) => (
              <Button
                key={key.id}
                type="button"
                size="sm"
                variant="secondary"
                className="sgi-wide"
                disabled={model.busy}
                onClick={() => {
                  void model.plateFromKey(key.id);
                }}
                data-testid={`signing-plate-key-${key.id}`}
              >
                {t("esign.plateFromKey", { label: key.label })}
              </Button>
            ))}
          <KeyMaker ctx={ctx} ui={ui} model={model} />
        </>
      ) : (
        <NoServerKeys plan={plan} />
      )}
      {!forming && plan.method === "detached" && (
        <div className="sgi-row">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={model.busy}
            onClick={() => {
              ui.patch({ prompt: "cryptopro-plate", failure: null });
            }}
            data-testid="signing-plate-cryptopro"
          >
            {t("esign.plateCryptoPro")}
          </Button>
          <FilePick
            accept={CERT_ACCEPT}
            disabled={model.busy}
            testId="signing-plate-file"
            onFile={(file) => {
              void model.plateFromFile(file);
            }}
          >
            {t("esign.plateFile")}
          </FilePick>
        </div>
      )}
    </div>
  );
};

/** Ключ Студии для подписи: единственный строкой, из нескольких список; нет ключа: создать. */
const StudioWay = ({ ctx, ui, model, plan }: EsignProps) => {
  const { t } = useTranslation("signing");
  const forming =
    ui.state.panel === "key-create" || ui.state.panel === "key-import";
  const label = (key: InlinePlan["keys"][number]) =>
    key.protected ? `${key.label} (${t("esign.keyProtected")})` : key.label;
  return (
    <>
      {plan.key === null ? (
        !model.keysLoading && (
          <Notice
            tone={ui.state.nudge === "key" ? "err" : "warn"}
            text={t("esign.noKey")}
          />
        )
      ) : plan.keys.length === 1 ? (
        <p data-testid="signing-key-line">
          {t("esign.key", { label: label(plan.key) })}
        </p>
      ) : (
        <label className="sgi-field">
          <span>{t("esign.keySelect")}</span>
          <select
            className="input"
            value={plan.key.id}
            disabled={model.busy}
            onChange={(event) => {
              ui.patch({ identityId: event.target.value });
            }}
            data-testid="signing-key-select"
          >
            {plan.keys.map((key) => (
              <option key={key.id} value={key.id}>
                {label(key)}
              </option>
            ))}
          </select>
        </label>
      )}
      {plan.key === null || forming || ui.state.moreOpen ? (
        <KeyMaker ctx={ctx} ui={ui} model={model} />
      ) : (
        <div className="sgi-row">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={model.busy}
            onClick={() => {
              ui.patch({ moreOpen: true });
            }}
            data-testid="signing-key-other"
          >
            {t("esign.otherKey")}
          </Button>
        </div>
      )}
    </>
  );
};

/** Готовая открепленная подпись: скачать итоговый PDF, подписать у себя, загрузить файл. */
const FileWay = ({ ctx, ui, model, plan }: EsignProps) => {
  const { t, i18n } = useTranslation("signing");
  if (ctx.task.me.plate === null && plan.canSetPlate)
    return (
      <>
        <Notice
          tone={ui.state.nudge === "plate" ? "err" : "warn"}
          text={t("esign.plateMissing")}
        />
        <div className="sgi-row">
          <FilePick
            accept={CERT_ACCEPT}
            disabled={model.busy}
            testId="signing-plate-file"
            onFile={(file) => {
              void model.plateFromFile(file);
            }}
          >
            {t("esign.plateFile")}
          </FilePick>
        </div>
      </>
    );
  if (plan.signAfterFreeze)
    return <p className="sgi-hint">{t("esign.fileAfterFreeze")}</p>;
  return (
    <>
      <p className="sgi-hint">{t("esign.fileHint")}</p>
      {ui.state.nudge === "files" && (
        <Notice tone="err" text={t("esign.nudge.files")} />
      )}
      <ul className="sgi-files">
        {plan.slots.map((slot) => {
          const file = ui.state.files[slot.key];
          return (
            <li key={slot.key} data-testid={`signing-file-${slot.key}`}>
              <span className="sgi-file-doc">
                {pickLocalized(slot.docName, i18n.language, slot.docId)}
              </span>
              <div className="sgi-row">
                <Button asChild size="sm" variant="ghost">
                  <a href={signingPdfUrl(slot.pdfUrl)} download>
                    <Download size="0.8125rem" aria-hidden />
                    {t("esign.download")}
                  </a>
                </Button>
                <FilePick
                  accept={SIGNATURE_ACCEPT}
                  disabled={model.busy}
                  testId={`signing-file-pick-${slot.key}`}
                  onFile={(picked) => {
                    ui.patch({
                      files: { ...ui.state.files, [slot.key]: picked },
                      nudge: null,
                    });
                  }}
                >
                  {t("esign.pick")}
                </FilePick>
              </div>
              {file && <span className="sgi-file-name">{file.name}</span>}
            </li>
          );
        })}
      </ul>
    </>
  );
};

/** «Чем подписать»: только то, что разрешено на установке и подходит способу. */
const SignWays = (props: EsignProps) => {
  const { ui, model, plan } = props;
  const { t } = useTranslation("signing");
  if (plan.ways.length === 0) return <NoServerKeys plan={plan} />;
  const pick = (way: SignWay) => {
    ui.patch({ way, nudge: null, failure: null, panel: null });
  };
  return (
    <>
      <div
        className="sgi-ways"
        role="radiogroup"
        aria-label={t("esign.ways")}
        data-testid="signing-ways"
      >
        <span className="sgi-legend">{t("esign.ways")}</span>
        {ui.state.nudge === "way" && (
          <Notice tone="err" text={t("esign.nudge.way")} />
        )}
        {plan.ways.map((way) => (
          <label
            key={way}
            className="sgi-way"
            data-active={plan.way === way}
            data-testid={`signing-way-${way}`}
          >
            <input
              type="radio"
              name="signing-way"
              checked={plan.way === way}
              disabled={model.busy}
              onChange={() => {
                pick(way);
              }}
            />
            <span>
              <strong>{t(`esign.way.${way}`)}</strong>
              <small>{t(`esign.wayHint.${way}`)}</small>
            </span>
          </label>
        ))}
      </div>
      {!plan.serverKeys && <NoServerKeys plan={plan} />}
      {plan.way === "studio" && <StudioWay {...props} />}
      {plan.way === "file" && <FileWay {...props} />}
    </>
  );
};

/**
 * ЭП на странице подписанта (раздел 3.2): данные плашки, пока документы не зафиксированы,
 * и способ поставить подпись, когда этим нажатием она ставится.
 */
export const EsignBlock = (props: EsignProps) => {
  const { ctx, ui, model, plan } = props;
  const { t } = useTranslation("signing");
  const { plate } = ctx.task.me;
  // Подписывая, плашку заполняют ключ Студии и сертификат КриптоПро; отдельно её задают
  // только до подписи и для готовой подписи.
  const plateStep = !plan.needsSign && plan.canSetPlate;
  return (
    <div className="sgi-block" data-testid="signing-esign">
      {plate ? (
        <p data-testid="signing-plate">
          {t("method.plateReady", {
            owner: plate.owner,
            kind: t(`method.plateKind.${plate.kind}`),
            id: plate.cert_id,
          })}
        </p>
      ) : (
        plateStep && (
          <Notice
            tone={ui.state.nudge === "plate" ? "err" : "warn"}
            text={t("esign.plateMissing")}
          />
        )
      )}
      {plateStep &&
        (plate && !ui.state.moreOpen ? (
          <div className="sgi-row">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={model.busy}
              onClick={() => {
                ui.patch({ moreOpen: true });
              }}
              data-testid="signing-plate-change"
            >
              {t("esign.plateChange")}
            </Button>
          </div>
        ) : (
          <PlateSources {...props} />
        ))}
      {plan.needsSign && <SignWays {...props} />}
    </div>
  );
};

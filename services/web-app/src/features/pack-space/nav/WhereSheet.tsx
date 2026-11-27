import { Check, ChevronRight, PencilLine, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { NewPackTarget } from "@features/pack-scaffold";
import { Modal } from "@shared/ui";
import { VersionState } from "./VersionState";
import type { Where } from "./useWhere";

/**
 * Содержимое шторки «Куда перейти» (телефон): сверху «Мои правки», ниже пак, шаблон и версия.
 * Пак и шаблон переключаются сразу и шторка остаётся, чтобы увидеть версии нового места; выбор
 * версии и «Мои правки» закрывают её.
 */
export const WhereBody = ({
  where,
  onCreate,
  onDone,
}: {
  where: Where;
  onCreate: (target: NewPackTarget) => void;
  onDone: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  return (
    <div className="sp-where-body" data-testid="sp-where-body">
      {where.mine.map((item) => (
        <button
          key={`${item.ref.pack}/${item.ref.template}/${item.ref.version}`}
          type="button"
          className="sp-where-mine"
          data-testid="sp-where-mine"
          onClick={() => {
            where.goMine(item.ref);
            onDone();
          }}
        >
          <PencilLine size="1rem" aria-hidden="true" />
          <span className="sp-where-text">
            <b>{t("nav.where.mine")}</b>
            <span>
              {t("nav.where.mineLead", {
                template: item.templateName,
                version: item.ref.version,
                edited: t("nav.edited", { count: item.files }),
              })}
            </span>
          </span>
          <ChevronRight size="1rem" aria-hidden="true" />
        </button>
      ))}

      <section className="sp-where-section" aria-label={t("nav.where.pack")}>
        <h3 className="sp-kicker">{t("nav.where.pack")}</h3>
        {where.packs.map((item) => (
          <button
            key={item.id}
            type="button"
            className="sp-where-row"
            aria-current={item.current ? "true" : undefined}
            disabled={item.empty !== null}
            data-testid={`sp-where-pack-${item.id}`}
            onClick={() => {
              where.goPack(item.id);
            }}
          >
            <span className="sp-where-check">
              {item.current ? <Check size="1rem" aria-hidden="true" /> : null}
            </span>
            <span className="sp-where-text">
              <b>{item.name}</b>
              {item.empty ? (
                <span>{t(`nav.crumb.${item.empty}None`)}</span>
              ) : null}
            </span>
          </button>
        ))}
        <button
          type="button"
          className="sp-where-new"
          onClick={() => {
            onCreate({ kind: "pack" });
          }}
        >
          <Plus size="0.875rem" aria-hidden="true" />
          {t("nav.crumb.newPack")}
        </button>
      </section>

      <section
        className="sp-where-section"
        aria-label={t("nav.where.template")}
      >
        <h3 className="sp-kicker">{t("nav.where.template")}</h3>
        <div className="sp-where-chips">
          {where.templates.map((item) => (
            <button
              key={item.id}
              type="button"
              className="sp-where-chip"
              aria-current={item.current ? "true" : undefined}
              disabled={item.empty}
              title={item.empty ? t("nav.crumb.versionsNone") : undefined}
              data-testid={`sp-where-template-${item.id}`}
              onClick={() => {
                where.goTemplate(item.id);
              }}
            >
              {item.name}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="sp-where-new"
          onClick={() => {
            onCreate({ kind: "template", pack: where.packDir });
          }}
        >
          <Plus size="0.875rem" aria-hidden="true" />
          {t("nav.crumb.newTemplate")}
        </button>
      </section>

      <section className="sp-where-section" aria-label={t("nav.where.version")}>
        <h3 className="sp-kicker">{t("nav.where.version")}</h3>
        {where.versions.map((item) => (
          <button
            key={item.version}
            type="button"
            className="sp-where-row"
            aria-current={item.current ? "true" : undefined}
            data-testid={`sp-where-version-${item.version}`}
            onClick={() => {
              where.goVersion(item.version);
              onDone();
            }}
          >
            <span className="sp-where-check">
              {item.current ? <Check size="1rem" aria-hidden="true" /> : null}
            </span>
            <span className="sp-where-text">
              <b>{item.version}</b>
              <span>
                {[
                  item.isDefault ? t("nav.crumb.default") : null,
                  item.files > 0
                    ? t("nav.edited", { count: item.files })
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
            <VersionState released={item.released} accepted={item.accepted} />
          </button>
        ))}
      </section>
    </div>
  );
};

/** Шторка «Куда перейти»: на телефоне `Modal` становится шторкой снизу. */
export const WhereSheet = ({
  open,
  onClose,
  where,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  where: Where;
  onCreate: (target: NewPackTarget) => void;
}) => {
  const { t } = useTranslation("packSpace");
  return (
    <Modal isOpen={open} onClose={onClose} title={t("nav.where.title")}>
      <WhereBody
        where={where}
        onCreate={(target) => {
          onClose();
          onCreate(target);
        }}
        onDone={onClose}
      />
    </Modal>
  );
};

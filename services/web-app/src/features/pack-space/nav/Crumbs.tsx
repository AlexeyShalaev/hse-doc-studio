import { useTranslation } from "react-i18next";
import type { NewPackTarget } from "@features/pack-scaffold";
import { useSpace } from "../context/SpaceContext";
import { CrumbMenu, type CrumbAction, type CrumbItem } from "./CrumbMenu";
import { VersionState } from "./VersionState";
import type { Where } from "./useWhere";

/** Пак, шаблон и версия выпадающими крошками (десктоп и планшет). */
export const Crumbs = ({
  where,
  onCreate,
}: {
  where: Where;
  onCreate: (target: NewPackTarget) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { released } = useSpace();
  const current = where.versions.find((v) => v.current);

  const packs: CrumbItem[] = where.packs.map((p) => ({
    id: p.id,
    label: p.name,
    hint: p.empty ? t(`nav.crumb.${p.empty}None`) : undefined,
    disabled: p.empty !== null,
  }));
  const templates: CrumbItem[] = where.templates.map((item) => ({
    id: item.id,
    label: item.name,
    hint: item.empty ? t("nav.crumb.versionsNone") : undefined,
    disabled: item.empty,
  }));
  const versions: CrumbItem[] = where.versions.map((v) => ({
    id: v.version,
    label: t("nav.crumb.version", { version: v.version }),
    hint: [
      v.isDefault ? t("nav.crumb.default") : null,
      v.files > 0 ? t("nav.edited", { count: v.files }) : null,
    ]
      .filter(Boolean)
      .join(" · "),
    trail: <VersionState released={v.released} />,
  }));
  const mine: CrumbAction[] = where.mineElsewhere.map((item) => ({
    id: `mine-${item.ref.pack}-${item.ref.template}-${item.ref.version}`,
    label: t("nav.crumb.mine", {
      template: item.templateName,
      version: item.ref.version,
    }),
    accent: true,
    onSelect: () => {
      where.goMine(item.ref);
    },
  }));

  return (
    <div className="sp-crumbs" role="group" aria-label={t("nav.crumb.label")}>
      <CrumbMenu
        testId="sp-crumb-pack"
        label={t("nav.crumb.packOf", { name: where.packName })}
        title={t("nav.crumb.packHint")}
        trigger={<span className="truncate">{where.packName}</span>}
        items={packs}
        value={where.packs.find((p) => p.current)?.id ?? ""}
        onPick={where.goPack}
        bottom={[
          {
            id: "new",
            label: t("nav.crumb.newPack"),
            onSelect: () => {
              onCreate({ kind: "pack" });
            },
          },
        ]}
      />
      <span className="sp-crumb-sep" aria-hidden="true">
        ›
      </span>
      <CrumbMenu
        testId="sp-crumb-template"
        label={t("nav.crumb.templateOf", { name: where.templateName })}
        trigger={<span className="truncate">{where.templateName}</span>}
        items={templates}
        value={where.templates.find((p) => p.current)?.id ?? ""}
        onPick={where.goTemplate}
        bottom={[
          {
            id: "new",
            label: t("nav.crumb.newTemplate"),
            onSelect: () => {
              onCreate({ kind: "template", pack: where.packDir });
            },
          },
        ]}
      />
      <span className="sp-crumb-sep" aria-hidden="true">
        ›
      </span>
      <CrumbMenu
        testId="sp-crumb-version"
        trigger={
          <>
            <span>
              {t("nav.crumb.version", {
                version: current?.version ?? "",
              })}
            </span>
            <VersionState released={released} />
          </>
        }
        items={versions}
        value={current?.version ?? ""}
        onPick={where.goVersion}
        top={mine}
      />
    </div>
  );
};

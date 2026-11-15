import type { TFunction } from "i18next";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { pickLocalized } from "@shared/lib";
import { Badge } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type {
  CatalogApply,
  CatalogCheck,
  PlannedPack,
  PlannedVersion,
} from "../api/schemas";
import { VERDICT_TONE, shortRevision, sortVersions } from "../lib/report";

const SMALL = { fontSize: "0.71875rem", lineHeight: 1.5 } as const;

const Lines = ({
  items,
  tone,
  label,
}: {
  items: readonly string[];
  tone: "err" | "warn";
  label: string;
}) =>
  items.length === 0 ? null : (
    <ul
      aria-label={label}
      className="mono"
      style={{
        ...SMALL,
        margin: 0,
        paddingLeft: "1rem",
        color: tone === "err" ? "var(--c-err)" : "var(--c-warn)",
        overflowWrap: "anywhere",
      }}
    >
      {items.map((item, index) => (
        <li key={`${String(index)}:${item}`}>{item}</li>
      ))}
    </ul>
  );

const VersionRow = ({ version }: { version: PlannedVersion }) => {
  const { t } = useTranslation("packCatalog");
  return (
    <li
      className="flex flex-col"
      style={{
        gap: "0.25rem",
        padding: "0.375rem 0",
        borderTop: "1px solid var(--border)",
      }}
      data-testid={`catalog-version-${version.template}@${version.version}`}
      data-verdict={version.verdict}
    >
      <div
        className="flex items-center"
        style={{ gap: "0.5rem", flexWrap: "wrap" }}
      >
        <span className="mono" style={{ fontSize: "0.75rem" }}>
          {version.template} {version.version}
        </span>
        <Badge
          variant={VERDICT_TONE[version.verdict]}
          title={t(`verdictHint.${version.verdict}`)}
        >
          {t(`verdict.${version.verdict}`)}
        </Badge>
        {version.kind && (
          <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
            {version.kind}
          </span>
        )}
      </div>
      {version.verdict !== "new" && version.verdict !== "present" && (
        <span className="dim" style={SMALL}>
          {version.verdict === "incompatible" && version.min_studio
            ? t("report.minStudio", { version: version.min_studio })
            : t(`verdictHint.${version.verdict}`)}
        </span>
      )}
      <Lines items={version.errors} tone="err" label={t("report.errors")} />
      <Lines
        items={version.warnings}
        tone="warn"
        label={t("report.warnings")}
      />
    </li>
  );
};

const conflictText = (pack: PlannedPack, t: TFunction): string | null => {
  if (pack.conflict === null) return null;
  if (pack.conflict === "other_source") {
    return pack.conflict_with
      ? t("conflict.other_source", { name: pack.conflict_with })
      : t("conflict.otherSourceUnknown");
  }
  return t(`conflict.${pack.conflict}`);
};

const PackBlock = ({ pack }: { pack: PlannedPack }) => {
  const { t, i18n } = useTranslation("packCatalog");
  const conflict = conflictText(pack, t);
  return (
    <section
      className="card"
      style={{ padding: "0.625rem 0.75rem" }}
      aria-label={pack.id}
      data-testid={`catalog-pack-${pack.id}`}
    >
      <div
        className="flex items-center"
        style={{ gap: "0.5rem", flexWrap: "wrap" }}
      >
        <strong style={{ fontSize: "0.8125rem" }}>
          {pickLocalized(pack.name, i18n.language, pack.id)}
        </strong>
        <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
          {pack.id}
        </span>
        {pack.replaces_builtin && (
          <Badge variant="info">{t("report.replacesBuiltin")}</Badge>
        )}
      </div>
      {conflict && (
        <div style={{ marginTop: "0.375rem" }}>
          <Notice
            tone={pack.conflict === "builtin" ? "warn" : "err"}
            text={conflict}
          />
        </div>
      )}
      <Lines items={pack.problems} tone="err" label={t("report.errors")} />
      {pack.versions.length > 0 && (
        <ul style={{ margin: "0.25rem 0 0", padding: 0, listStyle: "none" }}>
          {sortVersions(pack.versions).map((version) => (
            <VersionRow
              key={`${version.template}@${version.version}`}
              version={version}
            />
          ))}
        </ul>
      )}
    </section>
  );
};

export type CatalogCheckReportProps = {
  check: CatalogCheck;
  /** Под отчётом: пояснение и галочка «Заменить встроенный» у локального подключения. */
  footer?: ReactNode;
};

/**
 * Отчёт «Проверить» (template-studio.md, 10.3): можно ли применять, что мешает словами,
 * по пакам конфликт и вердикт каждой версии с ошибками и предупреждениями. Общий для
 * админки и «Подключить к каталогу» в Студии шаблонов.
 */
export const CatalogCheckReport = ({
  check,
  footer,
}: CatalogCheckReportProps) => {
  const { t } = useTranslation("packCatalog");
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.625rem" }}
      aria-label={t("report.label")}
      data-testid="catalog-check-report"
      data-ok={check.ok ? "true" : "false"}
    >
      {check.ok ? (
        <Notice
          tone="info"
          role="status"
          text={
            check.new_count > 0
              ? t("report.ok", { count: check.new_count })
              : t("report.okNothing")
          }
        />
      ) : (
        <Notice
          tone="err"
          role="alert"
          text={
            <>
              {t("report.blocked")}
              <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1rem" }}>
                {check.blockers.map((blocker) => (
                  <li key={blocker} data-testid={`catalog-blocker-${blocker}`}>
                    {t(`blocker.${blocker}`)}
                  </li>
                ))}
              </ul>
            </>
          }
        />
      )}
      <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
        {t("report.revision", { revision: shortRevision(check.revision) })}
      </span>
      {check.problems.length > 0 && (
        <div className="flex flex-col" style={{ gap: "0.25rem" }}>
          <strong style={{ fontSize: "0.75rem" }}>
            {t("report.problems")}
          </strong>
          <Lines
            items={check.problems}
            tone="warn"
            label={t("report.problems")}
          />
        </div>
      )}
      {check.packs.length === 0 ? (
        <span className="dim" style={SMALL}>
          {t("report.noPacks")}
        </span>
      ) : (
        check.packs.map((pack) => <PackBlock key={pack.id} pack={pack} />)
      )}
      {footer}
    </div>
  );
};

/** Итог «Применить»: какие версии добавлены и какая ревизия применена. */
export const CatalogApplyResult = ({ result }: { result: CatalogApply }) => {
  const { t } = useTranslation("packCatalog");
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.375rem" }}
      data-testid="catalog-apply-result"
    >
      <strong style={{ fontSize: "0.8125rem" }}>{t("applied.title")}</strong>
      {result.added.length > 0 ? (
        <>
          <span style={SMALL}>
            {t("applied.added", { count: result.added.length })}
          </span>
          <ul
            className="mono"
            style={{ ...SMALL, margin: 0, paddingLeft: "1rem" }}
          >
            {result.added.map((key) => (
              <li key={key}>{key}</li>
            ))}
          </ul>
        </>
      ) : (
        <span className="dim" style={SMALL}>
          {t("applied.nothing")}
        </span>
      )}
      <span className="mono dimmer" style={{ fontSize: "0.6875rem" }}>
        {t("applied.revision", { revision: shortRevision(result.revision) })}
      </span>
    </div>
  );
};

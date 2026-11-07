import { Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Section } from "@shared/ui";
import type { DowngradeTarget, UpdateStatus } from "../api/schemas";

export type VersionsSectionProps = {
  data: UpdateStatus;
  busy: boolean;
  onPick: (target: DowngradeTarget) => void;
};

type Row = {
  version: string;
  date: string;
  relation: "current" | "newer" | "older";
  target: DowngradeTarget | null;
  hasDigest: boolean;
};

/** Опубликованные релизы: текущий отмечен, на прежние можно откатиться, если схема базы совпадает. */
export const VersionsSection = ({
  data,
  busy,
  onPick,
}: VersionsSectionProps) => {
  const { t } = useTranslation("adminUpdates");
  const targets = new Map(data.downgrade_targets.map((x) => [x.version, x]));
  const rows: Row[] = data.releases.map((r) => ({
    version: r.version,
    date: r.date,
    relation:
      r.version === data.current_version
        ? "current"
        : targets.has(r.version)
          ? "older"
          : "newer",
    target: targets.get(r.version) ?? null,
    hasDigest: r.has_digest,
  }));
  if (!rows.some((r) => r.relation === "current")) {
    rows.push({
      version: data.current_version,
      date: "",
      relation: "current",
      target: null,
      hasDigest: true,
    });
  }
  const executorOn = data.executor !== "none";
  const blocked =
    busy || !executorOn || !data.updater_online || !data.updater_can_downgrade;
  const why = !executorOn
    ? "manual"
    : !data.updater_online
      ? "offline"
      : !data.updater_can_downgrade
        ? "outdated"
        : null;
  return (
    <Section
      title={t("versions.title")}
      description={t("versions.lead")}
      testId="update-versions"
    >
      {why && (
        <p className="form-hint" data-testid="update-versions-why">
          {t(`versions.why.${why}`)}
        </p>
      )}
      <ul
        className="flex flex-col"
        style={{ gap: "0.5rem", margin: 0, padding: 0, listStyle: "none" }}
        data-testid="update-versions-list"
      >
        {rows.map((row) => {
          const tooOld =
            row.relation === "older" &&
            data.settings.verify !== "none" &&
            !row.hasDigest;
          const disabled =
            blocked || row.target?.compat === "incompatible" || tooOld;
          return (
            <li
              key={row.version}
              className="flex items-center"
              style={{ gap: "0.75rem", flexWrap: "wrap" }}
              data-testid={`update-version-${row.version}`}
              data-relation={row.relation}
            >
              <code>{row.version}</code>
              <span className="dim">{row.date || ""}</span>
              {row.relation === "current" && (
                <strong data-testid="update-version-current-mark">
                  {t("versions.current")}
                </strong>
              )}
              {row.relation === "newer" && (
                <span className="dim">{t("versions.newer")}</span>
              )}
              {row.target && (
                <span
                  className="form-hint"
                  data-testid={`update-version-compat-${row.version}`}
                >
                  {t(`versions.compat.${row.target.compat}`, {
                    revision: row.target.revision ?? "?",
                    current: data.db_revision ?? "?",
                  })}
                </span>
              )}
              {tooOld && (
                <span className="form-hint">{t("versions.noDigest")}</span>
              )}
              {row.target && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={disabled}
                  data-testid={`update-downgrade-${row.version}`}
                  onClick={() => {
                    if (row.target) onPick(row.target);
                  }}
                >
                  <Undo2 size="0.875rem" />
                  {t("versions.rollbackTo", { version: row.version })}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
};

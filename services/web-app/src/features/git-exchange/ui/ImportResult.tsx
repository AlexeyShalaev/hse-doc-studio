import { useTranslation } from "react-i18next";
import type { SyncResult } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { Facts, ResultFrame, type FrameTone } from "@shared/ui/ResultFrame";

export type ImportResultProps = { result: SyncResult };

const toneOf = (outcome: string): FrameTone => {
  if (outcome === "conflicts") return "warn";
  if (outcome === "up_to_date") return "info";
  return "ok";
};

// Что получилось после импорта: сколько версий и файлов пришло, что Студия
// объединила сама и осталось ли решить конфликты.
export const ImportResult = ({ result }: ImportResultProps) => {
  const { t } = useTranslation("gitExchange");
  const outcome = result.outcome;
  const conflicts = result.conflicts;
  const known = ["up_to_date", "fast_forwarded", "merged", "conflicts"];
  const key = known.includes(outcome) ? outcome : "merged";

  const facts: [string, string][] = [];
  if (outcome !== "up_to_date") {
    facts.push([t("import.result.versions"), String(result.pulled_commits)]);
    facts.push([t("import.result.files"), String(result.files_changed)]);
    if (result.auto.length > 0) {
      facts.push([t("import.result.auto"), String(result.auto.length)]);
    }
  }

  return (
    <ResultFrame
      tone={toneOf(outcome)}
      role="status"
      title={t(`import.result.${key}.title`)}
      testId={`import-result-${key}`}
    >
      <p style={{ margin: 0 }}>
        {key === "conflicts"
          ? t("import.result.conflicts.text", {
              count: conflicts?.files_open ?? 0,
            })
          : t(`import.result.${key}.text`)}
      </p>
      {facts.length > 0 && <Facts items={facts} />}
      {result.warnings.map((warning) => (
        <Notice
          key={warning.code}
          tone="warn"
          role="status"
          text={t(`gitSync:warning.${warning.code}`, {
            defaultValue: warning.code,
          })}
        />
      ))}
    </ResultFrame>
  );
};

import { useEffect, useState } from "react";
import { Play, ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  usePackPreviewBuild,
  usePackPreviewOptions,
  useStartPackPreview,
  type PackPreviewBuild,
  type PackVersionRef,
} from "@entities/pack-studio";
import {
  documentFits,
  effectiveCombination,
  exampleOf,
  selectionKey,
  usePreviewSelection,
} from "@features/pack-preview";
import { pickLocalized } from "@shared/lib";
import { Button, Select, Spinner } from "@shared/ui";

export type CheckOnPreviewProps = {
  workspaceId: string;
  versionRef: PackVersionRef;
  /** Документы, к которым относятся правила (пусто: все документы версии). */
  documents: readonly string[];
  /** Сборка с проверками закончилась (или её ещё нет: null). */
  onBuild: (build: PackPreviewBuild | null) => void;
  build: PackPreviewBuild | null;
};

/**
 * «Проверить на предпросмотре» (5.7): сборка документа в комбинации предпросмотра с правилами
 * проверок версии, тем же движком, что у проекта. Набор данных и переключатели общие с вкладкой
 * предпросмотра; находки форма показывает у правил.
 */
export const CheckOnPreview = ({
  workspaceId,
  versionRef,
  documents,
  onBuild,
  build,
}: CheckOnPreviewProps) => {
  const { t, i18n } = useTranslation("packStudio");
  const options = usePackPreviewOptions(workspaceId, versionRef);
  const { selection } = usePreviewSelection(
    selectionKey(workspaceId, versionRef),
  );
  const start = useStartPackPreview(workspaceId);
  const [buildId, setBuildId] = useState<string | null>(null);
  const [document, setDocument] = useState<string | null>(null);
  const polled = usePackPreviewBuild(workspaceId, buildId);
  const current = polled.data ?? null;
  const finished =
    current && current.status !== "queued" && current.status !== "running"
      ? current
      : null;
  useEffect(() => {
    if (finished) onBuild(finished);
  }, [finished, onBuild]);

  if (!options.data) {
    return options.isPending ? <Spinner size="sm" /> : null;
  }
  const opts = options.data;
  const example = exampleOf(opts, selection.example);
  const combination = effectiveCombination(opts, example, selection.overrides);
  const docs = opts.documents.filter(
    (doc) =>
      (documents.length === 0 || documents.includes(doc.id)) &&
      documentFits(doc, combination),
  );
  const chosen = docs.find((doc) => doc.id === document) ?? docs[0];
  const running = current?.status === "queued" || current?.status === "running";
  const findings = build?.checks?.length ?? 0;

  return (
    <div className="pcf-run" data-testid="checks-run">
      <div className="pcf-run-row">
        <ScanSearch size="0.875rem" aria-hidden="true" />
        <Select
          value={chosen?.id ?? ""}
          onValueChange={setDocument}
          isDisabled={docs.length === 0}
          ariaLabel={t("checksForm.run.document")}
          placeholder={t("checksForm.run.noDocuments")}
          options={docs.map((doc) => ({
            value: doc.id,
            label: pickLocalized(doc.name, i18n.language, doc.id),
          }))}
        />
        <Button
          size="xs"
          disabled={!chosen || start.isPending || running}
          onClick={() => {
            if (!chosen) return;
            onBuild(null);
            start.mutate(
              {
                ref: versionRef,
                body: {
                  documents: [chosen.id],
                  example: example?.id ?? opts.default_example,
                  combination,
                  checks: true,
                },
              },
              {
                onSuccess: (builds) => {
                  setBuildId(builds[0]?.id ?? null);
                },
              },
            );
          }}
          data-testid="checks-run-start"
        >
          {start.isPending || running ? (
            <Spinner size="sm" />
          ) : (
            <Play size="0.6875rem" />
          )}
          {t("checksForm.run.start")}
        </Button>
      </div>
      <p className="hint">{t("checksForm.run.hint")}</p>
      {start.isError && (
        <p className="hint pcf-warn">{packErrorText(start.error)}</p>
      )}
      {running && <p className="hint">{t("checksForm.run.running")}</p>}
      {build?.status === "failed" && (
        <p className="hint pcf-warn" data-testid="checks-run-failed">
          {t("checksForm.run.failed", { code: build.error?.code ?? "" })}
        </p>
      )}
      {build?.status === "succeeded" && (
        <p className="hint" data-testid="checks-run-done">
          {findings === 0
            ? t("checksForm.run.clean")
            : t("checksForm.run.found", { count: findings })}
        </p>
      )}
    </div>
  );
};

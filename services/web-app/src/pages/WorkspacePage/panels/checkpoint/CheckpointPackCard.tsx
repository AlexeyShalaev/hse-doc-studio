import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  CheckCircle,
  Package,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import {
  useCreateSubmission,
  useSubmissionCustomFilePreflight,
} from "@entities/submission";
import { useArchiveFormats, type ArchiveFormatId } from "@entities/system";
import { useVersionDetail } from "@entities/template-catalog";
import { CustomFileDecisionsModal } from "@features/custom-document";
import type { CustomFilePreflightItemDto } from "@shared/api/types";
import { Spinner } from "@shared/ui/Spinner";
import { isMetaValueBlank, pickLocalized, toast } from "@shared/lib";

type Project = z.infer<typeof ProjectResponseSchema>;

/** Пункт профиля в том виде, в каком он уходит в запрос на сборку. */
export type PackItem = {
  doc_id: string;
  signatures: string[];
};

export type CheckpointPackCardProps = {
  project: Project;
  /** Точка, пакет которой собираем. Экран ОДИН, селектора профиля здесь нет. */
  profileId: string;
  /**
   * Пункты, которые реально уйдут в архив: гейты вида работы и NDA уже
   * применены расчётом готовности, а неинстанцированные документы отброшены.
   */
  packedItems: readonly PackItem[];
  isTeam: boolean;
  authors: readonly { slug: string; name: string }[];
  selectedAuthorSlug: string | null;
  onSelectAuthor: (slug: string | null) => void;
};

type PreflightProps = {
  ok: boolean;
  warn?: boolean;
  label: string;
};

const Preflight = ({ ok, warn, label }: PreflightProps) => {
  let Ic: LucideIcon = XCircle;
  let col = "var(--c-err)";
  if (ok) {
    Ic = CheckCircle;
    col = "var(--c-ok)";
  } else if (warn) {
    Ic = AlertTriangle;
    col = "var(--c-warn)";
  }
  return (
    <div className="flex items-start gap-2" style={{ fontSize: 12 }}>
      <Ic size={12} style={{ color: col, flexShrink: 0, marginTop: 3 }} />
      <span style={{ color: "var(--fg-1)" }}>{label}</span>
    </div>
  );
};

/**
 * Правая колонка экрана контрольной точки: всё, что нужно, чтобы собрать пакет
 * именно этой точки. Раньше это был отдельный экран «Упаковка» со своим
 * селектором профиля и своей копией списка документов — по сути та же страница
 * во второй раз. Точка и её упаковка неразделимы, поэтому и экран один.
 */
export const CheckpointPackCard = ({
  project,
  profileId,
  packedItems,
  isTeam,
  authors,
  selectedAuthorSlug,
  onSelectAuthor,
}: CheckpointPackCardProps) => {
  const { t } = useTranslation("workspace");
  const lang = project.lang ?? "ru";
  const isNda = project.meta?.nda === true;
  const supervisorOk = Boolean(project.supervisor?.name);

  const { data: archiveFormats } = useArchiveFormats();
  const { data: versionDetail } = useVersionDetail(
    project.lock.pack_id,
    project.lock.template_id,
    project.lock.version,
  );
  const { mutate: createSubmission, isPending: creating } =
    useCreateSubmission();
  const { mutateAsync: preflightCustomFiles, isPending: preflighting } =
    useSubmissionCustomFilePreflight();

  const [selectedFormat, setSelectedFormat] = useState<ArchiveFormatId | null>(
    null,
  );
  // Результат preflight показываем только непустым — модалка решений это
  // временное состояние экрана, а не стора.
  const [customDecisionsItems, setCustomDecisionsItems] = useState<
    CustomFilePreflightItemDto[] | null
  >(null);

  const formatList = archiveFormats?.formats ?? [];
  const firstAvailableFormat = formatList.find((f) => f.available)?.id ?? "zip";
  const effectiveFormat: ArchiveFormatId =
    selectedFormat ?? firstAvailableFormat;

  // Обязательные метаданные (create/finalize), оставшиеся пустыми. Только
  // предупреждение: как и остальные строки preflight, упаковку не блокирует.
  // Поля-персоны исключены — у руководителя своя строка.
  const missingMetaLabels = Object.entries(versionDetail?.meta_fields ?? {})
    .filter(
      ([key, def]) =>
        def.type !== "person" &&
        (def.required_at === "create" || def.required_at === "finalize") &&
        isMetaValueBlank(project.meta?.[key]),
    )
    .map(([key, def]) => pickLocalized(def.label, lang, key));
  const metaOk = missingMetaLabels.length === 0;

  const canPack = !isTeam || selectedAuthorSlug != null;

  const submitPack = (customDocDecisions?: Record<string, boolean>) => {
    // author_slug обязателен для командной сдачи — без него не отправляем.
    if (!canPack) return;
    createSubmission(
      {
        projectId: project.id,
        data: {
          profile_id: profileId,
          archive_format: effectiveFormat,
          items: packedItems.map((it) => ({
            doc_id: it.doc_id,
            signatures: it.signatures,
          })),
          ...(isTeam && selectedAuthorSlug != null
            ? { author_slug: selectedAuthorSlug }
            : {}),
          ...(customDocDecisions
            ? { custom_doc_decisions: customDocDecisions }
            : {}),
        },
      },
      {
        onSuccess: () => {
          setCustomDecisionsItems(null);
          toast.success(t("pack.submissionCreated"));
        },
      },
    );
  };

  const handlePack = () => {
    if (!canPack) return;
    preflightCustomFiles({
      projectId: project.id,
      params: {
        profile_id: profileId,
        archive_format: effectiveFormat,
        ...(isTeam && selectedAuthorSlug != null
          ? { author_slug: selectedAuthorSlug }
          : {}),
      },
    })
      .then((result) => {
        if (result.length === 0) {
          // Ни грамма лишнего трения в самом частом случае: своих файлов в
          // пакете нет вовсе.
          submitPack();
        } else {
          setCustomDecisionsItems(result);
        }
      })
      .catch(() => {
        toast.error(t("pack.preflightFailed"));
      });
  };

  return (
    <>
      <div className="card" style={{ padding: 18 }}>
        <strong style={{ display: "block", marginBottom: 6, fontSize: 13 }}>
          {t("pack.projectFolder")}
        </strong>
        <div
          className="mono dim"
          style={{ fontSize: 11.5, marginBottom: 14, wordBreak: "break-all" }}
          title={project.folder}
        >
          {project.folder}
        </div>

        {isTeam && (
          <div
            className="flex flex-col"
            style={{
              gap: 6,
              paddingTop: 12,
              borderTop: "1px dashed var(--border)",
            }}
          >
            <label className="field" style={{ gap: 6 }}>
              <span style={{ fontSize: 11, color: "var(--fg-2)" }}>
                {t("pack.packAuthor")}
              </span>
              <select
                className="input"
                style={{ fontSize: 12, padding: "7px 10px" }}
                value={selectedAuthorSlug ?? ""}
                onChange={(e) => {
                  onSelectAuthor(e.target.value || null);
                }}
              >
                {authors.length === 0 && (
                  <option value="">{t("pack.noPackAuthors")}</option>
                )}
                {authors.map((a) => (
                  <option key={a.slug} value={a.slug}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <p
              className="dim"
              style={{ margin: 0, fontSize: 10.5, lineHeight: 1.5 }}
            >
              {t("pack.packAuthorHint")}
            </p>
          </div>
        )}

        <label
          className="field"
          style={{
            gap: 6,
            paddingTop: 12,
            marginTop: 12,
            borderTop: "1px dashed var(--border)",
          }}
        >
          <span style={{ fontSize: 11, color: "var(--fg-2)" }}>
            {t("pack.archiveFormat")}
          </span>
          <select
            className="input"
            style={{ fontSize: 12, padding: "7px 10px" }}
            value={effectiveFormat}
            onChange={(e) => {
              setSelectedFormat(e.target.value as ArchiveFormatId);
            }}
          >
            {formatList.length === 0 && <option value="zip">ZIP</option>}
            {formatList.map((f) => (
              <option key={f.id} value={f.id} disabled={!f.available}>
                {f.available
                  ? f.label
                  : t("pack.noUtility", { label: f.label })}
              </option>
            ))}
          </select>
        </label>

        <div
          className="flex flex-col gap-2"
          style={{
            paddingTop: 12,
            marginTop: 12,
            borderTop: "1px dashed var(--border)",
          }}
        >
          <Preflight ok={supervisorOk} label={t("pack.preflightSupervisor")} />
          <Preflight
            ok={metaOk}
            warn={!metaOk}
            label={
              metaOk
                ? t("pack.preflightMetaOk")
                : t("pack.preflightMetaMissing", {
                    fields: missingMetaLabels.join(", "),
                  })
            }
          />
          <Preflight
            ok={!isNda}
            warn={isNda}
            label={
              isNda
                ? t("pack.preflightNdaNeedsSignatures")
                : t("pack.preflightNdaNotRequired")
            }
          />
        </div>

        <button
          type="button"
          className="btn primary lg"
          style={{ width: "100%", marginTop: 16 }}
          onClick={handlePack}
          disabled={creating || preflighting || !canPack}
        >
          {creating || preflighting ? (
            <Spinner size="sm" />
          ) : (
            <Package size={13} />
          )}
          {t("pack.pack")}
        </button>
      </div>

      {customDecisionsItems && (
        <CustomFileDecisionsModal
          isOpen={true}
          items={customDecisionsItems}
          lang={lang}
          onClose={() => {
            setCustomDecisionsItems(null);
          }}
          onConfirm={(decisions) => {
            submitPack(decisions);
          }}
          isSubmitting={creating}
        />
      )}
    </>
  );
};

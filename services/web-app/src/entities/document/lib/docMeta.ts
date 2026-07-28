import { i18n, pickLocalized } from "@shared/lib";

export type DocMeta = {
  code: string;
  name: string;
  file: string;
  out: string;
  gost: string;
};

// Per-type code/name come from the `documents` namespace (so they follow the
// interface language), while the structural fields (file paths, GOST refs)
// stay literal here.
type DocMetaStatic = {
  file: string;
  out: string;
  gost: string;
};

// Keyed by the pack DEFINITION id (= the document folder name). For real docs
// the API supplies source_file/output_file/gost_ref, so these are fallbacks;
// they stay in sync with the folder-name doc ids.
const DOC_META_STATIC: Record<string, DocMetaStatic> = {
  technical_specification: {
    file: "technical_specification/technical_specification.tex",
    out: "technical_specification/technical_specification.pdf",
    gost: "ГОСТ 19.201-78",
  },
  shared_technical_specification: {
    file: "shared_technical_specification/shared_technical_specification.tex",
    out: "shared_technical_specification/shared_technical_specification.pdf",
    gost: "ГОСТ 19.201-78",
  },
  thesis: {
    file: "thesis/thesis.tex",
    out: "thesis/thesis.pdf",
    gost: "ГОСТ 7.32-2017",
  },
  annotation: {
    file: "annotation/annotation.tex",
    out: "annotation/annotation.pdf",
    gost: "ГОСТ 7.32-2017",
  },
  shared_annotation: {
    file: "shared_annotation/shared_annotation.tex",
    out: "shared_annotation/shared_annotation.pdf",
    gost: "ГОСТ 7.32-2017",
  },
  explanatory_note: {
    file: "explanatory_note/explanatory_note.tex",
    out: "explanatory_note/explanatory_note.pdf",
    gost: "ГОСТ 19.404-79",
  },
  test_program_and_methodology: {
    file: "test_program_and_methodology/test_program_and_methodology.tex",
    out: "test_program_and_methodology/test_program_and_methodology.pdf",
    gost: "ГОСТ 19.301-79",
  },
  shared_test_program_and_methodology: {
    file: "shared_test_program_and_methodology/shared_test_program_and_methodology.tex",
    out: "shared_test_program_and_methodology/shared_test_program_and_methodology.pdf",
    gost: "ГОСТ 19.301-79",
  },
  source_listing: {
    file: "source_listing/source_listing.tex",
    out: "source_listing/source_listing.pdf",
    gost: "ГОСТ 19.401-78",
  },
  programmer_manual: {
    file: "programmer_manual/programmer_manual.tex",
    out: "programmer_manual/programmer_manual.pdf",
    gost: "ГОСТ 19.504-79",
  },
  operator_manual: {
    file: "operator_manual/operator_manual.tex",
    out: "operator_manual/operator_manual.pdf",
    gost: "ГОСТ 19.505-79",
  },
  presentation: {
    file: "presentation/beamer/presentation.tex",
    // latexmk drops the beamer PDF next to its source; variant-specific real
    // paths (pptx/reveal) come from the API and take priority anyway.
    out: "presentation/beamer/presentation.pdf",
    gost: "—",
  },
  project_proposal: {
    file: "project_proposal/project_proposal.tex",
    out: "project_proposal/project_proposal.pdf",
    gost: "—",
  },
  nda: { file: "nda/nda.tex", out: "nda/nda.pdf", gost: "—" },
};

// A DocumentResponse from the API satisfies this shape, so call sites should
// pass the whole document when they have one: its source_file/output_file are
// ready project-root-relative paths (team layouts prefix the author's base
// folder), def_id resolves the localized type name, and owner_name marks whose
// personal instance it is.
export type DocDefLike = {
  def_id?: string | null | undefined;
  owner_name?: string | null | undefined;
  source_file?: string | null | undefined;
  output_file?: string | null | undefined;
  gost_ref?: string | null | undefined;
  name?: Record<string, string> | null | undefined;
  code?: Record<string, string> | null | undefined;
};

export const getDocMeta = (
  docId: string,
  def?: DocDefLike,
  lang: "ru" | "en" = "ru",
): DocMeta => {
  // Team-mode personal docs are instances "{def_id}--{slug}". The localized
  // type name/code and the static per-type fallbacks resolve by the pack
  // DEFINITION id (from the API when present, else the instance-id base) —
  // never by the raw instance id.
  const typeKey = (def?.def_id ?? docId.split("--")[0] ?? docId).toLowerCase();
  const staticMeta = DOC_META_STATIC[typeKey];
  const fallback: DocMeta = staticMeta
    ? {
        code: i18n.t(`documents:type.${typeKey}.code`),
        name: i18n.t(`documents:type.${typeKey}.name`),
        ...staticMeta,
      }
    : {
        code: typeKey.toUpperCase(),
        name: typeKey,
        // Legacy layout fallback for solo/unknown docs; team instances always
        // carry API paths, which take precedence below.
        file: `${docId}/${docId}.tex`,
        out: `${docId}/${docId}.pdf`,
        gost: "—",
      };
  if (!def) return fallback;

  const name = pickLocalized(def.name ?? undefined, lang, fallback.name);
  return {
    code: pickLocalized(def.code ?? undefined, lang, fallback.code),
    // Per-author instances show whose document it is right in the title.
    name: def.owner_name ? `${name} — ${def.owner_name}` : name,
    file: def.source_file ?? fallback.file,
    out: def.output_file ?? fallback.out,
    gost: def.gost_ref ?? fallback.gost,
  };
};

export type DocStatus = "draft" | "building" | "ok" | "warn" | "err" | "locked";

export type StatusMeta = {
  sev: "ok" | "warn" | "err" | "info";
  label: string;
};

export const getStatusMeta = (status: DocStatus): StatusMeta => {
  switch (status) {
    case "ok":
      return { sev: "ok", label: i18n.t("documents:status.ok") };
    case "warn":
      return { sev: "warn", label: i18n.t("documents:status.warn") };
    case "err":
      return { sev: "err", label: i18n.t("documents:status.err") };
    case "building":
      return { sev: "info", label: i18n.t("documents:status.building") };
    case "locked":
      return { sev: "info", label: i18n.t("documents:status.locked") };
    case "draft":
    default:
      return { sev: "info", label: i18n.t("documents:status.draft") };
  }
};

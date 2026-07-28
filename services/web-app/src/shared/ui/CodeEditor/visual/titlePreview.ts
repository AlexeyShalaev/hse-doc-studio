import type { VisualEmbeddedInputKind } from "../types";

export type EspdTitlePreview = {
  kind: "titlePages";
  projectName: string;
  documentName: string;
  documentCode: string;
  approvalCode: string;
  supervisorName: string;
  supervisorRole: string;
  coSupervisorName: string | null;
  coSupervisorRole: string | null;
  academicSupervisorName: string;
  academicSupervisorRole: string;
  executors: string;
  executorGroup: string;
  year: string;
  sourceLineCount: number | null;
};

export type VkrTitlePreview = {
  kind: "vkrTitle";
  faculty: string;
  specialization: string;
  udc: string;
  programCode: string;
  projectName: string;
  academicSupervisorName: string;
  academicSupervisorRole: string;
  supervisorName: string;
  supervisorRole: string;
  supervisorDegree: string;
  coSupervisorName: string | null;
  coSupervisorRole: string | null;
  coSupervisorDegree: string | null;
  authorName: string;
  group: string;
  course: string;
  degreeLevel: string;
  city: string;
  year: string;
  sourceLineCount: number | null;
};

export type TitlePreview = EspdTitlePreview | VkrTitlePreview;

const stripLatexValue = (value: string): string => {
  let text = value.trim();
  for (let pass = 0; pass < 5; pass += 1) {
    const next = text
      .replace(/\\hseFill\{([^{}]*)\}/g, "‹$1›")
      .replace(/\\hseOptional\{([^{}]*)\}/g, "$1")
      .replace(
        /\\(?:textbf|textit|emph|underline|textrm|textsf|texttt|mbox|strut)\*?\{([^{}]*)\}/g,
        "$1",
      );
    if (next === text) break;
    text = next;
  }
  return text
    .replace(/\\ /g, " ")
    .replace(/\\([%&#_$])/g, "$1")
    .replace(/~/g, " ")
    .replace(/\\[A-Za-z@]+\*?/g, "")
    .replace(/[{}]/g, "")
    .replace(/\s+/g, " ")
    .trim();
};

const macro = (
  macros: Readonly<Record<string, string>>,
  names: readonly string[],
  fallback = "—",
): string => {
  for (const name of names) {
    const value = macros[name];
    if (value === undefined) continue;
    const plain = stripLatexValue(value);
    if (plain !== "") return plain;
  }
  return fallback;
};

const optionalMacro = (
  macros: Readonly<Record<string, string>>,
  names: readonly string[],
): string | null => {
  const value = macro(macros, names, "");
  return value === "" ? null : value;
};

const sourceLineCount = (source: string | undefined): number | null =>
  source === undefined ? null : source.split(/\r?\n/).length;

export const buildTitlePreview = (
  kind: Extract<VisualEmbeddedInputKind, "titlePages" | "vkrTitle">,
  macros: Readonly<Record<string, string>>,
  source: string | undefined,
): TitlePreview => {
  if (kind === "vkrTitle") {
    return {
      kind,
      faculty: macro(macros, ["hseFaculty"], "Факультет компьютерных наук"),
      specialization: macro(macros, ["hseSpecialization"]),
      udc: macro(macros, ["hseUDC"], "004"),
      programCode: macro(macros, ["hseProgramCode"], "09.03.04"),
      projectName: macro(macros, ["hseProjectName", "projectname"]),
      academicSupervisorName: macro(macros, [
        "hseAcademicSupervisorName",
        "academicsupervisorname",
      ]),
      academicSupervisorRole: macro(macros, [
        "hseAcademicSupervisorTitle",
        "academicsupervisorrole",
      ]),
      supervisorName: macro(macros, [
        "hseSupervisorName",
        "scientificadvisorname",
      ]),
      supervisorRole: macro(macros, [
        "hseSupervisorTitle",
        "scientificadvisorrole",
      ]),
      supervisorDegree: macro(macros, ["hseSupervisorDegree"]),
      coSupervisorName: optionalMacro(macros, [
        "hseCoSupervisorName",
        "coscientificadvisorname",
      ]),
      coSupervisorRole: optionalMacro(macros, [
        "hseCoSupervisorTitle",
        "coscientificadvisorrole",
      ]),
      coSupervisorDegree: optionalMacro(macros, ["hseCoSupervisorDegree"]),
      authorName: macro(macros, ["hseAuthorName", "studentname"]),
      group: macro(macros, ["hseGroup", "studentgroup"]),
      course: macro(macros, ["hseCourse"], "4"),
      degreeLevel: macro(macros, ["hseDegreeLevel"], "бакалавриата"),
      city: macro(macros, ["hseCity"], "Москва"),
      year: macro(macros, ["hseYear", "yearval"]),
      sourceLineCount: sourceLineCount(source),
    };
  }

  return {
    kind,
    projectName: macro(macros, ["projectname", "hseProjectName"]),
    documentName: macro(macros, ["docname"]),
    documentCode: macro(macros, ["doccode"]),
    approvalCode: macro(macros, ["doccodelu"]),
    supervisorName: macro(macros, [
      "scientificadvisorname",
      "hseSupervisorName",
    ]),
    supervisorRole: macro(macros, [
      "scientificadvisorrole",
      "hseSupervisorTitle",
    ]),
    coSupervisorName: optionalMacro(macros, [
      "coscientificadvisorname",
      "hseCoSupervisorName",
    ]),
    coSupervisorRole: optionalMacro(macros, [
      "coscientificadvisorrole",
      "hseCoSupervisorTitle",
    ]),
    academicSupervisorName: macro(macros, [
      "academicsupervisorname",
      "hseAcademicSupervisorName",
    ]),
    academicSupervisorRole: macro(macros, [
      "academicsupervisorrole",
      "hseAcademicSupervisorTitle",
    ]),
    executors: macro(macros, [
      "hseAuthorsList",
      "studentname",
      "hseAuthorName",
    ]),
    executorGroup: macro(macros, ["studentgroup", "hseGroup"]),
    year: macro(macros, ["yearval", "hseYear"]),
    sourceLineCount: sourceLineCount(source),
  };
};

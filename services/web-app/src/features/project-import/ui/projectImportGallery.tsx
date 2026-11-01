import type { ProjectImportResult } from "@entities/session";
import type { GalleryEntry, GalleryGroup } from "@shared/lib/stateGallery";
import type { ImportFailure } from "../model/useProjectImport";
import {
  ProjectImportView,
  type ProjectImportViewProps,
} from "./ProjectImportView";

const W = 560;
const noop = () => undefined;
const FILE = { name: "thesis-bertie.zip", size: 48_300_000 };

const CLEAN: ProjectImportResult = {
  project_id: "0b5d2a3e-3c1f-4d0e-9a52-1f2b7a6c9d10",
  name: "Курсовая: анализ данных",
  id_regenerated: false,
  files: 42,
  bytes: 3_145_728,
  chats: 2,
  warnings: [],
};
const NOISY: ProjectImportResult = {
  project_id: "7c1e9f40-5b8a-4c3d-8e21-6a9d0b4f2e73",
  name: "ВКР: распределённые системы",
  id_regenerated: true,
  files: 311,
  bytes: 52_428_800,
  chats: 0,
  warnings: [
    { code: "remote_needs_access", detail: "" },
    { code: "records_skipped", detail: "6" },
    { code: "store_hardened", detail: "2" },
    { code: "junk_skipped", detail: "4" },
  ],
};

const failure = (code: string): ImportFailure => ({ code, detail: "" });

const entry = (
  id: string,
  title: string,
  props: Partial<ProjectImportViewProps>,
): GalleryEntry => ({
  id,
  title,
  frame: "window",
  width: W,
  render: () => (
    <div style={{ padding: 24 }}>
      <ProjectImportView
        stage="idle"
        file={null}
        percent={0}
        result={null}
        failure={null}
        onPick={noop}
        {...props}
      />
    </div>
  ),
});

/** Окно «Импорт проекта из локальной Студии»: все шаги и отказы. */
export const getProjectImportGallery = (): GalleryGroup[] => [
  {
    id: "project-import",
    title: "Импорт проекта из zip",
    entries: [
      entry("import_choose", "Выбор файла", {}),
      entry("import_file", "Файл выбран", { file: FILE }),
      entry("import_uploading", "Загрузка 42%", {
        stage: "uploading",
        file: FILE,
        percent: 42,
      }),
      entry("import_unpacking", "Сервер распаковывает и проверяет", {
        stage: "uploading",
        file: FILE,
        percent: 100,
      }),
      entry("import_done", "Готово: чисто", { stage: "done", result: CLEAN }),
      entry("import_done_warnings", "Готово: новый id и предупреждения", {
        stage: "done",
        result: NOISY,
      }),
      entry("import_unsafe", "Отказ: опасный архив", {
        stage: "failed",
        file: FILE,
        failure: failure("import_archive_unsafe"),
      }),
      entry("import_too_large", "Отказ: слишком большой", {
        stage: "failed",
        file: FILE,
        failure: failure("import_too_large"),
      }),
      entry("import_no_project", "Отказ: в архиве нет проекта", {
        stage: "failed",
        file: FILE,
        failure: failure("import_no_project"),
      }),
      entry("import_newer", "Отказ: проект новее сервера", {
        stage: "failed",
        file: FILE,
        failure: failure("import_project_newer"),
      }),
      entry("import_invalid", "Отказ: не zip", {
        stage: "failed",
        file: FILE,
        failure: failure("import_archive_invalid"),
      }),
      entry("import_network", "Отказ: обрыв связи", {
        stage: "failed",
        file: FILE,
        failure: failure("network"),
      }),
    ],
  },
];

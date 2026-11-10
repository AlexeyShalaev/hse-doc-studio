import { useMemo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { getDocMeta, useDocuments } from "@entities/document";
import { isReadOnlyRole, useProject } from "@entities/project";
import { useBootstrap } from "@entities/session";
import {
  RouteEditGuardProvider,
  folderOf,
  type GuardDoc,
} from "@entities/signing-route";

/**
 * Мягкое предупреждение правки документов на подписании (signing-route.md, 12.7) на всю рабочую
 * область проекта: редактор, сборка, файлы, поля проекта и обновление шаблона спрашивают через
 * одно окно. Маршруты есть только на сервере у вошедшего, который правит проект; по ссылке и
 * читателю вопрос не нужен.
 */
export const RouteGuardScope = ({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) => {
  const { i18n } = useTranslation();
  const boot = useBootstrap().data;
  const { data: project } = useProject(projectId);
  const { data: documents } = useDocuments(projectId);
  const enabled =
    boot?.mode === "server" &&
    boot.user != null &&
    project !== undefined &&
    project.via_link !== true &&
    !isReadOnlyRole(project.my_role ?? null);
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  const docs = useMemo<GuardDoc[]>(
    () =>
      (documents ?? []).map((doc) => {
        const meta = getDocMeta(doc.id, doc, lang);
        return { id: doc.id, name: meta.name, folder: folderOf(meta.file) };
      }),
    [documents, lang],
  );
  return (
    <RouteEditGuardProvider projectId={projectId} enabled={enabled} docs={docs}>
      {children}
    </RouteEditGuardProvider>
  );
};

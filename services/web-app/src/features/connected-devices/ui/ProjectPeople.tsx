import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { getDocMeta, useDocuments } from "@entities/document";
import {
  pickPeople,
  useProjectPeople,
  useStudioLink,
  usePlaceStore,
  type PersonOnline,
  type Place,
} from "@entities/connected-device";
import { useBootstrap } from "@entities/session";
import { PeopleOnline } from "./PeopleOnline";

export type ProjectPeopleProps = {
  projectId: string;
  /** Открытый документ проекта; null, когда в окне не документ. */
  docId: string | null;
};

const useDocNames = (projectId: string) => {
  const { i18n } = useTranslation();
  const { data: documents } = useDocuments(projectId);
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  return useCallback(
    (id: string): string | null => {
      const doc = documents?.find((d) => d.id === id);
      return doc === undefined ? null : getDocMeta(doc.id, doc, lang).name;
    },
    [documents, lang],
  );
};

const useOpenDoc = (projectId: string) => {
  const navigate = useNavigate();
  return useCallback(
    (person: PersonOnline) => {
      if (person.doc_id === null) return;
      void navigate(`/projects/${projectId}/documents/${person.doc_id}`);
    },
    [navigate, projectId],
  );
};

const CloudPeople = ({ projectId, docId }: ProjectPeopleProps) => {
  const stored = usePlaceStore();
  const activity =
    docId !== null
      ? stored.docId === docId
        ? stored.activity
        : "viewing"
      : "browsing";
  const place = useMemo<Place>(() => ({ activity, docId }), [activity, docId]);
  const people = useProjectPeople(projectId, place);
  const docName = useDocNames(projectId);
  const open = useOpenDoc(projectId);
  if (people.data === undefined) return null;
  return (
    <PeopleOnline people={people.data} docName={docName} onOpenDoc={open} />
  );
};

/**
 * Локальная Студия: те же люди, что видит облако, приходят в ответе `studio-link` (его опрашивает плашка Студии),
 * своих запросов нет. Без входа на сервер, без проекта в облаке или без права на исходники списка нет.
 */
const LocalPeople = ({ projectId }: ProjectPeopleProps) => {
  const link = useStudioLink(projectId);
  const docName = useDocNames(projectId);
  const open = useOpenDoc(projectId);
  const people = pickPeople(link.data);
  if (people === null) return null;
  return <PeopleOnline people={people} docName={docName} onOpenDoc={open} />;
};

/** Аватары людей, которые сейчас в проекте, в шапке рабочего места: в облаке и в локальной Студии. */
export const ProjectPeople = (props: ProjectPeopleProps) => {
  const mode = useBootstrap().data?.mode;
  if (mode === "server") return <CloudPeople {...props} />;
  if (mode === "local") return <LocalPeople {...props} />;
  return null;
};

import { useRef, useState, type ComponentType } from "react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { sectionOfPointer, useRecordFocus } from "../lib/focus";
import { DocumentsSection } from "./documents/DocumentsSection";
import { LanguagesSection } from "./documents/LanguagesSection";
import { FieldsSection } from "./fields/FieldsSection";
import { ChecksSection } from "./checks/ChecksSections";
import { FormsSection } from "./forms/FormsSection";
import { SubmissionSection } from "./submission/SubmissionSection";

/** Что раздел формы версии получает от вкладки «Форма» (модель и правки берёт из useModelEditor). */
export type VersionSectionProps = {
  workspaceId: string;
  path: string;
  onSaved: (changed: string[]) => void;
  /** Открыть файл пространства в редакторе (манифест документа из ростера). */
  onOpenFile?: ((path: string) => void) | undefined;
  /** Указатель JSON записи, которую нужно показать (переход к правилу): раздел и выделение. */
  at?: string | null | undefined;
};

/**
 * Разделы формы манифеста версии (5.1): каждый срез добавляет свой раздел сюда
 * (T11 поля и анкеты, T12 документы и языки, T13 сдача и подписи).
 */
export const VERSION_SECTIONS: {
  id: string;
  Component: ComponentType<VersionSectionProps>;
}[] = [
  { id: "fields", Component: FieldsSection },
  { id: "forms", Component: FormsSection },
  { id: "documents", Component: DocumentsSection },
  { id: "languages", Component: LanguagesSection },
  { id: "submission", Component: SubmissionSection },
  { id: "checks", Component: ChecksSection },
];

export const VersionForm = (props: VersionSectionProps) => {
  const { t } = useTranslation("packForms");
  const [active, setActive] = useState(
    sectionOfPointer(props.at) ?? VERSION_SECTIONS[0]?.id ?? "",
  );
  const section =
    VERSION_SECTIONS.find((s) => s.id === active) ?? VERSION_SECTIONS[0];
  const root = useRef<HTMLDivElement>(null);
  useRecordFocus(root, props.at, section?.id ?? "");
  return (
    <div className="pf-version" ref={root}>
      <nav className="pf-tabs" role="tablist" aria-label={t("sections")}>
        {VERSION_SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={s.id === section?.id}
            className={clsx("pf-tab", s.id === section?.id && "active")}
            data-testid={`pf-tab-${s.id}`}
            onClick={() => {
              setActive(s.id);
            }}
          >
            {t(`tabs.${s.id}`)}
          </button>
        ))}
      </nav>
      {section && <section.Component {...props} />}
    </div>
  );
};

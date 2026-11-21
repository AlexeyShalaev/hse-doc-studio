import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { VersionSection } from "@features/pack-forms";
import { Button } from "@shared/ui";
import { useSpaceNav } from "../../context/useSpaceNav";
import type { ContentPart, ContentPartProps } from "../contract";
import { FormPane } from "../FormPane";
import { useContentNav } from "../useContentNav";
import "./space-content-parts.css";

// Раздел версии «Содержимого» (pack-studio-ux.md, 5.5, срез S8d): одно предложение о том, что здесь
// правят, и форма `pack-forms` ровно на этот раздел, без полосы вкладок прежней формы. «Подписи и
// места» делает S8c, «Все файлы» это `FilesPart`.
const SECTION: Partial<Record<ContentPart, VersionSection>> = {
  documents: "documents",
  fields: "fields",
  forms: "forms",
  deadlines: "submission",
  languages: "languages",
  rules: "checks",
};

export const VersionPart = ({
  workspaceId,
  versionDir,
  part,
  at,
  readOnly,
  children,
}: ContentPartProps & { children?: ReactNode }) => {
  const { t } = useTranslation("packSpace");
  const nav = useContentNav();
  const space = useSpaceNav();
  const section = SECTION[part];
  if (!section) return null;
  return (
    <div className="sp-ct-part" data-testid={`ct-part-${part}`}>
      <div className="sp-ct-part-lead">
        <p>{t(`content.parts.${part}.lead`)}</p>
        {readOnly && (
          <span className="sp-ct-part-lock" data-testid="ct-part-lock">
            <Lock
              size="0.75rem"
              aria-label={t("content.parts.readOnly")}
              role="img"
            />
            <Button
              size="xs"
              variant="secondary"
              data-testid="ct-part-copy"
              onClick={() => {
                // Кнопку «Править копию» делает S4; параметр `copy` зарезервирован за ним (12.6).
                space.go({ extra: { copy: "1" } });
              }}
            >
              {t("content.parts.copy")}
            </Button>
          </span>
        )}
      </div>
      <FormPane
        workspaceId={workspaceId}
        path={`${versionDir}/version.yaml`}
        at={at}
        section={section}
        onOpenFile={nav.toFile}
      />
      {children}
    </div>
  );
};

import { useTranslation } from "react-i18next";
import type { z } from "zod";
import type { ProjectResponseSchema } from "@entities/project";
import { useForms } from "@entities/form";
import { FormFill, getFormIcon } from "@features/form-fill";
import { pickLocalized } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { PageHead } from "./PageHead";

type Project = z.infer<typeof ProjectResponseSchema>;

export type FormViewProps = {
  project: Project;
  formId: string;
};

// Generic panel for ANY pack-declared form. The nav routes here as
// `form:<id>`; the form's schema/title/fields all come from the pack.
export const FormView = ({ project, formId }: FormViewProps) => {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useForms(project.id);
  const form = data?.forms.find((f) => f.id === formId);
  const lang = project.lang ?? "ru";
  const title = form
    ? pickLocalized(form.title, lang, t("common.formFallback"))
    : t("common.formFallback");

  return (
    <div
      style={{ padding: "24px 32px", overflowY: "auto", flex: 1, minHeight: 0 }}
    >
      <PageHead
        icon={getFormIcon(form?.icon)}
        title={title}
        sub={t("form.subtitle")}
      />

      {isLoading ? (
        <div className="flex justify-center" style={{ padding: 32 }}>
          <Spinner />
        </div>
      ) : form ? (
        <FormFill projectId={project.id} formId={form.id} lang={lang} />
      ) : (
        <p className="dim" style={{ marginTop: 24, fontSize: 13 }}>
          {t("form.notFound")}
        </p>
      )}
    </div>
  );
};

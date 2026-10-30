import { useTranslation } from "react-i18next";
import { toast } from "@shared/lib";
import { useSigningPolicy, useUpdateSigning } from "../api/installQueries";
import { LoadState, PageHead } from "./parts";
import { Ready } from "./Ready";
import { SigningPolicyForm } from "./SigningPolicyForm";

/** Раздел «Ключи подписи»: политика хранения секретных ключей на сервере. */
export const SigningPolicyPage = () => (
  <Ready>
    <SigningBody />
  </Ready>
);

const SigningBody = () => {
  const { t } = useTranslation("adminInstall");
  const policy = useSigningPolicy();
  const save = useUpdateSigning();

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20, flex: 1 }}
      data-testid="admin-signing-page"
    >
      <PageHead title={t("signing.page.title")} lead={t("signing.page.lead")} />
      {policy.data ? (
        <SigningPolicyForm
          policy={policy.data}
          onSave={(serverKeys) => save.mutateAsync(serverKeys)}
          onSaved={() => {
            toast.success(t("savedToast"));
          }}
        />
      ) : (
        <LoadState
          failed={policy.isError}
          sections={1}
          onRetry={() => {
            void policy.refetch();
          }}
        />
      )}
    </div>
  );
};

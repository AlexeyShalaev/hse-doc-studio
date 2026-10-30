import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { useSigningPolicy, useUpdateSigning } from "../api/installQueries";
import { LoadState } from "./LoadState";
import { PageHead } from "./parts";
import { Ready } from "./Ready";
import { SigningPolicyCard } from "./SigningPolicyCard";

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
  const [saved, setSaved] = useState(false);
  const [round, setRound] = useState(0);

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20 }}
      data-testid="admin-signing-page"
    >
      <PageHead title={t("signing.page.title")} lead={t("signing.page.lead")} />
      <div className="flex flex-col" style={{ gap: 14 }}>
        {!policy.data && (
          <LoadState
            failed={policy.isError}
            onRetry={() => {
              void policy.refetch();
            }}
          />
        )}
        {policy.data && (
          <SigningPolicyCard
            key={`${JSON.stringify(policy.data)}:${String(round)}`}
            policy={policy.data}
            pending={save.isPending}
            failure={save.isError ? { code: failureCode(save.error) } : null}
            saved={saved}
            onSave={(serverKeys) => {
              setSaved(false);
              save.mutate(serverKeys, {
                onSuccess: () => {
                  setSaved(true);
                  setRound((r) => r + 1);
                },
              });
            }}
          />
        )}
      </div>
    </div>
  );
};

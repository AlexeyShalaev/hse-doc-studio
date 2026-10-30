import {
  AiProvidersPage,
  InstancePage,
  SigningPolicyPage,
} from "@features/admin-install";
import { AIProviderEditorModal } from "@features/manage-ai-provider";

export type AdminInstallPart = "instance" | "signing" | "ai-providers";

/** Разделы настроек установки: название и сборка, политика ключей подписи, общие ИИ-провайдеры. */
export const AdminInstallPage = ({ part }: { part: AdminInstallPart }) => {
  switch (part) {
    case "instance":
      return <InstancePage />;
    case "signing":
      return <SigningPolicyPage />;
    case "ai-providers":
      return (
        <AiProvidersPage
          renderEditor={({ provider, onClose }) => (
            <AIProviderEditorModal
              key={provider?.id ?? "new"}
              isOpen
              owner="instance"
              provider={provider}
              onClose={onClose}
            />
          )}
        />
      );
  }
};

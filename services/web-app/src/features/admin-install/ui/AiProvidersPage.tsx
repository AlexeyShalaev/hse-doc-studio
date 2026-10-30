import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { toast } from "@shared/lib";
import { Button, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  useAIProviders,
  useDeleteAIProvider,
  type AIProvider,
} from "@entities/ai-provider";
import { failureKey } from "../lib/failure";
import { LoadState } from "./LoadState";
import { PageHead } from "./parts";
import { Ready } from "./Ready";
import { SharedProviders } from "./SharedProviders";

export type EditorSlotProps = {
  /** null создаёт нового провайдера. */
  provider: AIProvider | null;
  onClose: () => void;
};

/**
 * Раздел «ИИ-провайдеры»: общие провайдеры установки. Форму провайдера рисует тот же
 * редактор, что и в настройках пользователя; страница подключает его через слот, потому что
 * срезы (features) не импортируют друг друга.
 */
export const AiProvidersPage = ({
  renderEditor,
}: {
  renderEditor: (props: EditorSlotProps) => ReactNode;
}) => (
  <Ready>
    <AiBody renderEditor={renderEditor} />
  </Ready>
);

const AiBody = ({
  renderEditor,
}: {
  renderEditor: (props: EditorSlotProps) => ReactNode;
}) => {
  const { t } = useTranslation("adminInstall");
  const providers = useAIProviders("instance");
  const remove = useDeleteAIProvider("instance");
  const [editing, setEditing] = useState<{
    provider: AIProvider | null;
  } | null>(null);
  const [deleting, setDeleting] = useState<AIProvider | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const confirmDelete = () => {
    if (!deleting) return;
    const target = deleting;
    remove.mutate(target.id, {
      onSuccess: () => {
        toast.success(t("ai.deletedToast", { name: target.name }));
        setDeleting(null);
        setFailure(null);
      },
      onError: (error) => {
        setFailure(failureCode(error));
      },
    });
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20 }}
      data-testid="admin-ai-page"
    >
      <PageHead title={t("ai.page.title")} lead={t("ai.page.lead")} />
      <div className="flex flex-col" style={{ gap: 14 }}>
        {!providers.data && (
          <LoadState
            failed={providers.isError}
            onRetry={() => {
              void providers.refetch();
            }}
          />
        )}
        {providers.data && (
          <SharedProviders
            providers={providers.data}
            deleting={remove.isPending}
            onAdd={() => {
              setEditing({ provider: null });
            }}
            onEdit={(provider) => {
              setEditing({ provider });
            }}
            onDelete={(provider) => {
              setFailure(null);
              setDeleting(provider);
            }}
          />
        )}
      </div>
      {editing &&
        renderEditor({
          provider: editing.provider,
          onClose: () => {
            setEditing(null);
          },
        })}
      <Modal
        isOpen={deleting !== null}
        onClose={() => {
          if (!remove.isPending) setDeleting(null);
        }}
        title={t("ai.deleteTitle")}
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              disabled={remove.isPending}
              onClick={() => {
                setDeleting(null);
              }}
            >
              {t("cancel")}
            </Button>
            <button
              type="button"
              className="btn danger"
              disabled={remove.isPending}
              onClick={confirmDelete}
              data-testid="shared-provider-delete-confirm"
            >
              {remove.isPending && <Spinner size="sm" />}
              {t("ai.delete")}
            </button>
          </>
        }
      >
        <div
          className="flex flex-col"
          style={{ gap: 10, fontSize: 13 }}
          data-testid="shared-provider-delete"
        >
          <span>{t("ai.deleteBody", { name: deleting?.name ?? "" })}</span>
          {failure && (
            <Notice tone="err" role="alert" text={t(failureKey(failure))} />
          )}
        </div>
      </Modal>
    </div>
  );
};

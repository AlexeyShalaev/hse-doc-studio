import { useState } from "react";
import { KeyRound, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useAddPackServiceAccess,
  usePackServiceAccess,
  useRemovePackServiceAccess,
  type PackServiceAccess,
} from "@entities/pack-studio";
import { ApiError } from "@shared/api";
import { formatPastTime } from "@shared/lib";
import {
  Button,
  EmptyState,
  ErrorState,
  Input,
  ListRow,
  Modal,
  Section,
  SectionList,
  Spinner,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

/** Окно «Добавить служебный доступ»: адрес репозитория паков, метка и токен. */
const AddDialog = ({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminPackStudio");
  const add = useAddPackServiceAccess();
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [token, setToken] = useState("");

  const close = () => {
    if (add.isPending) return;
    add.reset();
    setUrl("");
    setLabel("");
    setToken("");
    onClose();
  };

  const submit = () => {
    const body = {
      url: url.trim(),
      token: token.trim(),
      label: label.trim() === "" ? null : label.trim(),
    };
    add.mutate(body, {
      onSuccess: close,
      // Токен не держим в окне дольше запроса: при ошибке его вводят заново.
      onSettled: () => {
        setToken("");
      },
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("service.addTitle")}
      description={t("service.addLead")}
      width={540}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("grant.cancel")}
          </Button>
          <Button
            disabled={add.isPending || url.trim() === "" || token.trim() === ""}
            onClick={submit}
            data-testid="ps-service-submit"
          >
            {t("service.submit")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.875rem" }}>
        <Input
          label={t("service.url")}
          placeholder="https://gitlab.example.org/fcs/packs.git"
          value={url}
          maxLength={2048}
          onChange={(e) => {
            setUrl(e.target.value);
          }}
          isMono
          autoFocus
          data-testid="ps-service-url"
        />
        <Input
          label={t("service.label")}
          hint={t("service.labelHint")}
          value={label}
          maxLength={120}
          onChange={(e) => {
            setLabel(e.target.value);
          }}
          data-testid="ps-service-label"
        />
        <Input
          label={t("service.token")}
          hint={t("service.tokenHint")}
          type="password"
          autoComplete="off"
          value={token}
          maxLength={4096}
          onChange={(e) => {
            setToken(e.target.value);
          }}
          isMono
          data-testid="ps-service-token"
        />
        {add.isError && (
          <Notice tone="err" role="alert" text={packErrorText(add.error)} />
        )}
      </div>
    </Modal>
  );
};

/**
 * «Служебные доступы» (template-studio.md, 4.2): токен репозитория паков уровня
 * установки, один на репозиторий. Им ходят пространства людей с правом «Автор
 * шаблонов»; коммит подписан человеком, секрет сервер не показывает.
 */
export const ServiceAccessSection = () => {
  const { t } = useTranslation("adminPackStudio");
  const list = usePackServiceAccess();
  const remove = useRemovePackServiceAccess();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<PackServiceAccess | null>(null);

  // Без хранилища служебных доступов (локальная Студия) раздела нет.
  if (
    list.error instanceof ApiError &&
    list.error.code === "service_access_not_found"
  ) {
    return null;
  }

  let body: React.ReactNode;
  if (list.isPending) {
    body = <Spinner />;
  } else if (list.isError) {
    body = (
      <ErrorState
        compact
        description={packErrorText(list.error)}
        onRetry={() => void list.refetch()}
      />
    );
  } else if (list.data.length === 0) {
    body = (
      <EmptyState
        compact
        icon={<ShieldCheck size="1.25rem" />}
        title={t("service.emptyTitle")}
        description={t("service.emptyLead")}
        testId="ps-service-empty"
      />
    );
  } else {
    body = (
      <SectionList>
        {list.data.map((item) => (
          <ListRow
            key={item.id}
            testId={`ps-service-${item.id}`}
            icon={<KeyRound size="0.875rem" />}
            title={item.label}
            description={[
              item.url,
              item.token_family ? `${item.token_family}…` : null,
              t("service.since", {
                when: formatPastTime(item.created_at),
                who: item.created_by_name ?? item.created_by ?? "",
              }),
            ]
              .filter(Boolean)
              .join(" · ")}
            meta={
              <Button
                size="xs"
                variant="ghost"
                aria-label={t("service.remove", { name: item.label })}
                title={t("service.remove", { name: item.label })}
                onClick={() => {
                  setRemoving(item);
                }}
                data-testid="ps-service-remove"
              >
                <Trash2 size="0.75rem" />
              </Button>
            }
          />
        ))}
      </SectionList>
    );
  }

  return (
    <Section
      title={t("service.title")}
      description={t("service.lead")}
      actions={
        <Button
          size="sm"
          onClick={() => {
            setAdding(true);
          }}
          data-testid="ps-service-open"
        >
          <Plus size="0.875rem" />
          {t("service.add")}
        </Button>
      }
      flush={(list.data?.length ?? 0) > 0}
    >
      {body}
      <AddDialog
        isOpen={adding}
        onClose={() => {
          setAdding(false);
        }}
      />
      <Modal
        isOpen={removing !== null}
        onClose={() => {
          if (!remove.isPending) {
            remove.reset();
            setRemoving(null);
          }
        }}
        title={t("service.removeTitle", { name: removing?.label ?? "" })}
        description={t("service.removeLead")}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                remove.reset();
                setRemoving(null);
              }}
            >
              {t("grant.cancel")}
            </Button>
            <Button
              variant="danger"
              disabled={remove.isPending}
              onClick={() => {
                if (!removing) return;
                remove.mutate(removing.id, {
                  onSuccess: () => {
                    setRemoving(null);
                  },
                });
              }}
              data-testid="ps-service-remove-confirm"
            >
              {t("service.removeSubmit")}
            </Button>
          </>
        }
      >
        {remove.isError && (
          <Notice tone="err" role="alert" text={packErrorText(remove.error)} />
        )}
      </Modal>
    </Section>
  );
};

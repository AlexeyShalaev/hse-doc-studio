import { useId, useState } from "react";
import {
  GitFork,
  KeyRound,
  Plus,
  ShieldCheck,
  Stethoscope,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useAddPackServiceAccess,
  useCheckPackServiceAccess,
  usePackServiceAccess,
  useRemovePackServiceAccess,
  type PackServiceAccess,
  type PackServiceAccessCheck,
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

/** Что открыть в окне добавления: из раздела «Официальные паки» это доступ бота. */
export type ServiceAccessPreset = { url: string; forkMode: boolean };

/** Окно «Добавить служебный доступ»: адрес репозитория паков, метка и токен. */
export const AddServiceAccessDialog = ({
  isOpen,
  onClose,
  preset = null,
}: {
  isOpen: boolean;
  onClose: () => void;
  preset?: ServiceAccessPreset | null;
}) => {
  const { t } = useTranslation("adminPackStudio");
  const add = useAddPackServiceAccess();
  const [url, setUrl] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [token, setToken] = useState("");
  const [forkMode, setForkMode] = useState<boolean | null>(null);
  const forkId = useId();
  const urlValue = url ?? preset?.url ?? "";
  const fork = forkMode ?? preset?.forkMode ?? false;

  const close = () => {
    if (add.isPending) return;
    add.reset();
    setUrl(null);
    setLabel("");
    setToken("");
    setForkMode(null);
    onClose();
  };

  const submit = () => {
    const body = {
      url: urlValue.trim(),
      token: token.trim(),
      label: label.trim() === "" ? null : label.trim(),
      ...(fork ? { fork_mode: true } : {}),
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
            disabled={
              add.isPending || urlValue.trim() === "" || token.trim() === ""
            }
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
          value={urlValue}
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
        <label className="ps-choice" htmlFor={forkId}>
          <input
            id={forkId}
            type="checkbox"
            checked={fork}
            onChange={(e) => {
              setForkMode(e.target.checked);
            }}
            style={{ accentColor: "var(--accent)" }}
            data-testid="ps-service-fork"
          />
          <span className="ps-choice-text">
            <span>{t("service.forkMode")}</span>
            <span className="ps-choice-hint">{t("service.forkModeHint")}</span>
          </span>
        </label>
        {add.isError && (
          <Notice tone="err" role="alert" text={packErrorText(add.error)} />
        )}
      </div>
    </Modal>
  );
};

/** Итог «Проверить»: чей токен, его области, право push, форк бота и что не так. */
const CheckResult = ({ check }: { check: PackServiceAccessCheck }) => {
  const { t } = useTranslation("adminPackStudio");
  return (
    <div
      className="flex flex-col"
      style={{ gap: "0.5rem" }}
      data-testid="ps-service-check-result"
    >
      <Notice
        tone={check.ok ? "info" : "err"}
        role={check.ok ? "status" : "alert"}
        text={check.ok ? t("service.check.ok") : t("service.check.failed")}
      />
      <ul
        className="flex flex-col"
        style={{ gap: "0.25rem", margin: 0, paddingLeft: "1rem" }}
      >
        {check.login && (
          <li>{t("service.check.login", { login: check.login })}</li>
        )}
        {check.scopes !== null && (
          <li>
            {t("service.check.scopes", {
              scopes: check.scopes.length > 0 ? check.scopes.join(", ") : "-",
            })}
          </li>
        )}
        {check.access.fork_url && (
          <li className="mono">
            {t("service.check.fork", { url: check.access.fork_url })}
          </li>
        )}
      </ul>
      {check.problems.map((problem) => (
        <div
          key={problem}
          className="flex items-start"
          style={{ gap: "0.375rem" }}
        >
          <TriangleAlert size="0.875rem" aria-hidden="true" />
          <span data-testid={`ps-service-problem-${problem}`}>
            {t(`service.problem.${problem}`)}
          </span>
        </div>
      ))}
    </div>
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
  const check = useCheckPackServiceAccess();
  const [checked, setChecked] = useState<PackServiceAccessCheck | null>(null);
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
            icon={
              item.fork_mode ? (
                <GitFork size="0.875rem" />
              ) : (
                <KeyRound size="0.875rem" />
              )
            }
            title={item.label}
            description={[
              item.url,
              item.fork_mode
                ? item.fork_url
                  ? t("service.forkAt", { url: item.fork_url })
                  : t("service.forkPending")
                : null,
              item.token_family ? `${item.token_family}…` : null,
              t("service.since", {
                when: formatPastTime(item.created_at),
                who: item.created_by_name ?? item.created_by ?? "",
              }),
            ]
              .filter(Boolean)
              .join(" · ")}
            meta={
              <>
                <Button
                  size="xs"
                  variant="ghost"
                  aria-label={t("service.check.button", { name: item.label })}
                  title={t("service.check.button", { name: item.label })}
                  disabled={check.isPending}
                  onClick={() => {
                    setChecked(null);
                    check.mutate(item.id, {
                      onSuccess: (result) => {
                        setChecked(result);
                      },
                    });
                  }}
                  data-testid="ps-service-check"
                >
                  {check.isPending && check.variables === item.id ? (
                    <Spinner size="sm" />
                  ) : (
                    <Stethoscope size="0.75rem" />
                  )}
                </Button>
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
              </>
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
      {check.isError && (
        <Notice tone="err" role="alert" text={packErrorText(check.error)} />
      )}
      <Modal
        isOpen={checked !== null}
        onClose={() => {
          setChecked(null);
        }}
        title={t("service.check.title", { name: checked?.access.label ?? "" })}
        footer={
          <Button
            onClick={() => {
              setChecked(null);
            }}
          >
            {t("service.check.close")}
          </Button>
        }
      >
        {checked && <CheckResult check={checked} />}
      </Modal>
      <AddServiceAccessDialog
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

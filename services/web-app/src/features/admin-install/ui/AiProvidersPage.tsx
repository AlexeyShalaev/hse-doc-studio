import { useState, type ReactNode } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import {
  needsPager,
  toast,
  useListQueryState,
  useServerList,
} from "@shared/lib";
import {
  Button,
  FilterBar,
  FilterMenu,
  Modal,
  Pagination,
  SortSelect,
  Spinner,
  type ActiveFilter,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  AIProviderTypeSchema,
  aiProviderKeys,
  instanceAiProviderApi,
  useDeleteAIProvider,
  type AIProvider,
} from "@entities/ai-provider";
import { failureKey } from "../lib/failure";
import { LoadState, PageHead } from "./parts";
import { Ready } from "./Ready";
import { SharedProviders } from "./SharedProviders";

export type EditorSlotProps = {
  /** null создаёт нового провайдера. */
  provider: AIProvider | null;
  onClose: () => void;
};

const TYPES = AIProviderTypeSchema.options;
const SORT_FIELDS = ["created_at", "name", "type"] as const;

// Состояние списка в адресе: поиск по названию и адресу, тип и порядок. Всё
// это считает сервер; по умолчанию порядок добавления.
const LIST = {
  filters: { type: { multi: true, values: TYPES } },
  sort: { fields: SORT_FIELDS, default: "created_at" },
} as const;
const LIST_KEY = [...aiProviderKeys.all, "instance"] as const;

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
  const state = useListQueryState(LIST);
  const list = useServerList({
    state,
    queryKey: LIST_KEY,
    fetchPage: instanceAiProviderApi.page,
  });
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

  const add = () => {
    setEditing({ provider: null });
  };

  const typeLabel = (type: string) => t(`ai.type.${type}`);
  // Провайдеров нет совсем: вместо поиска и фильтров одно пустое состояние с
  // кнопкой «Добавить».
  const loaded = list.query.data !== undefined;
  const nothingYet =
    loaded &&
    !state.isFiltered &&
    list.total === 0 &&
    !list.query.isPlaceholderData;
  // Поиск и фильтры видны и при отказе: иначе неудачное условие не снять.
  const withBar = !nothingYet && (loaded || state.isFiltered);
  const active: ActiveFilter[] = [
    ...(state.q
      ? [
          {
            id: "q",
            label: t("ai.filters.search"),
            value: state.q,
            onRemove: () => {
              state.setQ("");
            },
          },
        ]
      : []),
    ...(state.filters.type.length > 0
      ? [
          {
            id: "type",
            label: t("ai.filters.type"),
            value: state.filters.type.map(typeLabel).join(", "),
            onRemove: () => {
              state.setFilter("type", null);
            },
          },
        ]
      : []),
  ];

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20, flex: 1 }}
      data-testid="admin-ai-page"
    >
      <PageHead
        title={t("ai.page.title")}
        lead={t("ai.page.lead")}
        actions={
          withBar ? (
            <Button
              size="sm"
              type="button"
              onClick={add}
              data-testid="shared-provider-add"
            >
              <Plus size={14} aria-hidden="true" />
              {t("ai.add")}
            </Button>
          ) : null
        }
      />
      {withBar && (
        <FilterBar
          search={state.q}
          onSearchChange={state.setQ}
          searchLabel={t("ai.search")}
          searchPlaceholder={t("ai.searchPlaceholder")}
          busy={list.isFetching}
          onReset={state.reset}
          active={active}
          total={state.isFiltered ? list.total : null}
          extra={
            <>
              <FilterMenu
                label={t("ai.filters.type")}
                testId="shared-provider-filter-type"
                values={state.filters.type}
                onChange={(values) => {
                  state.setFilter("type", values);
                }}
                options={TYPES.map((type) => ({
                  value: type,
                  label: typeLabel(type),
                }))}
              />
              <SortSelect
                testId="shared-provider-sort"
                sort={state.sort}
                onChange={state.setSort}
                label={t("ai.sort.caption")}
                options={[
                  {
                    field: "created_at",
                    desc: true,
                    label: t("ai.sort.newest"),
                  },
                  {
                    field: "created_at",
                    desc: false,
                    label: t("ai.sort.oldest"),
                  },
                  { field: "name", desc: false, label: t("ai.sort.name") },
                  { field: "type", desc: false, label: t("ai.sort.type") },
                ]}
              />
            </>
          }
        />
      )}
      {loaded && !list.isError ? (
        <SharedProviders
          providers={list.items}
          filtered={state.isFiltered}
          query={state.q}
          onResetFilters={state.reset}
          busy={list.query.isPlaceholderData}
          pagination={
            needsPager(list.total, state) ? (
              <Pagination {...list.pagination} />
            ) : null
          }
          deleting={remove.isPending}
          onAdd={add}
          onEdit={(provider) => {
            setEditing({ provider });
          }}
          onDelete={(provider) => {
            setFailure(null);
            setDeleting(provider);
          }}
          onCheck={(provider) => instanceAiProviderApi.fetchModels(provider.id)}
        />
      ) : (
        <LoadState
          failed={list.isError}
          sections={1}
          onRetry={() => {
            void list.refetch();
          }}
        />
      )}
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

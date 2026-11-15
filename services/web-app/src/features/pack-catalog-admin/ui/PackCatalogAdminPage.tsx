import type { TFunction } from "i18next";
import { useState } from "react";
import { Library, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  catalogErrorText,
  usePackCatalog,
  useRemoveSource,
  useUpdateSource,
  type CatalogPack,
  type CatalogSource,
} from "@entities/pack-catalog";
import {
  Button,
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
  Section,
  Spinner,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { AddSourceDialog } from "./AddSourceDialog";
import { CheckDialog } from "./CheckDialog";
import { EditSourceDialog, ReplaceArchiveDialog } from "./EditSourceDialog";
import { HistoryDialog } from "./HistoryDialog";
import { PackLine, PackList } from "./PackList";
import { SourceCard, type SourceAction } from "./SourceCard";

type Open = { action: Exclude<SourceAction, "toggle">; source: CatalogSource };

/** Подтверждение «Удалить»: паки уходят из мастера, версии остаются для проектов. */
const RemoveDialog = ({
  source,
  onClose,
}: {
  source: CatalogSource | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminPackCatalog");
  const remove = useRemoveSource();
  const close = () => {
    if (remove.isPending) return;
    remove.reset();
    onClose();
  };
  return (
    <Modal
      isOpen={source !== null}
      onClose={close}
      title={t("remove.title", { name: source?.label ?? "" })}
      description={t("remove.lead")}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (!source) return;
              remove.mutate(source.id, {
                onSuccess: () => {
                  remove.reset();
                  onClose();
                },
              });
            }}
            data-testid="pc-remove-confirm"
          >
            {t("remove.submit")}
          </Button>
        </>
      }
    >
      {remove.isError && (
        <Notice tone="err" role="alert" text={catalogErrorText(remove.error)} />
      )}
    </Modal>
  );
};

/** Метка, откуда пак вне источников: вшит в образ или остался от удалённого источника. */
const otherOrigin = (pack: CatalogPack, t: TFunction): string =>
  pack.origin === "builtin" ? t("pack.builtin") : t("pack.orphan");

/**
 * Админка, «Каталоги паков» (template-studio.md, 10.3 и 10.4, срез T17): подключённые
 * источники паков git и архивы, их проверка и применение, остальные паки каталога.
 */
export const PackCatalogAdminPage = () => {
  const { t } = useTranslation("adminPackCatalog");
  const overview = usePackCatalog();
  const toggle = useUpdateSource();
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<Open | null>(null);

  const header = (
    <PageHeader
      title={t("title")}
      description={t("lead")}
      actions={
        overview.data ? (
          <Button
            onClick={() => {
              setAdding(true);
            }}
            data-testid="pc-add-open"
          >
            <Plus size="0.875rem" />
            {t("sources.add")}
          </Button>
        ) : undefined
      }
    />
  );

  if (overview.isPending) {
    return (
      <>
        {header}
        <Spinner />
      </>
    );
  }
  if (overview.isError) {
    return (
      <>
        {header}
        <ErrorState
          description={catalogErrorText(overview.error)}
          onRetry={() => void overview.refetch()}
        />
      </>
    );
  }

  const data = overview.data;
  // Пока окно открыто, источник берётся из свежего списка: после «Применить» и правок он новый.
  const current = (source: CatalogSource | undefined) =>
    source ? (data.sources.find((s) => s.id === source.id) ?? source) : null;
  const of = (action: Open["action"]) =>
    open?.action === action ? current(open.source) : null;
  const closeDialog = () => {
    setOpen(null);
  };

  const onAction = (action: SourceAction, source: CatalogSource) => {
    if (action === "toggle") {
      toggle.mutate({ id: source.id, body: { enabled: !source.enabled } });
      return;
    }
    setOpen({ action, source });
  };

  return (
    <div
      className="flex flex-col"
      style={{ gap: "1rem" }}
      data-testid="pc-admin"
    >
      {header}
      <Section title={t("sources.title")} description={t("sources.lead")}>
        {toggle.isError && (
          <div style={{ marginBottom: "0.5rem" }}>
            <Notice
              tone="err"
              role="alert"
              text={catalogErrorText(toggle.error)}
            />
          </div>
        )}
        {data.sources.length === 0 ? (
          <EmptyState
            compact
            icon={<Library size="1.25rem" />}
            title={t("sources.emptyTitle")}
            description={t("sources.emptyLead")}
            action={
              <Button
                size="sm"
                onClick={() => {
                  setAdding(true);
                }}
              >
                <Plus size="0.875rem" />
                {t("sources.add")}
              </Button>
            }
            testId="pc-sources-empty"
          />
        ) : (
          <div className="flex flex-col" style={{ gap: "0.625rem" }}>
            {data.sources.map((source) => (
              <SourceCard
                key={source.id}
                source={source}
                onAction={onAction}
                toggling={toggle.isPending}
              />
            ))}
          </div>
        )}
      </Section>
      <Section
        title={t("others.title")}
        description={t("others.lead")}
        testId="pc-others"
      >
        {data.packs.length === 0 ? (
          <p className="dim" style={{ fontSize: "0.75rem", margin: 0 }}>
            {t("others.empty")}
          </p>
        ) : (
          <PackList>
            {data.packs.map((pack) => (
              <PackLine
                key={pack.id}
                pack={pack}
                origin={otherOrigin(pack, t)}
              />
            ))}
          </PackList>
        )}
      </Section>
      <AddSourceDialog
        isOpen={adding}
        maxArchiveBytes={data.limits.max_archive_bytes}
        onClose={() => {
          setAdding(false);
        }}
        onAdded={(source) => {
          setAdding(false);
          // Новый источник сразу проверяется: без проверки его паки не появятся.
          setOpen({ action: "check", source });
        }}
      />
      <CheckDialog source={of("check")} onClose={closeDialog} />
      <EditSourceDialog source={of("edit")} onClose={closeDialog} />
      <ReplaceArchiveDialog
        source={of("replace")}
        maxArchiveBytes={data.limits.max_archive_bytes}
        onClose={closeDialog}
        onReplaced={(source) => {
          setOpen({ action: "check", source });
        }}
      />
      <HistoryDialog source={of("history")} onClose={closeDialog} />
      <RemoveDialog source={of("remove")} onClose={closeDialog} />
    </div>
  );
};

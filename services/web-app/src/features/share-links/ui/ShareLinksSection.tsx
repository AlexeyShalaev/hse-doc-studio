import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateShareLink,
  useRevokeShareLink,
  useRotateShareLink,
  useShareLinkVisits,
  useShareLinks,
  useUpdateShareLink,
  type ShareLink,
} from "@entities/share-link";
import type { ProjectRole } from "@entities/session";
import { ApiError } from "@shared/api";
import { toast } from "@shared/lib";
import { linkErrorText } from "../lib/errors";
import {
  ConfirmLinkDialog,
  CreatedLinkModal,
  LinkVisitsModal,
  ShareLinkForm,
  type ShareLinkFormValue,
} from "./ShareLinkDialogs";
import { ShareLinksView } from "./ShareLinksView";
import "./shareLinks.css";

/**
 * «Ссылки» в панели «Доступ». Владелец видит все ссылки, редактор с правом
 * делиться только свои (S8); остальным раздел не показывается: сервер ответил
 * бы 403, а гостю и вошедшему по ссылке ссылки проекта закрыты.
 */
export const ShareLinksSection = ({
  projectId,
  myRole,
}: {
  projectId: string;
  myRole: ProjectRole | null;
}) => {
  const { t } = useTranslation("shareLinks");
  // Право делиться у редактора знает только сервер: без него список отвечает 403, и раздел прячется.
  const mayTry = myRole === "owner" || myRole === "editor";
  const [showRevoked, setShowRevoked] = useState(false);
  const list = useShareLinks(projectId, {
    includeRevoked: showRevoked,
    enabled: mayTry,
  });
  const create = useCreateShareLink(projectId);
  const update = useUpdateShareLink(projectId);
  const rotate = useRotateShareLink(projectId);
  const revoke = useRevokeShareLink(projectId);
  const [form, setForm] = useState<{ link: ShareLink | null } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);
  const [rotating, setRotating] = useState<ShareLink | null>(null);
  const [revoking, setRevoking] = useState<ShareLink | null>(null);
  const [visitsOf, setVisitsOf] = useState<ShareLink | null>(null);
  const visits = useShareLinkVisits(projectId, visitsOf?.id ?? null);

  const forbidden = list.error instanceof ApiError && list.error.status === 403;
  if (!mayTry || forbidden) return null;

  const submit = (value: ShareLinkFormValue) => {
    setFormError(null);
    const onError = (error: unknown) => {
      setFormError(linkErrorText(error));
    };
    if (value.mode === "create") {
      create.mutate(value.body, {
        onSuccess: (link) => {
          setForm(null);
          setCreatedUrl(link.url);
          toast.success(t("toast.created", { label: link.label }));
        },
        onError,
      });
      return;
    }
    const link = form?.link;
    if (!link) return;
    update.mutate(
      { id: link.id, body: value.body },
      {
        onSuccess: () => {
          setForm(null);
          toast.success(t("toast.saved"));
        },
        onError,
      },
    );
  };

  return (
    <>
      <ShareLinksView
        status={list.data ? "ready" : list.isError ? "error" : "loading"}
        list={list.data ?? null}
        showRevoked={showRevoked}
        onToggleRevoked={() => {
          setShowRevoked((v) => !v);
        }}
        onRetry={() => {
          void list.refetch();
        }}
        onCreate={() => {
          setFormError(null);
          setForm({ link: null });
        }}
        onEdit={(link) => {
          setFormError(null);
          setForm({ link });
        }}
        onRotate={setRotating}
        onRevoke={setRevoking}
        onVisits={setVisitsOf}
        onCopied={() => {
          toast.success(t("toast.copied"));
        }}
      />
      {form && list.data && (
        <ShareLinkForm
          key={form.link?.id ?? "new"}
          isOpen
          link={form.link}
          maxRole={list.data.max_role}
          forcedLogin={list.data.forced_login}
          pending={create.isPending || update.isPending}
          error={formError}
          onSubmit={submit}
          onClose={() => {
            setForm(null);
          }}
        />
      )}
      <CreatedLinkModal
        url={createdUrl}
        onClose={() => {
          setCreatedUrl(null);
        }}
      />
      <ConfirmLinkDialog
        isOpen={rotating !== null}
        title={t("rotate.title")}
        body={t("rotate.text")}
        confirmLabel={t("rotate.confirm")}
        pending={rotate.isPending}
        testId="share-link-rotate-dialog"
        onClose={() => {
          setRotating(null);
        }}
        onConfirm={() => {
          if (!rotating) return;
          rotate.mutate(rotating.id, {
            onSuccess: (link) => {
              setRotating(null);
              setCreatedUrl(link.url);
              toast.success(t("toast.rotated"));
            },
            onError: (error) => {
              setRotating(null);
              toast.error(linkErrorText(error));
            },
          });
        }}
      />
      <ConfirmLinkDialog
        isOpen={revoking !== null}
        title={t("revoke.title")}
        body={t("revoke.text")}
        confirmLabel={t("revoke.confirm")}
        pending={revoke.isPending}
        testId="share-link-revoke-dialog"
        onClose={() => {
          setRevoking(null);
        }}
        onConfirm={() => {
          if (!revoking) return;
          revoke.mutate(revoking.id, {
            onSuccess: () => {
              setRevoking(null);
              toast.success(t("toast.revoked"));
            },
            onError: (error) => {
              setRevoking(null);
              toast.error(linkErrorText(error));
            },
          });
        }}
      />
      <LinkVisitsModal
        link={visitsOf}
        status={visits.data ? "ready" : visits.isError ? "error" : "loading"}
        items={visits.data?.items ?? []}
        onClose={() => {
          setVisitsOf(null);
        }}
      />
    </>
  );
};

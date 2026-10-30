import { useState } from "react";
import { useTranslation } from "react-i18next";
import { failureCode } from "@shared/api";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import { useCreateOrg } from "../api/adminOrgsQueries";
import type { Failure } from "../lib/failure";
import { SLUG_MAX, isValidSlug, slugify } from "../lib/slug";
import { FailureNotice } from "./parts";

export type CreateOrgFormProps = {
  pending?: boolean;
  failure?: Failure | null;
  onCancel: () => void;
  onSubmit: (input: { name: string; slug: string }) => void;
};

/** Форма новой организации: адрес подставляется из названия, пока его не правили руками. */
export const CreateOrgForm = ({
  pending = false,
  failure = null,
  onCancel,
  onSubmit,
}: CreateOrgFormProps) => {
  const { t } = useTranslation("adminOrgs");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [touched, setTouched] = useState(false);
  const [tried, setTried] = useState(false);

  const effectiveSlug = touched ? slug : slugify(name);
  const nameError =
    tried && name.trim() === "" ? t("create.nameRequired") : undefined;
  const slugError =
    tried && !isValidSlug(effectiveSlug) ? t("create.slugInvalid") : undefined;

  const submit = () => {
    setTried(true);
    if (name.trim() === "" || !isValidSlug(effectiveSlug)) return;
    onSubmit({ name: name.trim(), slug: effectiveSlug });
  };

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      data-testid="org-create-form"
    >
      <Input
        label={t("create.name")}
        value={name}
        maxLength={80}
        autoFocus
        autoComplete="off"
        {...(nameError ? { error: nameError } : {})}
        onChange={(event) => {
          setName(event.target.value);
        }}
        data-testid="org-create-name"
      />
      <Input
        label={t("create.slug")}
        value={effectiveSlug}
        maxLength={SLUG_MAX}
        isMono
        autoComplete="off"
        spellCheck={false}
        hint={t("create.slugHint")}
        {...(slugError ? { error: slugError } : {})}
        onChange={(event) => {
          setTouched(true);
          setSlug(event.target.value.toLowerCase());
        }}
        data-testid="org-create-slug"
      />
      {failure && <FailureNotice failure={failure} />}
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={pending}
        >
          {t("cancel")}
        </Button>
        <Button
          type="submit"
          disabled={pending}
          data-testid="org-create-submit"
        >
          {pending && <Spinner size="sm" />}
          {t("create.submit")}
        </Button>
      </div>
    </form>
  );
};

/** Диалог создания организации; после успеха открывает её. */
export const CreateOrgModal = ({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (slug: string) => void;
}) => {
  const { t } = useTranslation("adminOrgs");
  const create = useCreateOrg();
  const [failure, setFailure] = useState<Failure | null>(null);

  const close = () => {
    setFailure(null);
    create.reset();
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("create.title")}
      description={t("create.lead")}
    >
      {isOpen && (
        <CreateOrgForm
          pending={create.isPending}
          failure={failure}
          onCancel={close}
          onSubmit={(input) => {
            setFailure(null);
            create.mutate(input, {
              onSuccess: (org) => {
                onCreated(org.slug);
                close();
              },
              onError: (error) => {
                setFailure({ code: failureCode(error) });
              },
            });
          }}
        />
      )}
    </Modal>
  );
};

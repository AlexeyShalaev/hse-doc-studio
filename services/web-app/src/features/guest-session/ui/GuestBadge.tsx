import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router";
import { LogIn, LogOut, PencilLine, UserRound } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { linkSessionApi } from "@entities/share-link";
import { sessionKeys, type GuestInfo } from "@entities/session";
import { toast } from "@shared/lib";
import { Button, Input, Modal, Spinner } from "@shared/ui";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { useGuest } from "../model/useGuest";

const NAME_MAX = 64;

export type GuestBadgeViewProps = {
  guest: GuestInfo;
  defaultOpen?: boolean;
  onRename: () => void;
  onSignIn: () => void;
  onLeave: () => void;
};

const itemStyle = {
  width: "100%",
  justifyContent: "flex-start",
  padding: "7px 10px",
  gap: 8,
} as const;

/** «Гость: Борис» в шапке и меню гостевого режима. Чистый вид без запросов. */
export const GuestBadgeView = ({
  guest,
  defaultOpen,
  onRename,
  onSignIn,
  onLeave,
}: GuestBadgeViewProps) => {
  const { t } = useTranslation("guest");
  const label = guest.name
    ? t("badge.label", { name: guest.name })
    : t("badge.noName");
  return (
    <Popover {...(defaultOpen === undefined ? {} : { defaultOpen })}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="btn ghost sm"
          data-testid="guest-badge"
          aria-label={t("badge.menu")}
          style={{ gap: 6 }}
        >
          <UserRound size={14} aria-hidden="true" />
          <span className="truncate" style={{ maxWidth: 180 }}>
            {label}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        width={260}
        aria-label={t("badge.menu")}
        data-testid="guest-menu"
      >
        <div style={{ padding: 12, borderBottom: "1px solid var(--border)" }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
          <div style={{ fontSize: 11.5, color: "var(--fg-2)", marginTop: 2 }}>
            {t("badge.hint")}
          </div>
        </div>
        <div className="flex flex-col" style={{ padding: 4 }}>
          <button
            type="button"
            className="btn ghost sm"
            style={itemStyle}
            onClick={onRename}
            data-testid="guest-rename"
          >
            <PencilLine size={14} aria-hidden="true" /> {t("badge.rename")}
          </button>
          <button
            type="button"
            className="btn ghost sm"
            style={itemStyle}
            onClick={onSignIn}
            data-testid="guest-sign-in"
          >
            <LogIn size={14} aria-hidden="true" /> {t("badge.signIn")}
          </button>
          <button
            type="button"
            className="btn ghost sm"
            style={itemStyle}
            onClick={onLeave}
            data-testid="guest-leave"
          >
            <LogOut size={14} aria-hidden="true" /> {t("badge.leave")}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

export const GuestRenameDialog = ({
  isOpen,
  initial,
  pending,
  onSave,
  onClose,
}: {
  isOpen: boolean;
  initial: string;
  pending?: boolean;
  onSave: (name: string) => void;
  onClose: () => void;
}) => {
  const { t } = useTranslation("guest");
  const [name, setName] = useState(initial);
  const valid = name.trim().length > 0 && name.length <= NAME_MAX;
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("rename.title")}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("rename.cancel")}
          </Button>
          <Button
            type="submit"
            form="guest-rename-form"
            disabled={!valid || pending}
            data-testid="guest-rename-save"
          >
            {pending && <Spinner size="sm" />}
            {t("rename.save")}
          </Button>
        </>
      }
    >
      <form
        id="guest-rename-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) onSave(name.trim());
        }}
      >
        <Input
          label={t("rename.label")}
          hint={t("rename.hint")}
          value={name}
          maxLength={NAME_MAX}
          autoFocus
          onChange={(event) => {
            setName(event.target.value);
          }}
          data-testid="guest-rename-input"
        />
      </form>
    </Modal>
  );
};

export const GuestLeaveDialog = ({
  isOpen,
  pending,
  onConfirm,
  onClose,
}: {
  isOpen: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) => {
  const { t } = useTranslation("guest");
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("leave.title")}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("leave.cancel")}
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={pending}
            onClick={onConfirm}
            data-testid="guest-leave-confirm"
          >
            {t("leave.confirm")}
          </Button>
        </>
      }
    >
      <p>{t("leave.text")}</p>
    </Modal>
  );
};

/** Бейдж гостя в шапке: имя, переименование, вход, выход из гостевого режима. */
export const GuestBadge = () => {
  const { t } = useTranslation("guest");
  const guest = useGuest();
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const [renaming, setRenaming] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [pending, setPending] = useState(false);
  if (!guest) return null;

  const refresh = () =>
    client.invalidateQueries({ queryKey: sessionKeys.bootstrap() });

  return (
    <>
      <GuestBadgeView
        guest={guest}
        onRename={() => {
          setRenaming(true);
        }}
        onSignIn={() => {
          // Ссылочные права гостя на аккаунт не переносятся (T10): после входа ссылку открывают снова.
          const next = `${location.pathname}${location.search}`;
          void navigate(`/login?next=${encodeURIComponent(next)}`);
        }}
        onLeave={() => {
          setLeaving(true);
        }}
      />
      {renaming && (
        <GuestRenameDialog
          isOpen
          initial={guest.name ?? ""}
          pending={pending}
          onClose={() => {
            setRenaming(false);
          }}
          onSave={(name) => {
            setPending(true);
            linkSessionApi
              .rename(name)
              .then(() => refresh())
              .then(() => {
                setRenaming(false);
                toast.success(t("rename.saved"));
              })
              .catch(() => {
                toast.error(t("page.failed"));
              })
              .finally(() => {
                setPending(false);
              });
          }}
        />
      )}
      <GuestLeaveDialog
        isOpen={leaving}
        pending={pending}
        onClose={() => {
          setLeaving(false);
        }}
        onConfirm={() => {
          setPending(true);
          linkSessionApi
            .leave()
            .then(async () => {
              await refresh();
              setLeaving(false);
              void navigate("/login");
            })
            .catch(() => {
              toast.error(t("page.failed"));
            })
            .finally(() => {
              setPending(false);
            });
        }}
      />
    </>
  );
};

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  useSwitchPackBranch,
  type PackGit,
} from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Button, Input, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type BranchDialogProps = {
  git: PackGit;
  isOpen: boolean;
  onClose: () => void;
  /** Ветка сменилась: файлы на диске могли поменяться. */
  onSwitched: () => void;
};

type Mode = "auto" | "named";

/**
 * Рабочая ветка (template-studio.md, 4.6): новая ставится на текущую вершину и
 * правки остаются; своя прежняя или ветка с сервера открывается только при
 * чистом дереве. Имя по умолчанию Студия придумывает сама.
 */
export const BranchDialog = ({
  git,
  isOpen,
  onClose,
  onSwitched,
}: BranchDialogProps) => {
  const { t } = useTranslation("packStudio");
  const change = useSwitchPackBranch(git.workspace.id);
  const [mode, setMode] = useState<Mode>("auto");
  const [name, setName] = useState("");
  const uid = useId();

  const close = () => {
    if (change.isPending) return;
    change.reset();
    setMode("auto");
    setName("");
    onClose();
  };

  const wanted = mode === "named" ? name.trim() : null;
  const canSubmit = !change.isPending && (mode === "auto" || wanted !== "");

  const submit = () => {
    change.mutate(wanted, {
      onSuccess: (next) => {
        toast.success(t("git.branch.done", { branch: next.branch ?? "" }));
        onSwitched();
        change.reset();
        setName("");
        setMode("auto");
        onClose();
      },
    });
  };

  const radio = (value: Mode, label: string, hint: string) => (
    <label className="ps-choice" htmlFor={`${uid}-${value}`}>
      <input
        id={`${uid}-${value}`}
        type="radio"
        name={`${uid}-mode`}
        checked={mode === value}
        onChange={() => {
          setMode(value);
        }}
        style={{ accentColor: "var(--accent)" }}
      />
      <span className="ps-choice-text">
        <span>{label}</span>
        <span className="ps-choice-hint">{hint}</span>
      </span>
    </label>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title={t("git.branch.title")}
      description={
        git.branch
          ? t("git.branch.current", { branch: git.branch })
          : t("git.branch.none", { base: git.base_branch ?? "" })
      }
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("common.cancel")}
          </Button>
          <Button
            disabled={!canSubmit}
            onClick={submit}
            data-testid="git-branch-submit"
          >
            {mode === "auto" ? t("git.branch.create") : t("git.branch.switch")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col" style={{ gap: "0.625rem" }}>
        {radio("auto", t("git.branch.auto"), t("git.branch.autoHint"))}
        {radio("named", t("git.branch.named"), t("git.branch.namedHint"))}
        {mode === "named" && (
          <Input
            label={t("git.branch.name")}
            placeholder="pack-studio/me/fix-title"
            value={name}
            maxLength={200}
            onChange={(e) => {
              setName(e.target.value);
            }}
            isMono
            autoFocus
            data-testid="git-branch-name"
          />
        )}
        {git.dirty && mode === "named" && (
          <Notice tone="info" role="status" text={t("git.branch.dirtyHint")} />
        )}
        {change.isError && (
          <Notice tone="err" role="alert" text={packErrorText(change.error)} />
        )}
      </div>
    </Modal>
  );
};

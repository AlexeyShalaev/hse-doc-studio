import { useState } from "react";
import { GitPullRequestArrow } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  findingTarget,
  packOutcomePath,
  packWorkspacePath,
  type LintFailure,
  type PackVersionRef,
} from "@entities/pack-studio";
import { ProposeDialog, RepoAccessDialog } from "@features/pack-git";
import { Modal } from "@shared/ui";
import { useOutcomeModel } from "../model";
import { useScenarioUi } from "./scenarios/context";

const MAX_FINDINGS = 10;

/**
 * «Предложить» на экране «Результат» (git-пространство с правками): тот же диалог, что в режиме
 * «Файлы», с блоком «Что изменится в результате» над отправкой. Проверки пака, не прошедшие перед
 * отправкой, показываются списком с переходом к первой находке в «Файлах», где живут «Проблемы».
 */
export const ProposeAction = () => {
  const { t } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const navigate = useNavigate();
  const location = useLocation();
  const [dialog, setDialog] = useState<"propose" | "access" | null>(null);
  const [lint, setLint] = useState<LintFailure | null>(null);
  const { git, workspaceId, ref } = model;
  if (model.workspaceKind !== "git" || git === undefined) return null;

  const close = () => {
    setDialog(null);
  };
  const createScenario = (version: PackVersionRef) => {
    if (version.pack === ref.pack && version.template === ref.template) {
      ui?.open({ kind: "create" });
      return;
    }
    void navigate(packOutcomePath(workspaceId, version));
  };
  const first = lint?.findings
    .map((f) => findingTarget(f.path, f.message))
    .find((target) => target !== null);

  return (
    <>
      <button
        type="button"
        className="btn sm primary"
        disabled={
          model.url.state.mode === "student" ||
          (git.changed.length === 0 && git.ahead === 0)
        }
        title={t("bar.proposeHint")}
        data-testid="outcome-propose"
        onClick={() => {
          setDialog("propose");
        }}
      >
        <GitPullRequestArrow size="0.875rem" aria-hidden="true" />
        <span>{t("bar.propose")}</span>
      </button>
      <ProposeDialog
        git={git}
        isOpen={dialog === "propose"}
        onClose={close}
        editorDirty={false}
        version={ref}
        backTo={`${location.pathname}${location.search}`}
        onCreateScenario={createScenario}
        onLintFailed={setLint}
        onAccess={() => {
          setDialog("access");
        }}
      />
      <RepoAccessDialog
        workspace={git.workspace}
        isOpen={dialog === "access"}
        onClose={close}
      />
      <Modal
        isOpen={lint !== null}
        onClose={() => {
          setLint(null);
        }}
        title={t("bar.proposeLintTitle")}
        width={520}
        footer={
          <>
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                setLint(null);
              }}
            >
              {t("bar.proposeLintClose")}
            </button>
            <button
              type="button"
              className="btn sm primary"
              data-testid="outcome-propose-lint-open"
              onClick={() => {
                setLint(null);
                void navigate(packWorkspacePath(workspaceId, first?.path));
              }}
            >
              {t("bar.proposeLintOpen")}
            </button>
          </>
        }
      >
        <div data-testid="outcome-propose-lint">
          <p className="po-note">
            {t("bar.proposeLint", { count: lint?.findings.length ?? 0 })}
          </p>
          <ul className="po-lint-list">
            {(lint?.findings ?? []).slice(0, MAX_FINDINGS).map((f, index) => (
              <li key={`${f.path}-${String(index)}`}>
                <span className="po-mono">{f.path}</span> {f.message}
              </li>
            ))}
          </ul>
        </div>
      </Modal>
    </>
  );
};

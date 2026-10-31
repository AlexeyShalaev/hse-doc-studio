import { useEffect, useRef, useState, type ComponentType } from "react";
import { GitBranch } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ApiError } from "@shared/api";
import { useDebouncedValue } from "@shared/lib";
import {
  useCloneDefaults,
  useStartClone,
  useStartCloneFromBundle,
} from "@entities/git-remote";
import {
  describeGitError,
  readGitError,
  useOperation,
  type CloneTarget,
} from "@entities/git-sync";
import { useProfile } from "@entities/profile";
import { Spinner } from "@shared/ui/Spinner";
import { Stepper, type StepperStep } from "@shared/ui/Stepper";
import { cloneFailureTarget, isBundleCode } from "../../model/cloneFailure";
import { suggestedProjectName } from "../../lib/cloneNames";
import { useCloneSource } from "../../model/useCloneSource";
import { ProfileStep } from "../ProfileStep";
import {
  CloneFolderStep,
  type CloneFolderPickerProps,
  type FolderInspection,
} from "./CloneFolderStep";
import { CloneProgressStep } from "./CloneProgressStep";
import { CloneSourceStep, type CloneServerSlot } from "./CloneSourceStep";

/**
 * Окно выбора папки и проверка выбранной папки делает другая фича
 * (folder-picker). Фичи друг друга не импортируют, поэтому страница передаёт их
 * сюда. Без них путь вводится вручную.
 */
export type CloneFolderSlot = {
  Picker: ComponentType<CloneFolderPickerProps>;
  useInspect: (path: string) => FolderInspection;
};

export type CloneWizardProps = {
  folderSlot?: CloneFolderSlot | undefined;
  /** Источник «Сервер HSE Doc Studio» (локальная Студия): выбор проекта на сервере Студии. */
  serverSlot?: CloneServerSlot | undefined;
  /** Сервер: папку проекта выбирает сервер, шаг просит только название. */
  folderless?: boolean | undefined;
  /** Адрес и доступ, с которыми открыли мастер (из окна подключения). */
  initialTarget?: CloneTarget | null | undefined;
  /** «Отмена» и «К списку проектов». */
  onExit: () => void;
  onOpenProject: (projectId: string) => void;
};

type WizardStep = "profile" | "source" | "folder" | "progress";

const STEP_IDS = ["source", "folder", "progress"] as const;

const IDLE_INSPECTION: FolderInspection = { state: "idle" };
const noInspect = (): FolderInspection => IDLE_INSPECTION;

// Мастер «Клонировать проект из git»: три шага (источник, папка, загрузка) и,
// если не указан автор версий, перед ними короткое «Представься». Состояние
// шагов лежит здесь, поэтому «Назад» ничего не стирает.
const CloneWizardBody = ({
  folderSlot,
  serverSlot,
  folderless = false,
  initialTarget = null,
  onExit,
  onOpenProject,
}: CloneWizardProps) => {
  const { t } = useTranslation("gitRemote");
  const profileQuery = useProfile();
  const source = useCloneSource(initialTarget);
  const startClone = useStartClone();
  const startBundle = useStartCloneFromBundle();
  const useInspect = folderSlot?.useInspect ?? noInspect;
  const FolderPicker = folderSlot?.Picker;

  const [step, setStep] = useState<WizardStep | null>(null);
  const [nameDraft, setNameDraft] = useState<string | null>(null);
  const [folderDraft, setFolderDraft] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [folderError, setFolderError] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [bundleError, setBundleError] = useState<{
    code: string;
    message: string;
  } | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const operationQuery = useOperation(operationId);
  const autoChecked = useRef(false);

  // Пришли из окна подключения с адресом и доступом: сразу проверяем.
  useEffect(() => {
    if (autoChecked.current || initialTarget === null || !source.repoUrl)
      return;
    autoChecked.current = true;
    void source.runCheck();
  }, [initialTarget, source]);

  const currentStep: WizardStep | null =
    step ??
    (profileQuery.isLoading
      ? null
      : profileQuery.data?.is_default
        ? "profile"
        : "source");

  const fromBundle = source.tab === "bundle";
  const probe = source.check.status === "done" ? source.check.probe : null;
  const suggestion = suggestedProjectName({
    projectName: fromBundle ? null : (probe?.project?.name ?? null),
    repo: fromBundle ? null : (source.repoUrl?.repo ?? null),
    fileName: fromBundle ? (source.bundleFile?.name ?? null) : null,
  });
  const name = nameDraft ?? suggestion;
  const debouncedName = useDebouncedValue(name.trim(), 300);
  const defaults = useCloneDefaults(
    debouncedName,
    !folderless && (currentStep === "folder" || currentStep === "progress"),
  );
  const folder = folderDraft ?? defaults.data?.folder ?? "";
  const inspection = useInspect(folder.trim());

  const sourceLabel = fromBundle
    ? t("clone.folder.sourceBundle", { name: source.bundleFile?.name ?? "" })
    : [source.repoUrl?.host, source.repoUrl?.owner, source.repoUrl?.repo]
        .filter(Boolean)
        .join("/");

  // --- запуск --------------------------------------------------------------

  const start = async (): Promise<void> => {
    const target = folderless ? "" : folder.trim();
    if ((!folderless && target === "") || isStarting) return;
    setFolderError(null);
    setStartError(null);
    setIsStarting(true);
    try {
      const projectName = name.trim();
      let started;
      if (fromBundle) {
        if (!source.bundleFile) return;
        started = await startBundle.mutateAsync({
          file: source.bundleFile,
          ...(folderless ? {} : { folder: target }),
          ...(projectName !== "" ? { name: projectName } : {}),
          ...(source.bundlePassword.trim() !== ""
            ? { password: source.bundlePassword }
            : {}),
        });
      } else {
        if (!source.repoUrl) return;
        started = await startClone.mutateAsync({
          url: source.repoUrl.display_url,
          credential_id: source.credentialId,
          ...(source.branch !== "" ? { branch: source.branch } : {}),
          ...(folderless ? {} : { folder: target }),
          ...(projectName !== "" ? { name: projectName } : {}),
        });
      }
      // Пароль нужен был только для запуска.
      source.setBundlePassword("");
      setOperationId(started.operation_id);
      setStep("progress");
    } catch (error) {
      const code =
        readGitError(error)?.code ??
        (error instanceof ApiError ? error.code : "git_error");
      const message = describeGitError(error, t("clone.folder.failed"));
      const failure = cloneFailureTarget(code);
      if (failure === "profile") {
        setStep("profile");
      } else if (failure === "source") {
        if (isBundleCode(code)) {
          source.setBundlePassword("");
          setBundleError({ code, message });
        } else {
          source.setError(message);
        }
        source.resetCheck();
        setStep("source");
      } else if (failure === "folder") {
        setFolderError(message);
      } else {
        setStartError(message);
      }
    } finally {
      setIsStarting(false);
    }
  };

  // --- что показывать ---------------------------------------------------------

  if (currentStep === null) {
    return (
      <div
        role="status"
        className="flex items-center dim"
        style={{ gap: 8, minHeight: 160, justifyContent: "center" }}
      >
        <Spinner size="sm" />
        {t("clone.loading")}
      </div>
    );
  }

  // Когда клонирование закончилось, последний шаг заголовка тоже отмечен.
  const finalState =
    operationQuery.data?.status === "succeeded"
      ? "done"
      : operationQuery.data?.status === "failed"
        ? "error"
        : null;
  const stepperSteps: StepperStep[] = STEP_IDS.map((id) => ({
    id,
    label: t(`clone.steps.${id === "folder" && folderless ? "name" : id}`),
    ...(id === "progress" && finalState ? { state: finalState } : {}),
  }));

  return (
    <div className="flex flex-col" style={{ gap: 20 }}>
      <div>
        <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
          <GitBranch
            size={14}
            aria-hidden="true"
            style={{ color: "var(--accent)" }}
          />
          <span
            className="mono"
            style={{
              fontSize: 10,
              color: "var(--accent)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {t("clone.eyebrow")}
          </span>
        </div>
        <h2
          style={{
            margin: "0 0 4px",
            fontSize: 20,
            fontWeight: 600,
            letterSpacing: "-0.01em",
          }}
        >
          {t("clone.title")}
        </h2>
        <p
          className="dim"
          style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5 }}
        >
          {currentStep === "profile"
            ? t("clone.lead.profile")
            : currentStep === "folder"
              ? t(folderless ? "clone.lead.name" : "clone.lead.folder")
              : t("clone.description")}
        </p>
      </div>

      {currentStep !== "profile" && (
        <Stepper
          steps={stepperSteps}
          current={currentStep}
          label={t("clone.steps.label")}
        />
      )}

      {currentStep === "profile" && (
        <ProfileStep
          onCancel={onExit}
          onSaved={() => {
            setStep("source");
          }}
        />
      )}

      {currentStep === "source" && (
        <CloneSourceStep
          source={source}
          serverSlot={serverSlot}
          bundleError={bundleError}
          onCancel={onExit}
          onNext={() => {
            setBundleError(null);
            setStep("folder");
          }}
        />
      )}

      {currentStep === "folder" && (
        <CloneFolderStep
          sourceLabel={sourceLabel}
          name={name}
          namePlaceholder={suggestion}
          onNameChange={setNameDraft}
          folderless={folderless}
          folder={folder}
          onFolderChange={(value) => {
            setFolderDraft(value);
            setFolderError(null);
            setStartError(null);
          }}
          onBrowse={
            FolderPicker
              ? () => {
                  setPickerOpen(true);
                }
              : undefined
          }
          inspection={inspection}
          folderError={folderError}
          startError={startError}
          isStarting={isStarting}
          onBack={() => {
            setFolderError(null);
            setStartError(null);
            setStep("source");
          }}
          onStart={() => {
            void start();
          }}
        />
      )}

      {currentStep === "progress" && operationId !== null && (
        <CloneProgressStep
          operationId={operationId}
          fromBundle={fromBundle}
          onOpenProject={onOpenProject}
          onToList={onExit}
          onBackToFolder={(message) => {
            setFolderError(message);
            setOperationId(null);
            setStep("folder");
          }}
          onBackToSource={(failure) => {
            if (isBundleCode(failure.code)) {
              source.setBundlePassword("");
              setBundleError(failure);
            } else {
              source.setError(failure.message);
            }
            source.resetCheck();
            setOperationId(null);
            setStep("source");
          }}
          onProfile={() => {
            setOperationId(null);
            setStep("profile");
          }}
        />
      )}

      {FolderPicker && (
        <FolderPicker
          isOpen={pickerOpen}
          onClose={() => {
            setPickerOpen(false);
          }}
          onSelect={(path) => {
            setFolderDraft(path);
            setFolderError(null);
            setStartError(null);
          }}
          initialPath={folder || null}
        />
      )}
    </div>
  );
};

// Страница мастера: колонка 640 px по центру, прокручивается целиком, как у
// мастеров создания и подключения папки.
export const CloneWizard = (props: CloneWizardProps) => (
  <div className="flex h-full" style={{ background: "var(--bg-0)" }}>
    <div
      className="flex-1 flex flex-col items-center"
      style={{ minWidth: 0, overflow: "auto" }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 640,
          padding: "32px 24px 40px",
        }}
      >
        <CloneWizardBody {...props} />
      </div>
    </div>
  </div>
);

import {
  ArrowRight,
  Copy,
  Folder,
  GitPullRequest,
  KeyRound,
  NotebookPen,
  Plus,
  Send,
  TriangleAlert,
  Upload,
} from "lucide-react";
import {
  Suspense,
  lazy,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import { toast } from "@shared/lib";
import { Spinner } from "@shared/ui";
import { useChangesData } from "../changes/useChangesStatus";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import {
  isButtonStep,
  isPrimaryStep,
  resolveNextStep,
  type NextStep,
} from "./resolveNextStep";
import { FOCUS_PARAM } from "./focus";
import { useCopyVersion } from "./useCopyVersion";
import "./space-next-step.css";

const NextStepDialogs = lazy(() => import("./NextStepDialogs"));

const ICONS: Record<NextStep["kind"], ReactNode> = {
  connecting: null,
  folder: <Folder size="0.9375rem" aria-hidden="true" />,
  checkAccess: <KeyRound size="0.9375rem" aria-hidden="true" />,
  makeCopy: <Copy size="0.9375rem" aria-hidden="true" />,
  toDraft: <ArrowRight size="0.9375rem" aria-hidden="true" />,
  fixErrors: <TriangleAlert size="0.9375rem" aria-hidden="true" />,
  describe: <NotebookPen size="0.9375rem" aria-hidden="true" />,
  submit: <Send size="0.9375rem" aria-hidden="true" />,
  request: <GitPullRequest size="0.9375rem" aria-hidden="true" />,
  updateRequest: <Upload size="0.9375rem" aria-hidden="true" />,
  startNew: <Plus size="0.9375rem" aria-hidden="true" />,
};

/**
 * Главная кнопка полосы пространства (слот `nextStep`, pack-studio-ux.md, 4.3): одна кнопка,
 * которая называет следующий шаг. Какой это шаг, решает чистая `resolveNextStep` по статусу
 * изменений; здесь только подпись и действие. Кнопки нет у папки на диске и пока подключение
 * не готово: там подпись или чип.
 */
export const NextStepButton = () => {
  const { t } = useTranslation("packSpace");
  const { location } = useSpace();
  const nav = useSpaceNav();
  const data = useChangesData();
  const step = resolveNextStep(data.status);
  const copy = useCopyVersion();
  const [dialog, setDialog] = useState<"access" | "startOver" | null>(null);
  const ref = useRef<HTMLButtonElement>(null);

  // Ссылка из старого вида («новая версия»): создание копии не запускаем за человека, а ставим
  // на неё фокус, достаточно Enter.
  const wantsCopy = new URLSearchParams(location.search).get("copy") === "1";
  const focusCopy = useEffectEvent(() => {
    ref.current?.focus();
    nav.go({ extra: { copy: null } });
  });
  useEffect(() => {
    if (wantsCopy && step?.kind === "makeCopy") focusCopy();
  }, [wantsCopy, step?.kind]);

  if (!step) return null;

  const label = ((): string => {
    switch (step.kind) {
      case "toDraft":
        return t("next.toDraft", { version: step.version.version });
      case "fixErrors":
        return t("next.fixErrors", { count: step.count });
      case "request":
        return t(
          step.checks === "unknown"
            ? "next.requestOpen"
            : `next.request.${step.checks}`,
          { label: step.label, ...(step.progress ?? {}) },
        );
      default:
        return t(`next.${step.kind}`);
    }
  })();

  if (step.kind === "connecting") {
    return (
      <span className="sp-ns-note" role="status" data-testid="sp-next-step">
        <Spinner size="sm" />
        {label}
      </span>
    );
  }
  if (!isButtonStep(step)) {
    return (
      <span
        className="sp-ns-chip"
        title={t("next.folderTitle")}
        data-testid="sp-next-step"
        data-step={step.kind}
      >
        {ICONS[step.kind]}
        {label}
      </span>
    );
  }

  const act = () => {
    switch (step.kind) {
      case "checkAccess":
        setDialog("access");
        break;
      case "makeCopy":
        void copy.run();
        break;
      case "toDraft":
        nav.go({ ref: step.version });
        break;
      case "fixErrors":
        nav.go({ tab: "check", part: "issues", changes: false });
        break;
      case "describe":
        nav.go({ changes: true, extra: { [FOCUS_PARAM]: "notes" } });
        break;
      case "submit":
      case "updateRequest":
        nav.go({ changes: true, extra: { [FOCUS_PARAM]: "submit" } });
        break;
      case "request":
        nav.go({ changes: true });
        break;
      case "startNew":
        setDialog("startOver");
        break;
    }
  };

  const busy = step.kind === "makeCopy" && copy.pending;
  // Ошибка «Править копию» не прячется в углу: тост с причиной словами.
  const copyError = step.kind === "makeCopy" ? copy.error : null;
  return (
    <>
      <button
        ref={ref}
        type="button"
        className={`btn sp-ns${isPrimaryStep(step) ? " primary" : ""}`}
        disabled={busy}
        title={t(`next.hint.${step.kind}`)}
        onClick={act}
        data-testid="sp-next-step"
        data-step={step.kind}
      >
        {busy ? <Spinner size="sm" /> : ICONS[step.kind]}
        <span className="sp-ns-label">{label}</span>
      </button>
      {copyError !== null && <CopyError error={copyError} />}
      {dialog !== null && (
        <Suspense fallback={null}>
          <NextStepDialogs
            dialog={dialog}
            workspace={data.raw.workspace}
            git={data.raw.git}
            onClose={() => {
              setDialog(null);
            }}
          />
        </Suspense>
      )}
    </>
  );
};

/** Причина, почему копию создать не удалось: один раз тостом, не залипает в полосе. */
const CopyError = ({ error }: { error: unknown }) => {
  useEffect(() => {
    toast.error(packErrorText(error));
  }, [error]);
  return null;
};

export default NextStepButton;

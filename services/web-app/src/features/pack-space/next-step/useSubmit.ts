import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  forkRequired,
  notifyPackFilesSaved,
  packStudioKeys,
  useMovePackVersionEdits,
  usePackFilesRevision,
  usePackOfficial,
  usePackVersionState,
  useProposePack,
  useReleasePackVersion,
  type ForkRequired,
  type PackForkChoice,
  type PackProposeResponse,
  type PackVersionRef,
  type PackVersionState,
} from "@entities/pack-studio";
import type { ImpactReport } from "@features/pack-git";
import { currentClass } from "@features/pack-version";
import { toast } from "@shared/lib";
import type { ChangesData } from "../changes/useChangesStatus";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import {
  FOCUS_PARAM,
  NOTES_FIELD_ID,
  PRIMARY_BUTTON_ID,
  focusElement,
  isFocusTarget,
} from "./focus";
import { consentAsked, type LicenseInfo } from "./submitErrors";
import { planSteps, runSteps, type SubmitStep } from "./submitSteps";
import { useVersionNotes, type VersionNotes } from "./useVersionNotes";

export type SubmitOptions = {
  data: ChangesData;
  /** Что сказал блок «что изменится у студентов»; `null`, пока не ответил. */
  impact: ImpactReport | null;
  /** Есть ли версии с правками, для которых считается «что изменится». */
  hasImpact: boolean;
};

/** Почему отправка сейчас недоступна; `null`: можно. */
export type SubmitBlocker =
  | "errors"
  | "loading"
  | "notes"
  | "saving"
  | "consent"
  | "impact"
  | "ack"
  | "fork"
  | "moving";

export type SubmitFailure = { step: SubmitStep; error: unknown };

export type SubmitController = {
  /** Раздел отправки есть на экране: есть что отправлять и запрос не принят. */
  available: boolean;
  /** Запрос уже открыт: отправка добавляет правки в него. */
  update: boolean;
  version: PackVersionRef;
  /** Отчёт открытой версии: только для черновика с правками. */
  state: PackVersionState | null;
  stateLoading: boolean;
  notes: VersionNotes;
  // Выпуск.
  release: boolean;
  setRelease: (value: boolean) => void;
  /** Выпуск в этой отправке возможен: версия черновик, номер подходит. */
  releasable: boolean;
  setDefault: boolean;
  setSetDefault: (value: boolean) => void;
  releaseClass: ReturnType<typeof currentClass>;
  // Описание запроса.
  title: string;
  setTitle: (value: string) => void;
  description: string;
  setDescription: (value: string) => void;
  // Лицензия официальных паков.
  consent: LicenseInfo | null;
  accepted: boolean;
  setAccepted: (value: boolean) => void;
  // «Что изменится у студентов».
  impactPending: boolean;
  needsAck: boolean;
  ack: boolean;
  setAck: (value: boolean) => void;
  // Форк при отказе в праве.
  fork: ForkRequired | null;
  forkMode: "create" | "url";
  setForkMode: (value: "create" | "url") => void;
  forkUrl: string;
  setForkUrl: (value: string) => void;
  // Ход отправки.
  running: boolean;
  /** Шаги этой отправки и какие из них уже сделаны. */
  plan: readonly SubmitStep[] | null;
  done: readonly SubmitStep[];
  current: SubmitStep | null;
  failure: SubmitFailure | null;
  /** Итог, если запрос не открылся (ветка ушла, а запрос не создался). */
  outcome: PackProposeResponse | null;
  blocker: SubmitBlocker | null;
  run: () => void;
  /** Перенести правки в свободный номер, когда выбранный уже выпущен в основной ветке. */
  moveTo: (version: string) => void;
  moving: boolean;
  moveError: unknown;
  /** Прокрутить к заметкам и поставить фокус. */
  focusNotes: () => void;
};

const trimmed = (value: string): string | null => {
  const text = value.trim();
  return text === "" ? null : text;
};

/**
 * Отправка в панели «Изменения» (pack-studio-ux.md, 5.6): всё, что нужно разделу отправки и
 * кнопке подвала. Последовательность «заметки, выпуск, отправка» живёт в `submitSteps.ts`, здесь
 * она связана с запросами и полями. Оборванная отправка не теряет сделанного: повтор начинается
 * с упавшего шага.
 */
export const useSubmit = ({
  data,
  impact,
  hasImpact,
}: SubmitOptions): SubmitController => {
  const { t } = useTranslation("packSpace");
  const { workspace, versionRef, location } = useSpace();
  const nav = useSpaceNav();
  const client = useQueryClient();
  const { status, raw } = data;
  const git = raw.git;
  const id = workspace.id;
  const request = status.request;
  const update = request.kind === "open";
  const live =
    status.connection === "ready" &&
    status.workspaceKind === "git" &&
    status.load === "ready" &&
    git !== null;
  const available =
    live &&
    status.changedFiles > 0 &&
    (request.kind === "none" || (update && request.newEdits));

  // Отчёт версии: класс, номера, что записано. Только для черновика, где есть правки.
  const revision = usePackFilesRevision(id);
  const wantState =
    available && !status.released && status.changedInVersion > 0;
  const stateQuery = usePackVersionState(
    id,
    wantState ? versionRef : null,
    String(revision),
  );
  const loaded = stateQuery.data;
  const fresh =
    loaded?.version.version === versionRef.version && !loaded.released
      ? loaded
      : null;
  const state = wantState ? fresh : null;
  // Пока читается отчёт этой версии (или показан отчёт прежней), заметки и выпуск не готовы.
  const loadingState = stateQuery.isPending || stateQuery.isPlaceholderData;
  const notes = useVersionNotes(id, state);

  const releasable = state?.number_ok === true;
  const defaultRelease =
    releasable && !(state.registered && !state.release_outdated);
  const [releaseChoice, setReleaseChoice] = useState<boolean | null>(null);
  const release = releasable && (releaseChoice ?? defaultRelease);
  const [setDefault, setSetDefault] = useState(true);
  const releaseClass = state ? currentClass(state) : null;

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [ack, setAck] = useState(false);
  const [fork, setFork] = useState<ForkRequired | null>(null);
  const [forkMode, setForkMode] = useState<"create" | "url">("url");
  const [forkUrl, setForkUrl] = useState("");

  // Лицензия официальных паков: спрашивается до первой отправки и ещё раз, если сервер попросил.
  const ws = git?.workspace ?? workspace;
  const isOfficial = ws.official === true;
  const official = usePackOfficial(available && isOfficial);
  const [asked, setAsked] = useState<LicenseInfo | null>(null);
  const repo = official.data?.repo;
  const consent: LicenseInfo | null =
    asked ??
    (isOfficial && !ws.license_accepted_at
      ? {
          license: repo?.license ?? "",
          licenseUrl: repo?.license_url ?? null,
          contributingUrl: repo?.contributing_url ?? null,
        }
      : null);

  const impactPending = hasImpact && (impact === null || impact.pending);
  const needsAck = hasImpact && impact?.needsAck === true;

  // Ход.
  const [running, setRunning] = useState(false);
  const [plan, setPlan] = useState<readonly SubmitStep[] | null>(null);
  const [done, setDone] = useState<readonly SubmitStep[]>([]);
  const [current, setCurrent] = useState<SubmitStep | null>(null);
  const [failure, setFailure] = useState<SubmitFailure | null>(null);
  const [outcome, setOutcome] = useState<PackProposeResponse | null>(null);

  const releaseApi = useReleasePackVersion(id);
  const proposeApi = useProposePack(id);
  const moveApi = useMovePackVersionEdits(id);

  // Версия сменилась (номер, перенос правок, другая версия): прежний ход к ней не относится.
  const versionKey = `${versionRef.pack}/${versionRef.template}/${versionRef.version}`;
  const [seenKey, setSeenKey] = useState(versionKey);
  if (seenKey !== versionKey) {
    setSeenKey(versionKey);
    setPlan(null);
    setDone([]);
    setFailure(null);
    setOutcome(null);
    setReleaseChoice(null);
  }

  const forkChoice: PackForkChoice | null = !fork
    ? null
    : fork.canCreate && !ws.service_access && forkMode === "create"
      ? { create: true }
      : { url: forkUrl.trim() };

  let blocker: SubmitBlocker | null = null;
  if (moveApi.isPending) blocker = "moving";
  else if (status.errors > 0) blocker = "errors";
  else if (wantState && loadingState) blocker = "loading";
  else if (state !== null && notes.problem !== null) blocker = "notes";
  else if (notes.saving) blocker = "saving";
  else if (consent !== null && !accepted) blocker = "consent";
  else if (impactPending) blocker = "impact";
  else if (needsAck && !ack) blocker = "ack";
  else if (
    fork !== null &&
    !(fork.canCreate && !ws.service_access && forkMode === "create") &&
    forkUrl.trim() === ""
  ) {
    blocker = "fork";
  }

  const send = async (): Promise<PackProposeResponse> => {
    const summary = impact?.summary ?? "";
    const body = [trimmed(description), trimmed(summary)]
      .filter((part): part is string => part !== null)
      .join("\n\n");
    return proposeApi.mutateAsync({
      title: update ? null : trimmed(title),
      description: update || body === "" ? null : body,
      message: null,
      ...(forkChoice ? { fork: forkChoice } : {}),
      ...(consent && accepted ? { accept_license: true } : {}),
    });
  };

  const run = () => {
    if (blocker !== null || running || !live) return;
    const steps = plan ?? planSteps({ notesPending: notes.pending, release });
    const resumed = plan !== null;
    setPlan(steps);
    if (!resumed) setDone([]);
    setFailure(null);
    setOutcome(null);
    setRunning(true);
    void runSteps(
      steps,
      resumed ? done : [],
      {
        notes: notes.flush,
        release: async () => {
          if (!state || releaseClass === null) return;
          await releaseApi.mutateAsync({
            ref: state.version,
            body: { kind: releaseClass, set_default: setDefault },
          });
        },
        send,
      },
      setCurrent,
    ).then((out) => {
      setRunning(false);
      setCurrent(null);
      setDone(out.done);
      if (!out.ok) {
        setFailure({ step: out.step, error: out.error });
        const needFork = forkRequired(out.error);
        if (needFork) {
          setFork(needFork);
          setForkMode(
            needFork.canCreate && !ws.service_access ? "create" : "url",
          );
        }
        const consentRequest = consentAsked(out.error);
        if (consentRequest) {
          setAsked(consentRequest);
          setAccepted(false);
        }
        return;
      }
      // Ход закончен: следующая отправка начнётся с чистого листа.
      setPlan(null);
      setDone([]);
      setFork(null);
      const result = out.result;
      const pull = result.pull_request;
      if (pull) {
        const label = `${result.git.provider === "gitlab" ? "!" : "#"}${String(pull.number)}`;
        toast.success(
          t(pull.created ? "submit.done.opened" : "submit.done.updated", {
            label,
          }),
        );
      } else {
        // Ветка отправлена, а запрос не создался: подробности и ссылка остаются в разделе.
        setOutcome(result);
      }
      notifyPackFilesSaved(id);
    });
  };

  const moveTo = (version: string) => {
    if (!state) return;
    moveApi.mutate(
      { ref: state.version, version },
      {
        onSuccess: (moved) => {
          toast.success(
            t("submit.move.done", { version: moved.version.version }),
          );
          void client
            .refetchQueries({ queryKey: packStudioKeys.tree(id) })
            .then(() => {
              nav.go({
                ref: {
                  pack: moved.version.pack,
                  template: moved.version.template,
                  version: moved.version.version,
                },
              });
            });
        },
      },
    );
  };

  // Внимание по адресу: «Описать изменения» ведёт к заметкам, «Отправить» к кнопке отправки.
  const focusNotes = () => {
    focusElement(NOTES_FIELD_ID);
  };
  const wanted = new URLSearchParams(location.search).get(FOCUS_PARAM);
  const ready = available && (!wantState || state !== null);
  const applyFocus = useEffectEvent(() => {
    // Заметок уже нет (написаны): внимание к кнопке отправки.
    if (!(wanted === "notes" && focusElement(NOTES_FIELD_ID))) {
      focusElement(PRIMARY_BUTTON_ID);
    }
    nav.go({ extra: { [FOCUS_PARAM]: null } });
  });
  useEffect(() => {
    if (isFocusTarget(wanted) && ready) applyFocus();
  }, [wanted, ready]);

  return {
    available,
    update,
    version: versionRef,
    state,
    stateLoading: wantState && loadingState,
    notes,
    release,
    setRelease: setReleaseChoice,
    releasable,
    setDefault,
    setSetDefault,
    releaseClass,
    title,
    setTitle,
    description,
    setDescription,
    consent,
    accepted,
    setAccepted,
    impactPending,
    needsAck,
    ack,
    setAck,
    fork,
    forkMode,
    setForkMode,
    forkUrl,
    setForkUrl,
    running,
    plan,
    done,
    current,
    failure,
    outcome,
    blocker,
    run,
    moveTo,
    moving: moveApi.isPending,
    moveError: moveApi.error,
    focusNotes,
  };
};

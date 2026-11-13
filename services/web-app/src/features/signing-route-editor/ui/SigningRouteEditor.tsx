import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, PenLine, Send } from "lucide-react";
import type { z } from "zod";
import { useIsProjectBuilding } from "@entities/compile";
import { useDocuments } from "@entities/document";
import type { ProjectResponseSchema } from "@entities/project";
import { useBootstrap } from "@entities/session";
import { useSetSlotOptional, useSignaturesState } from "@entities/signature";
import { useSubmissionProfiles } from "@entities/submission";
import {
  isActionable,
  isResend,
  isRouteEditable,
  signingPagePath,
  signingRouteKeys,
  useCreateSigningRoute,
  useSendSigningRoute,
  useSigningRoute,
  useSigningRoutePreview,
  useSigningRoutes,
  useUpdateSigningRoute,
  type RouteSlotRef,
  type SigningRoute,
  type UpdateSigningRouteRequest,
} from "@entities/signing-route";
import { ApiError, failureCode } from "@shared/api";
import { pickLocalized, toast } from "@shared/lib";
import { Notice, Spinner } from "@shared/ui";
import { usePersonaLabel } from "../lib/labels";
import { chooseRoute } from "../model/chooseRoute";
import {
  draftOf,
  withExtraSlot,
  withoutExtraSlot,
  type DraftSteps,
} from "../model/routeDraft";
import { RouteDocsCard } from "./RouteDocsCard";
import { RoutePlacementsCard } from "./RoutePlacementsCard";
import { RouteSendCard } from "./RouteSendCard";
import { RouteStepsCard } from "./RouteStepsCard";
import { SenderSignatureCard } from "./SenderSignatureCard";

type Project = z.infer<typeof ProjectResponseSchema>;

export type SigningRouteEditorProps = {
  project: Project;
  profileId: string;
};

const PAGE_STYLE = {
  padding: "24px 32px",
  overflowY: "auto",
  flex: 1,
  minHeight: 0,
} as const;

// Согласующим может быть руководитель; авторы и так стоят в маршруте со своими слотами.
const APPROVER_PERSONAS = [
  "supervisor",
  "co_supervisor",
  "academic_supervisor",
];

const Card = ({
  title,
  children,
  testId,
}: {
  title: string;
  children: React.ReactNode;
  testId?: string;
}) => (
  <section
    className="card"
    style={{
      padding: "1.125rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.75rem",
    }}
    data-testid={testId}
  >
    <h3 style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 600 }}>
      {title}
    </h3>
    {children}
  </section>
);

/** Пересчитать предпросмотр, когда меняется то, что он учитывает, но не маршрут: сборка, подписи. */
const useRefreshPreviewOn = (
  projectId: string,
  routeId: string,
  signal: unknown,
) => {
  const client = useQueryClient();
  const last = useRef(signal);
  useEffect(() => {
    if (last.current === signal) return;
    last.current = signal;
    if (routeId === "") return;
    void client.invalidateQueries({
      queryKey: signingRouteKeys.preview(projectId, routeId),
    });
  }, [client, projectId, routeId, signal]);
};

/**
 * Экран «Отправка на подписание» (docs/design/signing-route.md, 3.1): документы точки, шаги
 * с людьми, где стоят подписи, своя подпись, срок и сообщение, что мешает, и отправка.
 * Черновик точки создаётся при первом заходе; правки сразу уходят на сервер целиком (PUT).
 */
export const SigningRouteEditor = ({
  project,
  profileId,
}: SigningRouteEditorProps) => {
  const { t, i18n } = useTranslation("signingRouteEditor");
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const boot = useBootstrap().data;
  const isServer = boot?.mode === "server";
  const meId = boot?.user?.id ?? null;
  const pointPath = `/projects/${encodeURIComponent(project.id)}/submit/cp/${encodeURIComponent(profileId)}`;

  const list = useSigningRoutes(project.id, profileId, { enabled: isServer });
  const {
    mutate: createRoute,
    isPending: isCreating,
    error: createError,
  } = useCreateSigningRoute(project.id);
  const choice = chooseRoute(list.data?.items, params.get("route"));
  // Первый заход на точку без маршрута: черновик из пака (сервер вернёт уже открытый, если он есть).
  const asked = useRef(false);
  useEffect(() => {
    if (choice.kind !== "create" || asked.current) return;
    asked.current = true;
    createRoute(profileId);
  }, [choice.kind, createRoute, profileId]);

  const routeId =
    choice.kind === "use" || choice.kind === "completed" ? choice.id : "";
  const routeQuery = useSigningRoute(project.id, routeId, {
    enabled: routeId !== "",
  });
  const route = routeQuery.data;
  const editable = route !== undefined && isRouteEditable(route.status);
  const preview = useSigningRoutePreview(project.id, routeId, {
    enabled: editable,
  });
  const update = useUpdateSigningRoute(project.id, routeId);
  const send = useSendSigningRoute(project.id, routeId);
  const signatures = useSignaturesState(project.id);
  const setOptional = useSetSlotOptional();
  const documents = useDocuments(project.id);
  // Срок сдачи точки (signing-route.md, 16.2): строка под сроком маршрута.
  const profiles = useSubmissionProfiles(project.id);
  const personaLabel = usePersonaLabel(project.authors);
  const [sendError, setSendError] = useState<string | null>(null);
  // «Отправить и подписать»: маршрут ушёл, а подпись отправителя не поставлена (причина отказа).
  const [unsigned, setUnsigned] = useState<string | null>(null);
  // Помеха «подпись не размещена» ведёт к слоту в блоке «Где подписи».
  const [placeFocus, setPlaceFocus] = useState<
    (RouteSlotRef & { n: number }) | null
  >(null);

  const building = useIsProjectBuilding(project.id);
  // Ссылка на данные меняется только вместе с содержимым (structural sharing запросов).
  useRefreshPreviewOn(project.id, routeId, signatures.data);
  useRefreshPreviewOn(project.id, routeId, building);

  const errorText = (error: unknown): string => {
    const code = failureCode(error);
    const known: Record<string, string> = {
      doc_changed: t("error.doc_changed"),
      route_blocked: t("error.route_blocked"),
      invalid_transition: t("error.invalid_transition"),
      passphrase_required: t("error.passphrase_required"),
      optional_forbidden: t("placements.optionalRequired"),
      slot_signed: t("placements.optionalSigned"),
      network: t("error.network"),
    };
    if (code === "rate_limited" && error instanceof ApiError) {
      const retry = Number(error.data?.retry_after ?? 60);
      return t("error.rate_limited", { seconds: retry });
    }
    if (code in known) return known[code] ?? "";
    return error instanceof ApiError && error.detail !== ""
      ? error.detail
      : t("error.generic");
  };

  const save = (body: UpdateSigningRouteRequest) => {
    update.mutate(body, {
      onError: (error) => {
        toast.error(`${t("error.save")}: ${errorText(error)}`);
      },
    });
  };

  if (boot && !isServer) {
    return (
      <div style={PAGE_STYLE}>
        <Head title={t("title")} back={pointPath} />
        <div style={{ marginTop: "1.25rem" }}>
          <Notice tone="info" text={t("localOnly")} />
        </div>
      </div>
    );
  }

  const failed = list.isError || routeQuery.isError || createError !== null;
  if (failed) {
    const error = list.error ?? routeQuery.error ?? createError;
    return (
      <div style={PAGE_STYLE}>
        <Head title={t("title")} back={pointPath} />
        <div style={{ marginTop: "1.25rem" }}>
          <Notice
            tone="err"
            role="alert"
            text={`${t("loadFailed")}: ${errorText(error)}`}
            action={
              <button
                type="button"
                className="btn xs"
                onClick={() => {
                  void list.refetch();
                  if (routeId !== "") void routeQuery.refetch();
                }}
              >
                {t("retry")}
              </button>
            }
          />
        </div>
      </div>
    );
  }

  if (!route) {
    return (
      <div style={PAGE_STYLE}>
        <Head title={t("title")} back={pointPath} />
        <div
          className="flex justify-center"
          style={{ padding: "2rem" }}
          data-testid="route-loading"
        >
          <Spinner />
        </div>
      </div>
    );
  }

  const body = (): UpdateSigningRouteRequest => draftOf(route);
  const onSteps = (steps: DraftSteps) => {
    save({ ...body(), steps });
  };
  const onAddExtra = (slot: RouteSlotRef) => {
    save(withExtraSlot(body(), slot));
  };
  const onRemoveExtra = (slot: RouteSlotRef) => {
    save(withoutExtraSlot(body(), route, slot));
  };
  // «Подпись необязательна» (13.9): флаг живёт в состоянии подписей, маршрут перечитывается.
  const onSetOptional = (slot: RouteSlotRef, optional: boolean) => {
    setOptional.mutate(
      {
        projectId: project.id,
        docId: slot.doc_id,
        slotId: slot.slot_id,
        profileId: route.profile.id,
        optional,
      },
      {
        onError: (error) => {
          toast.error(`${t("placements.optionalFailed")}: ${errorText(error)}`);
        },
      },
    );
  };

  const onSend = async (input: {
    deadline: string | null;
    message: string | null;
    sign: { passphrase: string | null } | null;
  }) => {
    setSendError(null);
    try {
      if (input.deadline !== route.deadline || input.message !== route.message)
        await update.mutateAsync({
          ...body(),
          deadline: input.deadline,
          message: input.message,
        });
      const shown = preview.data;
      if (!shown) return;
      const key = shown.sender_key;
      await send.mutateAsync({
        expected: Object.fromEntries(
          shown.docs.map((doc) => [doc.doc_id, doc.token ?? ""]),
        ),
        sign:
          input.sign && key
            ? { identity_id: key.id, passphrase: input.sign.passphrase }
            : null,
      });
      toast.success(input.sign ? t("send.sentSigned") : t("send.sent"));
      void navigate(pointPath);
    } catch (error) {
      // Отказ подписи после записи отправки (`sent: true`): маршрут уже у подписантов, это не
      // сбой отправки. Экран остаётся на маршруте и ведёт отправителя на его страницу подписи.
      if (
        error instanceof ApiError &&
        error.code === "sign_failed" &&
        error.data?.sent === true
      ) {
        setUnsigned(error.detail);
        return;
      }
      setSendError(errorText(error));
      void preview.refetch();
    }
  };

  const people = route.steps.flat();
  const myStepIndex = route.steps.findIndex((step) =>
    step.some((p) => meId !== null && p.user_id === meId),
  );
  const me =
    myStepIndex === -1
      ? undefined
      : route.steps[myStepIndex]?.find((p) => p.user_id === meId);
  const present = new Set(people.map((p) => p.persona));
  const busy = update.isPending || send.isPending;

  const steps = (
    <RouteStepsCard
      projectId={project.id}
      route={route}
      preview={editable ? preview.data : undefined}
      editable={editable}
      busy={busy}
      meId={meId}
      personaLabel={personaLabel}
      approverPersonas={APPROVER_PERSONAS.filter((p) => !present.has(p))}
      registrationClosed={boot?.auth.registration_mode === "closed"}
      onChange={onSteps}
    />
  );

  return (
    <div style={PAGE_STYLE} data-testid="signing-route-editor">
      <Head
        title={t("title")}
        sub={pickLocalized(route.profile.name, i18n.language, route.profile.id)}
        back={pointPath}
      />
      <StatusNotice
        route={route}
        onNewRoute={() => {
          createRoute(profileId);
        }}
        isCreating={isCreating}
      />
      {route.status === "active" && me && isActionable(me.next_action) && (
        <div style={{ marginTop: "0.75rem" }} data-testid="route-my-turn">
          <Notice
            tone="warn"
            role={unsigned === null ? "status" : "alert"}
            text={[
              me.next_action === "sign"
                ? t("mine.sentUnsigned")
                : t("mine.yourTurn"),
              unsigned === null || unsigned === ""
                ? null
                : t("mine.signFailed", { reason: unsigned }),
            ]
              .filter((part) => part !== null)
              .join(" ")}
            action={
              <Link
                to={signingPagePath(project.id, route.id)}
                className="btn xs primary"
                data-testid="route-go-sign"
              >
                <PenLine size="0.6875rem" aria-hidden="true" />
                {me.next_action === "approve"
                  ? t("mine.goApprove")
                  : t("mine.goSign")}
              </Link>
            }
          />
        </div>
      )}

      {editable ? (
        <>
          <div
            className="grid-split"
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
              gap: "1.25rem",
              marginTop: "1.25rem",
              alignItems: "start",
            }}
          >
            <div className="flex flex-col" style={{ gap: "1rem" }}>
              <Card title={t("docs.title")} testId="route-docs">
                <RouteDocsCard
                  projectId={project.id}
                  route={route}
                  preview={preview.data}
                  editable
                />
              </Card>
              <Card title={t("steps.title")} testId="route-steps">
                {steps}
              </Card>
            </div>
            <div
              className="flex flex-col"
              style={{ gap: "1rem", position: "sticky", top: 0 }}
            >
              <Card title={t("mine.title")} testId="route-mine">
                <SenderSignatureCard
                  projectId={project.id}
                  me={me}
                  myStep={myStepIndex === -1 ? null : myStepIndex + 1}
                  preview={preview.data}
                  state={signatures.data}
                  editable
                />
              </Card>
              <Card title={t("send.title")} testId="route-send-card">
                <RouteSendCard
                  key={route.id}
                  route={route}
                  preview={preview.data}
                  previewFailed={preview.isError}
                  resend={isResend(route.status)}
                  personaLabel={personaLabel}
                  sending={send.isPending}
                  error={sendError}
                  onSaveTexts={(texts) => {
                    save({ ...body(), ...texts });
                  }}
                  onSend={(input) => {
                    void onSend(input);
                  }}
                  onPlace={(slot) => {
                    setPlaceFocus((prev) => ({
                      ...slot,
                      n: (prev?.n ?? 0) + 1,
                    }));
                  }}
                  pointProfile={profiles.data?.find(
                    (p) => p.id === route.profile.id,
                  )}
                />
              </Card>
            </div>
          </div>
          <div style={{ marginTop: "1.25rem" }}>
            <Card title={t("placements.title")} testId="route-placements">
              <RoutePlacementsCard
                projectId={project.id}
                route={route}
                preview={preview.data}
                editable
                busy={busy}
                state={signatures.data}
                documents={documents.data}
                personaLabel={personaLabel}
                docLang={project.lang ?? i18n.language}
                onAddExtra={onAddExtra}
                onRemoveExtra={onRemoveExtra}
                onSetOptional={onSetOptional}
                optionalPending={
                  setOptional.isPending
                    ? {
                        doc_id: setOptional.variables.docId,
                        slot_id: setOptional.variables.slotId,
                      }
                    : null
                }
                focus={placeFocus}
              />
            </Card>
          </div>
        </>
      ) : (
        <div style={{ marginTop: "1.25rem" }}>
          <Card title={t("steps.title")} testId="route-steps">
            {steps}
          </Card>
        </div>
      )}
    </div>
  );
};

const Head = ({
  title,
  sub,
  back,
}: {
  title: string;
  sub?: string;
  back: string;
}) => {
  const { t } = useTranslation("signingRouteEditor");
  return (
    <div
      className="flex items-center"
      style={{ gap: "0.75rem", flexWrap: "wrap" }}
    >
      <div
        className="flex items-center justify-center shrink-0"
        style={{
          width: "2.375rem",
          height: "2.375rem",
          borderRadius: "0.625rem",
          background: "var(--accent-soft)",
          color: "var(--accent)",
        }}
      >
        <Send size="1.125rem" aria-hidden="true" />
      </div>
      {/* На узком экране ссылка «К контрольной точке» уходит на свою строку, заголовок не сжимается. */}
      <div
        className="flex flex-col"
        style={{ gap: "0.125rem", flex: "1 1 12rem", minWidth: 0 }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: "1.125rem",
            fontWeight: 600,
            letterSpacing: "-0.01em",
          }}
        >
          {title}
        </h2>
        {sub && (
          <p className="dim" style={{ margin: 0, fontSize: "0.78125rem" }}>
            {sub}
          </p>
        )}
      </div>
      <Link to={back} className="btn sm ghost">
        <ArrowLeft size="0.75rem" aria-hidden="true" />
        {t("back")}
      </Link>
    </div>
  );
};

/** Почему маршрут не черновик: идёт, остановлен, возвращён, отменён или завершён. */
const StatusNotice = ({
  route,
  onNewRoute,
  isCreating,
}: {
  route: SigningRoute;
  onNewRoute: () => void;
  isCreating: boolean;
}) => {
  const { t } = useTranslation("signingRouteEditor");
  const text = (() => {
    switch (route.status) {
      case "active":
        return t("status.active", {
          step: route.current_step ?? route.steps.length,
          total: route.steps.length,
        });
      case "paused":
        return t("status.paused", {
          reason: t(`stopReason.${route.stop_reason ?? "rebuilt"}`),
        });
      case "returned": {
        const back = [...route.events]
          .reverse()
          .find((e) => e.kind === "returned");
        return back?.comment
          ? t("status.returned", {
              who: back.who ?? t("status.someone"),
              comment: back.comment,
            })
          : t("status.returnedNoComment");
      }
      case "cancelled":
        return t("status.cancelled");
      case "completed":
        return t("status.completed");
      case "archived":
        return t("status.archived");
      case "draft":
        return null;
    }
  })();
  if (text === null) return null;
  const tone =
    route.status === "completed"
      ? "info"
      : route.status === "active"
        ? "info"
        : "warn";
  return (
    <div style={{ marginTop: "1.25rem" }} data-testid="route-status">
      <Notice
        tone={tone}
        role="status"
        text={text}
        action={
          route.status === "completed" ? (
            <button
              type="button"
              className="btn xs"
              disabled={isCreating}
              onClick={onNewRoute}
            >
              {t("newRoute")}
            </button>
          ) : undefined
        }
      />
    </div>
  );
};

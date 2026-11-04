import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { Inbox, Info, ListChecks } from "lucide-react";
import { useRequirements } from "@entities/requirements";
import { i18n } from "@shared/lib";
import { Spinner } from "@shared/ui/Spinner";
import { PageHead } from "./PageHead";
import { RequirementsFormatEditor } from "./RequirementsFormatEditor";

type Status = "ok" | "warn" | "err";

const statusLabel = (status: Status): string =>
  ({
    ok: i18n.t("workspace:requirements.statusOk"),
    warn: i18n.t("workspace:requirements.statusWarn"),
    err: i18n.t("workspace:requirements.statusErr"),
  })[status];

const Code = ({ children }: { children: React.ReactNode }) => (
  <span
    className="mono"
    style={{
      fontSize: "0.71875rem",
      padding: "1px 0.375rem",
      borderRadius: "0.3125rem",
      background: "var(--bg-2)",
      border: "1px solid var(--border)",
      color: "var(--fg-1)",
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </span>
);

const HowItWorks = () => {
  const { t } = useTranslation("workspace");
  const steps: { text: string; code: string | null }[] = [
    {
      text: t("requirements.step1Text"),
      code: "\\req{R-01}{Текст требования}",
    },
    { text: t("requirements.step2Text"), code: "\\reqref{R-01}" },
    { text: t("requirements.step3Text"), code: null },
  ];
  const legend: { status: Status; hint: string }[] = [
    { status: "ok", hint: t("requirements.legendOk") },
    { status: "warn", hint: t("requirements.legendWarn") },
    { status: "err", hint: t("requirements.legendErr") },
  ];
  return (
    <div
      className="card"
      style={{
        marginTop: "1.25rem",
        padding: "1.125rem",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <div>
        <h3
          style={{
            margin: 0,
            fontSize: "0.8125rem",
            fontWeight: 600,
            color: "var(--fg-0)",
          }}
        >
          {t("requirements.howItWorks")}
        </h3>
        <p
          className="dim"
          style={{
            margin: "0.25rem 0 0",
            fontSize: "0.75rem",
            lineHeight: 1.55,
          }}
        >
          {t("requirements.howItWorksIntroPrefix")}
          <span className="mono">.tex</span>
          {t("requirements.howItWorksIntroSuffix")}
        </p>
      </div>

      <div
        style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}
      >
        {steps.map((s, i) => (
          <div
            key={i}
            className="flex items-center"
            style={{ gap: "0.625rem" }}
          >
            <span
              className="flex items-center justify-center shrink-0"
              style={{
                width: "1.25rem",
                height: "1.25rem",
                borderRadius: "0.375rem",
                background: "var(--accent-soft)",
                color: "var(--accent)",
                fontSize: "0.6875rem",
                fontWeight: 700,
              }}
            >
              {i + 1}
            </span>
            <span
              style={{
                fontSize: "0.78125rem",
                color: "var(--fg-1)",
                lineHeight: 1.5,
              }}
            >
              {s.text}
              {s.code ? (
                <>
                  {" "}
                  <Code>{s.code}</Code>
                </>
              ) : null}
            </span>
          </div>
        ))}
      </div>

      <div
        style={{
          borderTop: "1px solid var(--border)",
          paddingTop: "0.875rem",
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        <div
          style={{
            fontSize: "0.65625rem",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "var(--fg-3)",
          }}
        >
          {t("requirements.statusMeaning")}
        </div>
        {legend.map((l) => (
          <div
            key={l.status}
            className="flex items-center"
            style={{ gap: "0.625rem", fontSize: "0.75rem" }}
          >
            <span
              className={`sev ${l.status}`}
              style={{ width: "7.375rem", flexShrink: 0 }}
            >
              <span className={`dot ${l.status}`} />
              {statusLabel(l.status)}
            </span>
            <span
              className="dim"
              style={{ fontSize: "0.71875rem", lineHeight: 1.5 }}
            >
              {l.hint}
            </span>
          </div>
        ))}
      </div>

      <div
        className="flex"
        style={{
          gap: "0.4375rem",
          fontSize: "0.6875rem",
          color: "var(--fg-3)",
          lineHeight: 1.5,
        }}
      >
        <Info
          size="0.8125rem"
          style={{ flexShrink: 0, marginTop: "0.125rem" }}
        />
        <span>
          {t("requirements.macrosNotePrefix")}
          <span className="mono">\req</span>
          {t("requirements.macrosNoteMiddle")}
          <span className="mono">\reqref</span>
          {t("requirements.macrosNoteSuffix")}
          <span className="mono">common/preamble.tex</span>
          {t("requirements.macrosNoteAfterPreamble")}
          <span className="mono">\reqref{"{R-01,R-02}"}</span>.
        </span>
      </div>
    </div>
  );
};

export const RequirementsView = () => {
  const { t } = useTranslation("workspace");
  const { projectId = "" } = useParams<{ projectId: string }>();
  const { data, isLoading, isError, error } = useRequirements(projectId);
  const items = data?.items ?? [];

  return (
    <div
      style={{
        padding: "1.5rem 2rem",
        overflowY: "auto",
        flex: 1,
        minHeight: 0,
      }}
    >
      <PageHead
        icon={ListChecks}
        title={t("requirements.title")}
        sub={t("requirements.subtitle")}
      />

      <HowItWorks />

      {data && (
        <RequirementsFormatEditor
          projectId={projectId}
          format={data.format}
          overridden={data.format_overridden}
        />
      )}

      {isLoading ? (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            padding: "2.5rem",
          }}
        >
          <Spinner />
        </div>
      ) : isError ? (
        <div
          className="card"
          style={{
            marginTop: "1rem",
            padding: "1.125rem",
            color: "var(--c-err)",
            fontSize: "0.78125rem",
          }}
        >
          {t("requirements.loadError", {
            error:
              error instanceof Error ? error.message : t("common.unknownError"),
          })}
        </div>
      ) : items.length === 0 ? (
        <div
          className="card"
          style={{ marginTop: "1rem", padding: "1.5rem", textAlign: "center" }}
        >
          <Inbox
            size="1.375rem"
            style={{ color: "var(--fg-3)", marginBottom: "0.5rem" }}
          />
          <div
            style={{
              fontSize: "0.8125rem",
              fontWeight: 600,
              color: "var(--fg-0)",
              marginBottom: "0.25rem",
            }}
          >
            {t("requirements.emptyTitle")}
          </div>
          <p
            className="dim"
            style={{
              margin: "0 auto",
              fontSize: "0.75rem",
              lineHeight: 1.55,
              maxWidth: "28.75rem",
            }}
          >
            {t("requirements.emptyHint")}
          </p>
        </div>
      ) : (
        <div className="card" style={{ marginTop: "1rem", overflow: "hidden" }}>
          <div
            className="flex items-center"
            style={{
              padding: "0.625rem 1rem",
              borderBottom: "1px solid var(--border)",
              background: "var(--bg-2)",
              gap: "0.75rem",
              fontSize: "0.65625rem",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--fg-3)",
            }}
          >
            <span style={{ width: "4rem" }}>{t("requirements.colId")}</span>
            <span className="flex-1">{t("requirements.colDescription")}</span>
            <span style={{ width: "5rem" }}>{t("requirements.colSource")}</span>
            <span style={{ width: "13.75rem" }}>
              {t("requirements.colReferencedIn")}
            </span>
            <span style={{ width: "6.875rem", textAlign: "right" }}>
              {t("requirements.colStatus")}
            </span>
          </div>
          {items.map((r, i) => (
            <div
              key={r.id}
              className="flex items-center"
              style={{
                padding: "0.625rem 1rem",
                borderBottom:
                  i < items.length - 1 ? "1px solid var(--border)" : 0,
                gap: "0.75rem",
                fontSize: "0.75rem",
              }}
            >
              <span
                className="mono"
                style={{
                  width: "4rem",
                  color: "var(--accent)",
                  fontWeight: 600,
                }}
              >
                {r.id}
              </span>
              <span
                className="flex-1 truncate"
                style={{ color: "var(--fg-1)" }}
                title={r.title}
              >
                {r.title}
              </span>
              <span
                className="chip mono"
                style={{
                  width: "5rem",
                  justifyContent: "center",
                  textTransform: "uppercase",
                }}
              >
                {r.source || "—"}
              </span>
              <span
                style={{
                  width: "13.75rem",
                  display: "flex",
                  gap: "0.25rem",
                  flexWrap: "wrap",
                }}
              >
                {r.referenced_in.length === 0 ? (
                  <span className="dim" style={{ fontSize: "0.6875rem" }}>
                    —
                  </span>
                ) : (
                  r.referenced_in.map((d) => (
                    <span
                      key={d}
                      className="chip mono"
                      style={{
                        fontSize: "0.625rem",
                        textTransform: "uppercase",
                      }}
                    >
                      {d}
                    </span>
                  ))
                )}
              </span>
              <span
                className={`sev ${r.status}`}
                style={{ width: "6.875rem", justifyContent: "flex-end" }}
              >
                <span className={`dot ${r.status}`} />
                {statusLabel(r.status)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

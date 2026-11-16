import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  OutcomeInput,
  OutcomeParticipant,
  PackOutcome,
} from "@entities/pack-studio";
import { Badge } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell } from "./SectionShell";
import { PickItem, Reason, Stats } from "./parts";
import { onArrowNav } from "./helpers";
import { useExplain } from "./useExplain";

/** Шаг маршрута точки, в котором нет человека: сервер прислал персону с пустым именем. */
type EmptyStep = {
  pointId: string;
  pointName: string;
  step: number;
  personas: string[];
};

const emptySteps = (outcome: PackOutcome, lang: string): EmptyStep[] => {
  const out: EmptyStep[] = [];
  const absent = new Set(
    outcome.participants.filter((p) => !p.present).map((p) => p.persona),
  );
  for (const point of outcome.points) {
    point.route.steps.forEach((step, index) => {
      const gone = step.filter(
        (person) => person.name.trim() === "" || absent.has(person.persona),
      );
      if (gone.length > 0) {
        out.push({
          pointId: point.id,
          pointName: pickLocalized(point.name, lang, point.id),
          step: index + 1,
          personas: gone.map((person) => person.persona),
        });
      }
    });
  }
  return out;
};

const AUTHOR = /^author(\d+)$/;

const ParticipantCard = ({
  person,
  outcome,
  inputs,
}: {
  person: OutcomeParticipant;
  outcome: PackOutcome;
  inputs: readonly OutcomeInput[] | undefined;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const num = AUTHOR.exec(person.persona)?.[1];
  const role = num
    ? t("participants.authorN", { n: num })
    : t(`participants.role.${person.role}`);
  // Обязательность берётся у поля проекта с тем же id (`supervisor`, `co_supervisor`): так
  // версия объявляет, когда руководителя нужно указать. У авторов своего поля нет.
  const field = outcome.meta.find((m) => m.id === person.role);
  const input = inputs?.find((i) => i.id === person.role);
  const reasons = person.present ? [] : explain.reasons(person.why);
  const value = outcome.inputs[person.role];
  return (
    <PickItem
      el={{ section: "participants", id: person.persona }}
      muted={!person.present}
      testId={`outcome-participant-${person.persona}`}
      title={role}
      badges={
        <>
          {person.org && (
            <Badge variant={person.org === "company" ? "info" : "default"}>
              {t(`participants.org.${person.org}`)}
            </Badge>
          )}
          {field ? (
            <Badge
              variant={field.required_at === "create" ? "accent" : "subtle"}
            >
              {t(`participants.required.${field.required_at}`)}
            </Badge>
          ) : (
            <Badge variant="subtle">{t("participants.always")}</Badge>
          )}
        </>
      }
    >
      {person.present ? (
        <span className="po-person-name">{person.name}</span>
      ) : (
        <Reason
          prefix={t("participants.absent")}
          texts={
            reasons.length > 0
              ? reasons
              : input && value !== undefined
                ? [
                    t("participants.byInput", {
                      input: pickLocalized(
                        input.label ?? undefined,
                        i18n.language,
                        explain.subject(input.id),
                      ),
                      value: explain.value(input.id, value),
                    }),
                  ]
                : [t("participants.absentWhy")]
          }
        />
      )}
      <span className="po-mono po-note">{person.persona}</span>
    </PickItem>
  );
};

const ParticipantsBody = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale, inputs } = useOutcomeModel();
  const people = outcome.participants;
  const authors = people.filter((p) => p.role === "author");
  const others = people.filter((p) => p.role !== "author");
  const steps = emptySteps(outcome, i18n.language);
  const list = inputs.data?.inputs;
  return (
    <div
      className="po-sec"
      data-stale={stale ? "true" : undefined}
      data-testid="outcome-participants"
      onKeyDown={onArrowNav}
    >
      <Stats
        testId="outcome-participants-stats"
        items={[
          {
            id: "authors",
            label: t("participants.stats.authors"),
            value: authors.length,
          },
          {
            id: "supervisors",
            label: t("participants.stats.supervisors"),
            value: others.filter((p) => p.present).length,
          },
          {
            id: "absent",
            label: t("participants.stats.absent"),
            value: people.filter((p) => !p.present).length,
          },
        ]}
      />
      {steps.length > 0 && (
        <div
          className="po-warn"
          role="group"
          aria-label={t("participants.warnTitle")}
          data-testid="outcome-participants-warning"
        >
          <TriangleAlert
            size="1rem"
            aria-hidden="true"
            className="po-warn-icon"
          />
          <div>
            <p className="po-warn-title">{t("participants.warnTitle")}</p>
            <ul className="po-warn-list">
              {steps.map((s) => (
                <li key={`${s.pointId}:${String(s.step)}`}>
                  {t("participants.warnStep", {
                    point: s.pointName,
                    step: s.step,
                    who: s.personas.join(", "),
                  })}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {people.length === 0 ? (
        <p className="po-note" data-testid="outcome-participants-empty">
          {t("participants.empty")}
        </p>
      ) : (
        <ul className="po-grid" data-testid="outcome-participants-list">
          {[...authors, ...others].map((p) => (
            <ParticipantCard
              key={p.persona}
              person={p}
              outcome={outcome}
              inputs={list}
            />
          ))}
        </ul>
      )}
    </div>
  );
};

/** Кто ожидается в проекте при этой комбинации: авторы и руководители, в том числе «нет». */
export const ParticipantsSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="participants"
      title={t("sections.participants")}
      count={
        sum
          ? t("sections.count.participants", {
              present: sum.participantsPresent,
              total: sum.participantsTotal,
            })
          : null
      }
      loading={!shown}
    >
      {shown && <ParticipantsBody outcome={shown} />}
    </SectionShell>
  );
};

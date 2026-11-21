import { Check, Clock } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Badge, Button, Section } from "@shared/ui";
import { Switch } from "@shared/ui/Switch";
import type { SetupState, SetupStatus } from "../lib/setup";
import "./packStudioAdmin.css";

const STATUS_VARIANT = {
  ready: "success",
  off: "warning",
  needAccess: "warning",
} as const satisfies Record<SetupStatus, "success" | "warning">;

const Row = ({
  id,
  done,
  title,
  hint,
  tag,
  children,
}: {
  id: string;
  done: boolean;
  title: string;
  hint: ReactNode;
  tag?: string | undefined;
  children?: ReactNode;
}) => (
  <li className="sp-setup-row" data-testid={`ps-step-${id}`} data-done={done}>
    <span className="sp-setup-mark" data-done={done} aria-hidden="true">
      {done ? <Check size="0.75rem" /> : <Clock size="0.75rem" />}
    </span>
    <div className="sp-setup-text">
      <span className="sp-setup-title">
        {title}
        {tag && <Badge variant="subtle">{tag}</Badge>}
      </span>
      <p className="sp-setup-hint">{hint}</p>
    </div>
    {children && <div className="sp-setup-control">{children}</div>}
  </li>
);

/**
 * Чек-лист «Настройка: N шагов из M» наверху страницы: что включить и что ещё
 * осталось. Значок и слово дублируют друг друга: «сделано» не только цветом.
 */
export const SetupChecklist = ({
  setup,
  enabled,
  locked,
  toggling,
  onToggle,
  accessHint,
  repoHint,
  onGrant,
  onConnect,
}: {
  setup: SetupState;
  enabled: boolean;
  locked: boolean;
  toggling: boolean;
  onToggle: (next: boolean) => void;
  /** Кто сейчас может править шаблоны, готовой фразой. */
  accessHint: string;
  /** Какие репозитории подключены, или «ошибка» вместо списка. */
  repoHint: string;
  onGrant: () => void;
  onConnect: () => void;
}) => {
  const { t } = useTranslation("adminPackStudio");
  const done = (id: string): boolean =>
    setup.steps.find((s) => s.id === id)?.done ?? false;
  const hasRepoStep = setup.steps.some((s) => s.id === "repo");
  return (
    <Section
      testId="ps-setup"
      title={
        setup.done === setup.total
          ? t("setup.titleDone")
          : t("setup.title", { count: setup.done, total: setup.total })
      }
      actions={
        <Badge
          variant={STATUS_VARIANT[setup.status]}
          data-testid="ps-setup-status"
        >
          {t(`setup.status.${setup.status}`)}
        </Badge>
      }
    >
      <ol className="sp-setup">
        <Row
          id="enabled"
          done={done("enabled")}
          title={t("setup.enabled.title")}
          hint={
            locked
              ? t("setup.enabled.locked")
              : enabled
                ? t("setup.enabled.hintOn")
                : t("setup.enabled.hintOff")
          }
        >
          <span className="sp-setup-hint" aria-hidden="true">
            {enabled
              ? t("setup.enabled.switchOn")
              : t("setup.enabled.switchOff")}
          </span>
          <Switch
            checked={enabled}
            disabled={locked || toggling}
            onChange={onToggle}
            label={t("setup.enabled.title")}
            testId="ps-admin-enabled"
          />
        </Row>
        <Row
          id="access"
          done={done("access")}
          title={t("setup.access.title")}
          hint={accessHint}
        >
          {!done("access") && (
            <Button size="sm" variant="secondary" onClick={onGrant}>
              {t("setup.access.action")}
            </Button>
          )}
        </Row>
        {hasRepoStep && (
          <Row
            id="repo"
            done={done("repo")}
            title={t("setup.repo.title")}
            tag={t("setup.optional")}
            hint={repoHint}
          >
            {!done("repo") && (
              <Button size="sm" variant="secondary" onClick={onConnect}>
                {t("setup.repo.action")}
              </Button>
            )}
          </Row>
        )}
      </ol>
    </Section>
  );
};

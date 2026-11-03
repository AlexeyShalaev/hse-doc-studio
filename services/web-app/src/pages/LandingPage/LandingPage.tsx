import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import {
  BookOpen,
  FileCheck,
  FileText,
  GitBranch,
  GraduationCap,
  Laptop,
  LogIn,
  PenLine,
  ServerCog,
  Share2,
  ShieldCheck,
  Sparkles,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { SignInForm } from "@features/sign-in";
import { HELP_BASE } from "@entities/help";
import { LOCAL_STUDIO_PATH } from "@entities/local-studio";
import { useBootstrap, type AuthOptions } from "@entities/session";
import { AuthSwitches } from "@widgets/AuthLayout";
import { useThemeStore } from "@shared/lib";
import { PREFERS_DARK_QUERY, resolveTheme } from "@shared/lib/theme";
import { Button } from "@shared/ui";
import { Modal } from "@shared/ui/Modal";
import { useMatchMedia } from "./useMatchMedia";
import "./landing.css";

/** Окно шире этого показывает форму входа рядом с описанием, уже: кнопка и диалог. */
const WIDE_QUERY = "(min-width: 960px)";

type Feature = { id: string; icon: LucideIcon; shot: string };

// Снимки берутся из справки (/help/media): новых файлов у страницы нет.
const FEATURES: readonly Feature[] = [
  { id: "checks", icon: FileCheck, shot: "runbooks/checks/step-02" },
  { id: "editor", icon: FileText, shot: "runbooks/editor-preview/step-02" },
  { id: "ai", icon: Sparkles, shot: "runbooks/ai-agent/step-05" },
  { id: "collab", icon: Users, shot: "runbooks/review-collaboration/step-01" },
  { id: "git", icon: GitBranch, shot: "runbooks/git-sync/step-01" },
  { id: "sign", icon: PenLine, shot: "runbooks/submit-sign/step-03" },
];

const AUDIENCE: readonly { id: string; icon: LucideIcon }[] = [
  { id: "student", icon: GraduationCap },
  { id: "supervisor", icon: BookOpen },
  { id: "admin", icon: ServerCog },
];

const CLOUD: readonly { id: string; icon: LucideIcon }[] = [
  { id: "team", icon: Users },
  { id: "links", icon: Share2 },
  { id: "build", icon: FileCheck },
  { id: "anywhere", icon: Laptop },
];

/** Регистрация открыта там же, где её откроет форма (иначе ссылка вела бы в тупик). */
const canRegister = (auth: AuthOptions): boolean =>
  auth.password_enabled &&
  (auth.registration_mode === "open" || auth.registration_mode === "domains");

const Shot = ({
  src,
  alt,
  priority,
}: {
  src: string;
  alt: string;
  priority: boolean;
}) => {
  const [broken, setBroken] = useState(false);
  // Нет снимка (справка не собрана): блок остаётся текстом, а не битой картинкой.
  if (broken) return null;
  return (
    <img
      className="lp-shot"
      src={src}
      alt={alt}
      width={1600}
      height={1000}
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      onError={() => {
        setBroken(true);
      }}
    />
  );
};

const Section = ({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead?: string;
  children: ReactNode;
}) => (
  <section className="lp-section" id={id} aria-labelledby={`${id}-title`}>
    <div className="lp-wrap">
      <h2 className="lp-h2" id={`${id}-title`}>
        {title}
      </h2>
      {lead && <p className="lp-section-lead">{lead}</p>}
      {children}
    </div>
  </section>
);

/**
 * Лендинг облачной установки: что это, зачем и как начать, со входом на первом
 * экране. Видит его только не вошедший человек на корне (см. showsLanding).
 * Снимки и ролики берутся из справки, поэтому страница лёгкая.
 */
export const LandingPage = () => {
  const { t } = useTranslation("landing");
  const { data } = useBootstrap();
  const lang = useThemeStore((s) => s.lang);
  const themePref = useThemeStore((s) => s.theme);
  const wide = useMatchMedia(WIDE_QUERY);
  const [loginOpen, setLoginOpen] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);

  const name = data?.landing?.name ?? "HSE Doc Studio";
  const title = t("meta.title", { name });
  useEffect(() => {
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);

  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia(PREFERS_DARK_QUERY).matches;
  const shotTheme =
    resolveTheme(themePref, prefersDark) === "light" ? "light" : "dark";
  const shotUrl = (key: string): string =>
    `${HELP_BASE}/media/${key}.${lang}.${shotTheme}.webp`;

  if (!data) return null;
  const registerOpen = canRegister(data.auth);
  const inviteOnly =
    data.auth.registration_mode === "invite" && data.auth.password_enabled;

  // Рядом с описанием форма уже на экране: кнопка возвращает к ней и ставит фокус. На узком экране форма в диалоге.
  const openLogin = () => {
    if (!wide) {
      setLoginOpen(true);
      return;
    }
    formRef.current?.scrollIntoView({ block: "center" });
    formRef.current?.querySelector<HTMLInputElement>("input")?.focus();
  };

  const helpHref = `${HELP_BASE}/${lang}/`;
  const localGuideHref = `${HELP_BASE}/${lang}/runbooks/local-version/`;

  return (
    <div className="lp" data-testid="landing-page">
      <a className="lp-skip" href="#lp-main">
        {t("skip")}
      </a>
      <header className="lp-header">
        <div className="lp-wrap lp-header-row">
          <Link className="lp-brand" to="/" aria-label={name}>
            <span className="lp-logo" aria-hidden>
              §
            </span>
            <span className="lp-brand-name">{name}</span>
          </Link>
          <nav className="lp-nav" aria-label={t("nav.label")}>
            <a href="#features">{t("nav.features")}</a>
            <a href="#cloud">{t("nav.cloud")}</a>
            <a href="#start">{t("nav.start")}</a>
            <a href="#security">{t("nav.security")}</a>
          </nav>
          <div className="lp-header-actions">
            <AuthSwitches />
            <Button
              size="sm"
              onClick={openLogin}
              data-testid="landing-login-button"
              aria-label={t("login")}
            >
              <LogIn size={14} aria-hidden="true" />
              <span className="lp-btn-label">{t("login")}</span>
            </Button>
          </div>
        </div>
      </header>

      <main id="lp-main">
        <section className="lp-hero" aria-labelledby="lp-hero-title">
          <div className="lp-wrap lp-hero-grid">
            <div className="lp-hero-copy">
              <p className="lp-eyebrow">{t("hero.eyebrow")}</p>
              <h1 className="lp-h1" id="lp-hero-title">
                {t("hero.title")}
              </h1>
              <p className="lp-lead">{t("hero.lead", { name })}</p>
              <div className="lp-cta">
                <Button size="lg" onClick={openLogin}>
                  <LogIn size={15} aria-hidden="true" />
                  {t("login")}
                </Button>
                {registerOpen && (
                  <Button size="lg" variant="secondary" asChild>
                    <Link to="/register" data-testid="landing-register">
                      <UserPlus size={15} aria-hidden="true" />
                      {t("register")}
                    </Link>
                  </Button>
                )}
                <a className="lp-link" href="#features">
                  {t("hero.more")}
                </a>
              </div>
              {inviteOnly && (
                <p className="lp-note" data-testid="landing-invite-only">
                  {t("hero.inviteOnly")}
                </p>
              )}
            </div>
            {wide && (
              <div
                className="lp-login"
                ref={formRef}
                id="login"
                data-testid="landing-login-card"
              >
                <SignInForm heading="h2" autoFocus={false} />
              </div>
            )}
          </div>
        </section>

        <Section id="audience" title={t("audience.title")}>
          <ul className="lp-cards">
            {AUDIENCE.map(({ id, icon: Icon }) => (
              <li className="lp-card" key={id}>
                <Icon size={20} aria-hidden="true" className="lp-card-icon" />
                <h3 className="lp-h3">{t(`audience.${id}.title`)}</h3>
                <p>{t(`audience.${id}.text`)}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section
          id="features"
          title={t("features.title")}
          lead={t("features.lead")}
        >
          <ol className="lp-features">
            {FEATURES.map(({ id, icon: Icon, shot }, index) => (
              <li className="lp-feature" key={id}>
                <div className="lp-feature-copy">
                  <Icon size={20} aria-hidden="true" className="lp-card-icon" />
                  <h3 className="lp-h3">{t(`features.${id}.title`)}</h3>
                  <p>{t(`features.${id}.text`)}</p>
                </div>
                <div className="lp-feature-shot">
                  <Shot
                    src={shotUrl(shot)}
                    alt={t(`features.${id}.alt`)}
                    priority={index === 0}
                  />
                </div>
              </li>
            ))}
          </ol>
        </Section>

        <Section id="cloud" title={t("cloud.title")} lead={t("cloud.lead")}>
          <ul className="lp-cards lp-cards-4">
            {CLOUD.map(({ id, icon: Icon }) => (
              <li className="lp-card" key={id}>
                <Icon size={20} aria-hidden="true" className="lp-card-icon" />
                <h3 className="lp-h3">{t(`cloud.${id}.title`)}</h3>
                <p>{t(`cloud.${id}.text`)}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="start" title={t("start.title")}>
          <ol className="lp-steps">
            <li>
              <h3 className="lp-h3">
                {t(wide ? "start.step1.title" : "start.step1Mobile.title")}
              </h3>
              <p>{t(wide ? "start.step1.text" : "start.step1Mobile.text")}</p>
            </li>
            <li>
              <h3 className="lp-h3">{t("start.step2.title")}</h3>
              <p>{t("start.step2.text")}</p>
            </li>
            <li>
              <h3 className="lp-h3">{t("start.step3.title")}</h3>
              <p>{t("start.step3.text")}</p>
              <p className="lp-links">
                <a href={localGuideHref} data-testid="landing-local-guide">
                  {t("start.step3.guide")}
                </a>
                <Link to={LOCAL_STUDIO_PATH} data-testid="landing-local-page">
                  {t("start.step3.page")}
                </Link>
              </p>
            </li>
          </ol>
          <p className="lp-links">
            <a href={helpHref}>{t("start.help")}</a>
          </p>
        </Section>

        <Section id="security" title={t("security.title")}>
          <ul className="lp-checklist">
            {(["projects", "admin", "tracking", "ai", "login"] as const).map(
              (id) => (
                <li key={id}>
                  <ShieldCheck size={18} aria-hidden="true" />
                  <span>{t(`security.${id}`)}</span>
                </li>
              ),
            )}
          </ul>
        </Section>

        <section className="lp-section lp-final" aria-labelledby="lp-cta-title">
          <div className="lp-wrap lp-final-box">
            <div>
              <h2 className="lp-h2" id="lp-cta-title">
                {t("cta.title")}
              </h2>
              <p className="lp-section-lead">{t("cta.text")}</p>
            </div>
            <div className="lp-cta">
              <Button size="lg" onClick={openLogin}>
                <LogIn size={15} aria-hidden="true" />
                {t("login")}
              </Button>
              {registerOpen && (
                <Button size="lg" variant="secondary" asChild>
                  <Link to="/register">
                    <UserPlus size={15} aria-hidden="true" />
                    {t("register")}
                  </Link>
                </Button>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap lp-footer-row">
          <span>{t("footer.poweredBy")}</span>
          <nav className="lp-footer-links" aria-label={name}>
            <a href={helpHref}>{t("footer.help")}</a>
            <a href={localGuideHref}>{t("footer.local")}</a>
            <Link to="/login">{t("footer.login")}</Link>
          </nav>
        </div>
      </footer>

      <Modal
        isOpen={loginOpen && !wide}
        onClose={() => {
          setLoginOpen(false);
        }}
        title={t("hero.formTitle", { name })}
        width={420}
      >
        <div className="lp-dialog-form">
          <SignInForm heading={false} />
        </div>
      </Modal>
    </div>
  );
};

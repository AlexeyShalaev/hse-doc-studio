import {
  BadgeCheck,
  FolderGit2,
  Folder,
  Plus,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { ActionMenu, Badge, Button } from "@shared/ui";
import type { ConnectKind } from "../lib/connectKinds";
import "./space-list.css";

const ICON: Record<ConnectKind, LucideIcon> = {
  official: BadgeCheck,
  git: FolderGit2,
  folder: Folder,
};

export type ConnectPathsProps = {
  kinds: readonly ConnectKind[];
  onConnect: (kind: ConnectKind) => void;
};

/**
 * Пустое состояние: пути подключения равными карточками, с короткими
 * объяснениями. Самый простой выделен рамкой и подписью «Проще всего», и только
 * у него залитая кнопка; нет официальных шаблонов, залита кнопка «Свой репозиторий».
 */
export const ConnectPaths = ({ kinds, onConnect }: ConnectPathsProps) => {
  const { t } = useTranslation("packStudio");
  const first = kinds[0];
  return (
    <div className="sp-paths" data-count={kinds.length} data-testid="ws-paths">
      {kinds.map((kind) => {
        const Icon = ICON[kind];
        const recommended = kind === "official";
        return (
          <section
            key={kind}
            className="sp-path"
            data-recommended={recommended ? "true" : undefined}
            data-testid={`ws-path-${kind}`}
          >
            <span className="sp-path-ico" aria-hidden="true">
              <Icon size="1.25rem" />
            </span>
            {recommended && <Badge variant="accent">{t("connect.best")}</Badge>}
            <h2 className="sp-path-title">{t(`connect.${kind}.title`)}</h2>
            <p className="sp-path-text">{t(`connect.${kind}.text`)}</p>
            <span className="sp-grow" />
            <Button
              variant={kind === first ? "primary" : "secondary"}
              onClick={() => {
                onConnect(kind);
              }}
              data-testid={`ws-connect-${kind}`}
            >
              {t(`connect.${kind}.action`)}
            </Button>
          </section>
        );
      })}
    </div>
  );
};

export type ConnectButtonProps = ConnectPathsProps & {
  /** Главная кнопка экрана: залита, только если «Продолжить» нет. */
  primary: boolean;
};

/**
 * «Подключить пространство» в шапке: меню путей, а когда путь один, сразу он.
 * Три клика до подключения репозитория: эта кнопка, «Свой репозиторий», «Подключить».
 */
export const ConnectButton = ({
  kinds,
  onConnect,
  primary,
}: ConnectButtonProps) => {
  const { t } = useTranslation("packStudio");
  const label = t("workspaces.connect");
  const button = (
    <Button
      size="lg"
      variant={primary ? "primary" : "secondary"}
      className="sp-connect-btn"
      data-testid="ws-connect"
      onClick={
        kinds.length === 1 && kinds[0]
          ? () => {
              if (kinds[0]) onConnect(kinds[0]);
            }
          : undefined
      }
    >
      <Plus size="0.875rem" aria-hidden="true" />
      {label}
    </Button>
  );
  if (kinds.length <= 1) return button;
  return (
    <ActionMenu
      label={label}
      trigger={button}
      align="end"
      items={kinds.map((kind) => {
        const Icon = ICON[kind];
        return {
          id: kind,
          label: t(`connect.${kind}.title`),
          icon: <Icon size="0.875rem" />,
          testId: `ws-connect-menu-${kind}`,
          onSelect: () => {
            onConnect(kind);
          },
        };
      })}
    />
  );
};

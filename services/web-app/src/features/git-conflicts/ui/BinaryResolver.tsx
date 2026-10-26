import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, FileQuestion, FileX, ImageOff } from "lucide-react";
import {
  useConflictBlobUrl,
  type ConflictFile,
  type ConflictFileSide,
  type FileResolution,
} from "@entities/git-sync";
import { CopyField } from "@shared/ui/CopyField";
import { Spinner } from "@shared/ui/Spinner";
import { formatWhen } from "../lib/format";
import type { BinaryDetail } from "../model/conflictModel";
import { SideFacts } from "./SideFacts";

export type BinaryResolverProps = {
  projectId: string;
  file: ConflictFile;
  /** Подробности с сервера; без них берём сведения из самого файла в списке. */
  detail: BinaryDetail | undefined;
  resolution: FileResolution | null | undefined;
  theirsAuthor: string | null;
  onChoose: (choice: string) => void;
};

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|svg|avif)$/i;
// Тяжёлые картинки не тянем: предпросмотр нужен, чтобы узнать, а не чтобы читать.
const PREVIEW_LIMIT_BYTES = 8 * 1024 * 1024;

const isImagePath = (path: string): boolean => IMAGE_EXT.test(path);

const extensionOf = (path: string): string => {
  const match = /\.([A-Za-z0-9]{1,6})$/.exec(path);
  return match?.[1]?.toUpperCase() ?? "";
};

type PreviewProps = {
  projectId: string;
  path: string;
  side: "ours" | "theirs";
  info: ConflictFileSide;
  alt: string;
};

const PreviewNote = ({
  icon,
  text,
  busy = false,
}: {
  icon: React.ReactNode;
  text: string;
  busy?: boolean;
}) => (
  <div
    className="file-preview-note"
    role={busy ? "status" : undefined}
    aria-busy={busy || undefined}
  >
    {icon}
    <span>{text}</span>
  </div>
);

/** Картинка стороны или короткое пояснение, почему её не видно. */
const FilePreview = ({ projectId, path, side, info, alt }: PreviewProps) => {
  const { t } = useTranslation("gitConflicts");
  const [broken, setBroken] = useState(false);
  const exists = info.exists;
  const image = exists && isImagePath(path);
  const tooBig = image && info.size != null && info.size > PREVIEW_LIMIT_BYTES;
  const { url, isLoading, isError } = useConflictBlobUrl(
    projectId,
    image && !tooBig ? path : null,
    side,
  );

  const body = ((): React.ReactNode => {
    if (!exists) {
      return (
        <PreviewNote
          icon={<FileX size={22} aria-hidden="true" />}
          text={t("binary.missing")}
        />
      );
    }
    if (!image) {
      const ext = extensionOf(path);
      return (
        <PreviewNote
          icon={<FileQuestion size={22} aria-hidden="true" />}
          text={
            ext ? `${ext}. ${t("binary.noPreview")}` : t("binary.noPreview")
          }
        />
      );
    }
    if (tooBig) {
      return (
        <PreviewNote
          icon={<ImageOff size={22} aria-hidden="true" />}
          text={t("binary.tooBig")}
        />
      );
    }
    if (isLoading) {
      return (
        <PreviewNote
          busy
          icon={<Spinner size="sm" />}
          text={t("binary.loading")}
        />
      );
    }
    if (isError || broken || !url) {
      return (
        <PreviewNote
          icon={<ImageOff size={22} aria-hidden="true" />}
          text={t("binary.error")}
        />
      );
    }
    return (
      <img
        src={url}
        alt={alt}
        onError={() => {
          setBroken(true);
        }}
      />
    );
  })();

  return <div className="file-preview">{body}</div>;
};

type TileProps = {
  projectId: string;
  file: ConflictFile;
  side: "ours" | "theirs";
  info: ConflictFileSide;
  title: string;
  previewAlt: string;
  isNewer: boolean;
  checked: boolean;
  disabled: boolean;
  groupName: string;
  onChoose: () => void;
};

const Tile = ({
  projectId,
  file,
  side,
  info,
  title,
  previewAlt,
  isNewer,
  checked,
  disabled,
  groupName,
  onChoose,
}: TileProps) => {
  const { t } = useTranslation("gitConflicts");
  return (
    <label
      className="card file-tile"
      data-checked={checked ? "true" : undefined}
      data-disabled={disabled ? "true" : undefined}
    >
      <span className="file-tile-head">
        <input
          type="radio"
          name={groupName}
          checked={checked}
          disabled={disabled}
          aria-label={title}
          onChange={onChoose}
        />
        <span className="truncate" title={title}>
          {title}
        </span>
        {isNewer && <span className="chip accent">{t("binary.newer")}</span>}
        {checked && (
          <Check size={13} aria-hidden="true" style={{ marginLeft: "auto" }} />
        )}
      </span>
      <FilePreview
        projectId={projectId}
        path={file.path}
        side={side}
        info={info}
        alt={previewAlt}
      />
      <span style={{ fontSize: 11.5 }}>
        <SideFacts side={info} />
      </span>
    </label>
  );
};

/**
 * Файл, который нельзя слить по частям (картинка, документ Office): две версии
 * рядом с предпросмотром и выбор одной. Если сервер умеет оставить более новую,
 * это третий вариант, и рядом называется имя, под которым сохранится вторая.
 */
export const BinaryResolver = ({
  projectId,
  file,
  detail,
  resolution,
  theirsAuthor,
  onChoose,
}: BinaryResolverProps) => {
  const { t } = useTranslation("gitConflicts");
  const groupId = useId();
  const current = resolution?.kind === "file" ? resolution.choice : null;
  const ours = detail?.ours ?? file.sides.ours;
  const theirs = detail?.theirs ?? file.sides.theirs;
  const newer = detail?.newer ?? null;
  const copyPath = detail?.copy_path ?? file.copy_path ?? null;
  const canNewest = file.allowed.includes("newest");
  const theirsTitle = theirsAuthor
    ? t("hunk.theirs", { author: theirsAuthor })
    : t("binary.theirs");

  const newerSide = newer === "theirs" ? theirs : ours;
  const newerAuthor =
    (newer === "theirs" ? theirsAuthor : null) ?? newerSide.author ?? null;
  const newestId = `${groupId}-newest`;

  const isAllowed = (choice: string): boolean =>
    file.allowed.length === 0 || file.allowed.includes(choice);

  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      <p className="dim" style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>
        {t("binary.explain")}
      </p>
      <div
        role="radiogroup"
        aria-label={t("file.groupLabel")}
        className="flex flex-col"
        style={{ gap: 8 }}
      >
        <div className="file-tiles">
          <Tile
            projectId={projectId}
            file={file}
            side="ours"
            info={ours}
            title={t("binary.mine")}
            previewAlt={t("binary.previewMine")}
            isNewer={newer === "ours"}
            checked={current === "mine"}
            disabled={!isAllowed("mine")}
            groupName={groupId}
            onChoose={() => {
              onChoose("mine");
            }}
          />
          <Tile
            projectId={projectId}
            file={file}
            side="theirs"
            info={theirs}
            title={theirsTitle}
            previewAlt={t("binary.previewTheirs")}
            isNewer={newer === "theirs"}
            checked={current === "theirs"}
            disabled={!isAllowed("theirs")}
            groupName={groupId}
            onChoose={() => {
              onChoose("theirs");
            }}
          />
        </div>

        {canNewest && (
          <label
            htmlFor={newestId}
            className="card whole-choice"
            data-checked={current === "newest" ? "true" : undefined}
          >
            <input
              id={newestId}
              type="radio"
              name={groupId}
              checked={current === "newest"}
              onChange={() => {
                onChoose("newest");
              }}
            />
            <span className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {t("file.choice.newest")}
                {file.default_resolution === "newest" && (
                  <span
                    className="chip accent"
                    style={{ marginLeft: 8, fontFamily: "var(--font-sans)" }}
                  >
                    {t("file.recommended")}
                  </span>
                )}
              </span>
              <span className="dim" style={{ fontSize: 11.5 }}>
                {newer
                  ? t("binary.newestKeeps", {
                      author: newerAuthor ?? t("side.unknown"),
                      when: formatWhen(newerSide.at) || "—",
                    })
                  : t("binary.newestKeepsPlain")}
              </span>
            </span>
          </label>
        )}
      </div>

      {canNewest && copyPath && (
        <div className="flex flex-col" style={{ gap: 6 }}>
          <span className="dim" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
            {t("binary.copySaved")}
          </span>
          <CopyField value={copyPath} label={t("binary.copyLabel")} />
        </div>
      )}
    </div>
  );
};

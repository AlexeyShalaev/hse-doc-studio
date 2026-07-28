import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Asterisk,
  Bold,
  BookMarked,
  ChevronLeft,
  ChevronRight,
  Code,
  ImagePlus,
  Italic,
  List,
  ListOrdered,
  ListTree,
  Maximize2,
  MessageSquareText,
  Minimize2,
  Minus,
  Plus,
  Quote,
  Redo2,
  SeparatorHorizontal,
  Sigma,
  SquareSigma,
  Table2,
  Underline,
  Undo2,
  type LucideIcon,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import {
  VISUAL_ZOOM_MAX,
  VISUAL_ZOOM_MIN,
  useEditorPrefsStore,
} from "@shared/lib";
import { Select } from "@shared/ui/Select";
import { Tooltip } from "@shared/ui/Tooltip";
import type {
  CodeEditorController,
  EditorCommandId,
  EditorFormatState,
} from "@shared/ui/CodeEditor";

export type FormatToolbarProps = {
  /** Imperative editor handle (populated by CodeEditor once mounted). */
  controller: { current: CodeEditorController | null };
  /** Formatting at the caret — drives active states and the fields counter. */
  formatState: EditorFormatState | null;
  readOnly?: boolean;
  focusMode: boolean;
  onToggleFocusMode: () => void;
};

type InsertItem = {
  id: EditorCommandId;
  label: string;
  hint: string;
  icon: LucideIcon;
};

/**
 * Word-processor formatting bar for the visual mode. Editing actions stay in
 * predictable groups, the whole bar scrolls horizontally in narrow split
 * views, and presentation controls remain available for read-only documents.
 */
export const FormatToolbar = ({
  controller,
  formatState,
  readOnly = false,
  focusMode,
  onToggleFocusMode,
}: FormatToolbarProps) => {
  const { t } = useTranslation("sourceEdit");
  const showComments = useEditorPrefsStore((s) => s.showComments);
  const toggleShowComments = useEditorPrefsStore((s) => s.toggleShowComments);
  const showOutline = useEditorPrefsStore((s) => s.showOutline);
  const toggleShowOutline = useEditorPrefsStore((s) => s.toggleShowOutline);
  const visualZoom = useEditorPrefsStore((s) => s.visualZoom);
  const zoomVisualIn = useEditorPrefsStore((s) => s.zoomVisualIn);
  const zoomVisualOut = useEditorPrefsStore((s) => s.zoomVisualOut);
  const resetVisualZoom = useEditorPrefsStore((s) => s.resetVisualZoom);

  const exec = (id: EditorCommandId): void => {
    controller.current?.exec(id);
    controller.current?.focus();
  };

  const execHistory = (direction: "undo" | "redo"): void => {
    controller.current?.[direction]();
    controller.current?.focus();
  };

  // Keep the editor focused (and its selection alive) while clicking buttons.
  const keepFocus = (event: React.MouseEvent): void => {
    event.preventDefault();
  };

  // The formatting row scrolls horizontally and therefore clips normal CSS
  // pseudo-element tooltips. Portal-backed tooltips escape that scrollport;
  // the document canvas has an empty top margin for the downward placement.
  const toolbarTooltip = (
    content: string,
    trigger: React.ReactElement,
  ): React.ReactElement => (
    <Tooltip
      content={content}
      side="bottom"
      delayDuration={250}
      collisionPadding={8}
      className="visual-format-tooltip"
    >
      {trigger}
    </Tooltip>
  );

  const iconButton = (
    id: EditorCommandId,
    title: string,
    icon: React.ReactNode,
    active = false,
  ) =>
    toolbarTooltip(
      title,
      <button
        type="button"
        className={clsx("icon-btn sm visual-format-button", active && "active")}
        aria-label={title}
        aria-pressed={active}
        onMouseDown={keepFocus}
        onClick={() => {
          exec(id);
        }}
      >
        {icon}
      </button>,
    );

  const divider = <span className="visual-format-divider" aria-hidden="true" />;
  const fieldsRemaining = formatState?.fieldsRemaining ?? 0;
  const insertItems: InsertItem[] = [
    {
      id: "insert:figure",
      label: t("insert.figure"),
      hint: t("insert.figureHint"),
      icon: ImagePlus,
    },
    {
      id: "insert:table",
      label: t("insert.table"),
      hint: t("insert.tableHint"),
      icon: Table2,
    },
    {
      id: "insert:citation",
      label: t("insert.citation"),
      hint: t("insert.citationHint"),
      icon: BookMarked,
    },
    {
      id: "insert:footnote",
      label: t("insert.footnote"),
      hint: t("insert.footnoteHint"),
      icon: Asterisk,
    },
    {
      id: "insert:quote",
      label: t("insert.quote"),
      hint: t("insert.quoteHint"),
      icon: Quote,
    },
    {
      id: "insert:pageBreak",
      label: t("insert.pageBreak"),
      hint: t("insert.pageBreakHint"),
      icon: SeparatorHorizontal,
    },
  ];

  return (
    <div
      className="visual-format-toolbar"
      role="toolbar"
      aria-label={t("format.toolbarLabel")}
    >
      <div className="visual-format-toolbar-track">
        <div className="visual-format-group">
          {toolbarTooltip(
            t("outline.toggle"),
            <button
              type="button"
              className={clsx(
                "icon-btn sm visual-format-button",
                showOutline && "active",
              )}
              aria-label={t("outline.toggle")}
              aria-pressed={showOutline}
              onClick={toggleShowOutline}
            >
              <ListTree size={15} />
            </button>,
          )}
          {!readOnly && (
            <>
              {toolbarTooltip(
                t("format.undo"),
                <button
                  type="button"
                  className="icon-btn sm visual-format-button"
                  aria-label={t("format.undo")}
                  onMouseDown={keepFocus}
                  onClick={() => {
                    execHistory("undo");
                  }}
                >
                  <Undo2 size={15} />
                </button>,
              )}
              {toolbarTooltip(
                t("format.redo"),
                <button
                  type="button"
                  className="icon-btn sm visual-format-button"
                  aria-label={t("format.redo")}
                  onMouseDown={keepFocus}
                  onClick={() => {
                    execHistory("redo");
                  }}
                >
                  <Redo2 size={15} />
                </button>,
              )}
            </>
          )}
        </div>

        {!readOnly && (
          <>
            {divider}
            <div className="visual-heading-select">
              <Select
                value={formatState?.heading ?? "none"}
                options={[
                  { value: "none", label: t("format.headingNone") },
                  { value: "chapter", label: t("format.chapter") },
                  { value: "section", label: t("format.section") },
                  { value: "subsection", label: t("format.subsection") },
                  {
                    value: "subsubsection",
                    label: t("format.subsubsection"),
                  },
                ]}
                placeholder={t("format.headingLevel")}
                onValueChange={(value) => {
                  exec(
                    `heading:${value === "none" ? "none" : value}` as EditorCommandId,
                  );
                }}
                onCloseAutoFocus={(event) => {
                  event.preventDefault();
                  controller.current?.focus();
                }}
                className="visual-heading-select-trigger"
              />
            </div>

            {divider}
            <div className="visual-format-group">
              {iconButton(
                "bold",
                t("format.bold"),
                <Bold size={15} />,
                formatState?.bold,
              )}
              {iconButton(
                "italic",
                t("format.italic"),
                <Italic size={15} />,
                formatState?.italic,
              )}
              {iconButton(
                "underline",
                t("format.underline"),
                <Underline size={15} />,
                formatState?.underline,
              )}
              {iconButton(
                "monospace",
                t("format.monospace"),
                <Code size={15} />,
                formatState?.monospace,
              )}
            </div>

            {divider}
            <div className="visual-format-group">
              {iconButton(
                "bulletList",
                t("format.bulletList"),
                <List size={15} />,
                formatState?.list === "itemize",
              )}
              {iconButton(
                "numberedList",
                t("format.numberedList"),
                <ListOrdered size={15} />,
                formatState?.list === "enumerate",
              )}
              {iconButton(
                "inlineMath",
                t("format.inlineMath"),
                <Sigma size={15} />,
              )}
              {iconButton(
                "displayMath",
                t("format.displayMath"),
                <SquareSigma size={15} />,
              )}
            </div>

            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  className="btn sm visual-insert-trigger"
                  aria-label={t("insert.open")}
                  title={t("insert.slashHint")}
                >
                  <Plus size={14} />
                  <span>{t("insert.open")}</span>
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  className="visual-insert-menu"
                  sideOffset={7}
                  align="start"
                  collisionPadding={10}
                  onCloseAutoFocus={(event) => {
                    event.preventDefault();
                    controller.current?.focus();
                  }}
                >
                  <div className="visual-insert-menu-head">
                    <span>{t("insert.title")}</span>
                    <span className="kbd">/</span>
                  </div>
                  {insertItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <DropdownMenu.Item
                        key={item.id}
                        className="visual-insert-item"
                        onSelect={() => {
                          exec(item.id);
                        }}
                      >
                        <span className="visual-insert-item-icon">
                          <Icon size={15} />
                        </span>
                        <span className="visual-insert-item-copy">
                          <span>{item.label}</span>
                          <span>{item.hint}</span>
                        </span>
                      </DropdownMenu.Item>
                    );
                  })}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </>
        )}

        <span className="visual-format-spacer" />

        {!readOnly && fieldsRemaining > 0 && (
          <span className="visual-fields-control">
            {toolbarTooltip(
              t("format.prevField"),
              <button
                type="button"
                className="icon-btn sm visual-format-button"
                aria-label={t("format.prevField")}
                onMouseDown={keepFocus}
                onClick={() => {
                  exec("prevField");
                }}
              >
                <ChevronLeft size={14} />
              </button>,
            )}
            {toolbarTooltip(
              t("format.fieldsHint"),
              <button
                type="button"
                className="visual-fields-badge"
                aria-label={t("format.fieldsHint")}
                onMouseDown={keepFocus}
                onClick={() => {
                  exec("nextField");
                }}
              >
                {t("format.fieldsRemaining", { count: fieldsRemaining })}
              </button>,
            )}
            {toolbarTooltip(
              t("format.nextField"),
              <button
                type="button"
                className="icon-btn sm visual-format-button"
                aria-label={t("format.nextField")}
                onMouseDown={keepFocus}
                onClick={() => {
                  exec("nextField");
                }}
              >
                <ChevronRight size={14} />
              </button>,
            )}
          </span>
        )}

        <div className="visual-zoom-control" aria-label={t("zoom.label")}>
          {toolbarTooltip(
            t("zoom.out"),
            <button
              type="button"
              className="icon-btn sm visual-format-button"
              aria-label={t("zoom.out")}
              disabled={visualZoom <= VISUAL_ZOOM_MIN}
              onClick={zoomVisualOut}
            >
              <Minus size={14} />
            </button>,
          )}
          {toolbarTooltip(
            t("zoom.reset"),
            <button
              type="button"
              className="visual-zoom-value"
              aria-label={t("zoom.reset")}
              onClick={resetVisualZoom}
            >
              {visualZoom}%
            </button>,
          )}
          {toolbarTooltip(
            t("zoom.in"),
            <button
              type="button"
              className="icon-btn sm visual-format-button"
              aria-label={t("zoom.in")}
              disabled={visualZoom >= VISUAL_ZOOM_MAX}
              onClick={zoomVisualIn}
            >
              <Plus size={14} />
            </button>,
          )}
        </div>

        {toolbarTooltip(
          t("format.comments"),
          <button
            type="button"
            className={clsx(
              "icon-btn sm visual-format-button",
              showComments && "active",
            )}
            aria-label={t("format.comments")}
            aria-pressed={showComments}
            onClick={toggleShowComments}
          >
            <MessageSquareText size={15} />
          </button>,
        )}
        {toolbarTooltip(
          focusMode ? t("focus.exit") : t("focus.enter"),
          <button
            type="button"
            className={clsx(
              "icon-btn sm visual-format-button visual-focus-button",
              focusMode && "active",
            )}
            aria-label={focusMode ? t("focus.exit") : t("focus.enter")}
            aria-pressed={focusMode}
            onClick={onToggleFocusMode}
          >
            {focusMode ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>,
        )}
      </div>
    </div>
  );
};

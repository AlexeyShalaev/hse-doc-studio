import { useRef, type ReactNode } from "react";
import { Button, type ButtonProps } from "@shared/ui";

export type FilePickProps = {
  accept: string;
  disabled?: boolean;
  variant?: ButtonProps["variant"];
  testId: string;
  children: ReactNode;
  onFile: (file: File) => void;
};

/** Кнопка выбора файла: скрытое поле, тот же файл можно выбрать повторно. */
export const FilePick = ({
  accept,
  disabled = false,
  variant = "secondary",
  testId,
  children,
  onFile,
}: FilePickProps) => {
  const input = useRef<HTMLInputElement | null>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        data-testid={`${testId}-input`}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
      <Button
        type="button"
        size="sm"
        variant={variant}
        disabled={disabled}
        onClick={() => input.current?.click()}
        data-testid={testId}
      >
        {children}
      </Button>
    </>
  );
};

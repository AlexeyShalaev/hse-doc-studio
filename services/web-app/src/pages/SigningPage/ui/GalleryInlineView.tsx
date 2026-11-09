import { useSigningInline, type InlineUiState } from "@features/signing-inline";
import { SigningView, type SigningViewProps } from "./SigningView";

/**
 * Страница подписанта для галереи с настоящими блоками подписи; `initial`: что человек
 * уже выбрал или раскрыл (рисует подпись, открыл форму ключа).
 */
export const GalleryInlineView = ({
  initial,
  ...props
}: SigningViewProps & { initial?: Partial<InlineUiState> }) => {
  const extension = useSigningInline(initial);
  return <SigningView {...props} extension={extension} />;
};

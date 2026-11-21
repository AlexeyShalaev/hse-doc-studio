import { useTranslation } from "react-i18next";
import type { DocumentSegmentProps } from "../contract";

// S8c: ЗАМЕНИТЬ ЭТОТ ФАЙЛ. Места подписей документа по его PDF (`PackPlacesEditor`) пишет S8c;
// пока заглушка. Контракт props: `DocumentSegmentProps` (docs/design/pack-studio-ux.md, 12.7).
const SignaturesSegment = ({ doc }: DocumentSegmentProps) => {
  const { t } = useTranslation("packSpace");
  return (
    <div
      className="sp-ct-stub"
      data-testid="ct-stub-signatures"
      data-doc={doc.id}
    >
      <h2>{t("content.stub.title")}</h2>
      <p>{t("content.stub.signatures")}</p>
    </div>
  );
};

export default SignaturesSegment;

export { DocPlacementPanel } from "./ui/DocPlacementPanel";
export { PdfStampEditor } from "./ui/PdfStampEditor";
export { SignatureOverlay } from "./ui/SignatureOverlay";
export { SignatureEditorModal } from "./ui/SignatureEditorModal";
export { SignerPlateEditor } from "./ui/DetachedSignatureBlocks";
export { SlotPanel } from "./ui/SlotPanel";
export type { DocPlacementPanelProps } from "./ui/DocPlacementPanel";
export type { PdfStampEditorProps } from "./ui/PdfStampEditor";
export type { SlotPanelProps } from "./ui/SlotPanel";
export { SignSubmissionDialog } from "./ui/SignSubmissionDialog";
export type { SignSubmissionDialogProps } from "./ui/SignSubmissionDialog";
// КриптоПро ЭЦП Browser plug-in: страница подписанта маршрута ведёт свой сценарий подписи.
export {
  CadesError,
  exportCertificatePem,
  listCertificates,
  loadCadesPlugin,
  signDetached,
} from "./lib/cades";
export type { CadesCertificate, CadesPlugin } from "./lib/cades";

export type {
  SigningIdentity,
  SigningIdentityKind,
  SignMode,
  CreateSelfSignedRequest,
  GenerateOpenPgpKeyRequest,
  OpenPgpKey,
  OpenPgpKeys,
  TrustedRoot,
  UpdateSlotConfigRequest,
} from "./api/signingIdentitySchemas";
export {
  SigningIdentitySchema,
  SignModeSchema,
  CreateSelfSignedRequestSchema,
} from "./api/signingIdentitySchemas";
export { signingIdentityApi, publicKeyUrl } from "./api/signingIdentityApi";
export type { DefaultKey } from "./api/signingIdentityApi";
export {
  useSigningIdentities,
  useDefaultSigningKey,
  useSetDefaultSigningKey,
  useCreateSelfSigned,
  useImportPkcs12,
  useDeleteSigningIdentity,
  useUpdateSlotConfig,
  useOpenPgpKeys,
  useGenerateOpenPgpKey,
  useImportOpenPgpKey,
  useTrustedRoots,
  useAddTrustedRoot,
  useDeleteTrustedRoot,
  signingIdentityKeys,
} from "./api/signingIdentityQueries";

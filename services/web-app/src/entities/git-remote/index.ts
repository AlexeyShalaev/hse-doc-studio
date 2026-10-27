export * from "./api/gitRemoteSchemas";
export {
  PROVIDER_CATALOG,
  apiBase,
  assessScopes,
  detectProvider,
  instancePrefixCandidates,
  providerForHost,
  providerSpec,
  webBase,
} from "./model/providerCatalog";
export type {
  DetectProviderOptions,
  ProviderAuthVariant,
  ProviderCatalog,
  ProviderDetection,
  ProviderSpec,
  ScopeAssessment,
  TokenSufficiency,
  WebBaseInput,
} from "./model/providerCatalog";
export {
  findHostSettings,
  hostKey,
  providerOfHost,
} from "./model/hostProvider";
export {
  EXPIRING_SOON_DAYS,
  credentialExpiry,
  worstExpiry,
} from "./model/credentialExpiry";
export type { CredentialExpiry, ExpiryState } from "./model/credentialExpiry";
export {
  cleanText,
  defaultTokenDescription,
  defaultTokenName,
  encodeComponent,
  sshLinks,
  tokenLinks,
} from "./model/providerLinks";
export type {
  ProviderLink,
  ProviderLinkKind,
  SshLinkInput,
  SshLinks,
  TokenLinkInput,
  TokenLinks,
} from "./model/providerLinks";
export { gitRemoteApi } from "./api/gitRemoteApi";
export type { CloneFromBundleParams } from "./api/gitRemoteApi";
export {
  gitRemoteKeys,
  useCiPreview,
  useCloneDefaults,
  useCheckCredential,
  useCreateCredential,
  useCredentials,
  useDeleteCredential,
  useDeleteHost,
  useGitHosts,
  useHostSettings,
  useProbe,
  useSecretsStatus,
  useSharedFolder,
  useStartClone,
  useStartCloneFromBundle,
  useTrustHost,
  useUpdateCredential,
  useUpdateHostSettings,
  useWriteCi,
} from "./api/gitRemoteQueries";

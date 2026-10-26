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
  useCreateCredential,
  useCredentials,
  useDeleteCredential,
  useDeleteHost,
  useGitHosts,
  useProbe,
  useSecretsStatus,
  useSharedFolder,
  useStartClone,
  useStartCloneFromBundle,
  useTrustHost,
  useUpdateCredential,
  useWriteCi,
} from "./api/gitRemoteQueries";

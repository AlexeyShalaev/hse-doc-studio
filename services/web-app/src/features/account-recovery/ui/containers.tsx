import { useCallback, useState } from "react";
import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import { Spinner } from "@shared/ui";
import { useBootstrap, useRefreshSession } from "@entities/session";
import { recoveryApi } from "../api/recoveryApi";
import { useRecoveryRequest } from "../model/useRecoveryRequest";
import { ForgotCard, ForgotSentCard } from "./ForgotCard";
import { ResetCard, ResetDoneCard, ResetExpiredCard } from "./ResetCard";
import { VerifyCard, type VerifyState } from "./VerifyCard";

const Loading = () => (
  <div
    className="flex justify-center"
    style={{ padding: "32px 0" }}
    data-testid="auth-loading"
  >
    <Spinner />
  </div>
);

/** /forgot: форма, затем нейтральный итог. */
export const ForgotForm = () => {
  const { data } = useBootstrap();
  const { submit, pending, failure, result } = useRecoveryRequest(
    recoveryApi.forgot,
  );
  const [sentTo, setSentTo] = useState("");
  const onSubmit = useCallback(
    (email: string) => {
      setSentTo(email);
      void submit(email);
    },
    [setSentTo, submit],
  );
  if (!data) return <Loading />;
  if (result) {
    return (
      <ForgotSentCard
        email={sentTo}
        link={result.link}
        smtp={data.auth.smtp_enabled}
      />
    );
  }
  return <ForgotCard pending={pending} failure={failure} onSubmit={onSubmit} />;
};

/** /reset/:token: новый пароль; просроченная ссылка ведёт к новому запросу. */
export const ResetForm = ({ token: tokenProp }: { token?: string }) => {
  const params = useParams();
  const token = tokenProp ?? params.token ?? "";
  const { data } = useBootstrap();
  const call = useCallback(
    (password: string) => recoveryApi.reset(token, password).then(() => true),
    [token],
  );
  const { submit, pending, failure, result } = useRecoveryRequest(call);
  if (!data) return <Loading />;
  if (result) return <ResetDoneCard />;
  if (failure?.code === "token_invalid") return <ResetExpiredCard />;
  return (
    <ResetCard
      minLength={data.auth.password_min_length}
      pending={pending}
      failure={failure}
      onSubmit={(password) => {
        void submit(password);
      }}
    />
  );
};

/** /verify/:token: письмо открыли, ссылка проверяется сразу. */
export const VerifyEmail = ({ token: tokenProp }: { token?: string }) => {
  const params = useParams();
  const token = tokenProp ?? params.token ?? "";
  const { data } = useBootstrap();
  const refresh = useRefreshSession();
  // POST в запросе нужен ради дедупликации: StrictMode монтирует экран дважды,
  // а ссылка одноразовая, второй вызов дал бы «недействительна».
  const check = useQuery({
    queryKey: ["session", "verify-email", token],
    queryFn: async () => {
      await recoveryApi.verify(token);
      void refresh();
      return true;
    },
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const resendCall = useCallback(
    (email: string) =>
      recoveryApi.resendVerification(email).then((res) => ({ ...res, email })),
    [],
  );
  const resend = useRecoveryRequest(resendCall);

  let state: VerifyState = "checking";
  if (check.isSuccess) state = "done";
  else if (check.isError) {
    const error = check.error;
    state =
      error instanceof ApiError && (error.status === 0 || error.status >= 500)
        ? "unreachable"
        : "invalid";
  }
  return (
    <VerifyCard
      state={state}
      onRetry={() => {
        void check.refetch();
      }}
      resend={{
        pending: resend.pending,
        failure: resend.failure,
        sent: resend.result,
        smtp: data?.auth.smtp_enabled ?? true,
        onSubmit: (email) => {
          void resend.submit(email);
        },
      }}
    />
  );
};

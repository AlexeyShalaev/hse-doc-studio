import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import { Spinner } from "@shared/ui";
import { useBootstrap } from "@entities/session";
import { registerAvailability } from "../lib/registerAvailability";
import { signUpApi } from "../api/signUpApi";
import { usePasskeySignUp } from "../model/usePasskeySignUp";
import { useSignUp } from "../model/useSignUp";
import { RegisterCard } from "./RegisterCard";
import { RegisterResultCard, RegisterUnavailableCard } from "./RegisterNotice";

/** /invite/:token: регистрация по приглашению с заблокированной почтой. */
export const InviteForm = ({ token: tokenProp }: { token?: string }) => {
  const params = useParams();
  const token = tokenProp ?? params.token ?? "";
  const { data: boot } = useBootstrap();
  const invitation = useQuery({
    queryKey: ["session", "invitation", token],
    queryFn: () => signUpApi.invitation(token),
    retry: false,
    staleTime: Infinity,
  });
  const { submit, pending, failure, result } = useSignUp(token);
  // С passkey можно только по приглашению на конкретный адрес: его почту подтверждает само приглашение.
  const passkey = usePasskeySignUp(token, {
    enabled:
      (boot?.auth.passkeys_enabled ?? false) &&
      (invitation.data?.email ?? "") !== "",
  });

  if (!boot || invitation.isPending)
    return (
      <div
        className="flex justify-center"
        style={{ padding: "2rem 0" }}
        data-testid="auth-loading"
      >
        <Spinner />
      </div>
    );
  if (result) {
    return (
      <RegisterResultCard
        status={result.status}
        link={result.link}
        email={result.email}
        invited={(invitation.data?.email ?? "") !== ""}
      />
    );
  }
  if (invitation.isError) {
    const error = invitation.error;
    const unreachable =
      error instanceof ApiError && (error.status === 0 || error.status >= 500);
    return (
      <RegisterUnavailableCard
        reason={unreachable ? "unreachable" : "invitation_invalid"}
      />
    );
  }
  // Без входа по паролю регистрация по приглашению остаётся, если можно сразу создать passkey.
  if (registerAvailability(boot.auth, true) !== "form" && !passkey.available) {
    return <RegisterUnavailableCard reason="closed" />;
  }
  return (
    <RegisterCard
      auth={boot.auth}
      invitation={invitation.data}
      pending={pending}
      failure={failure ?? passkey.failure}
      onSubmit={(input) => {
        void submit(input);
      }}
      passkey={{
        available: passkey.available,
        pending: passkey.pending,
        onStart: (name) => {
          void passkey.start(name);
        },
      }}
    />
  );
};

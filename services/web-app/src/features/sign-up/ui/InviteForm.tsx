import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@shared/api";
import { Spinner } from "@shared/ui";
import { useBootstrap } from "@entities/session";
import { registerAvailability } from "../lib/registerAvailability";
import { signUpApi } from "../api/signUpApi";
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

  if (!boot || invitation.isPending)
    return (
      <div
        className="flex justify-center"
        style={{ padding: "32px 0" }}
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
  if (registerAvailability(boot.auth, true) !== "form") {
    return <RegisterUnavailableCard reason="closed" />;
  }
  return (
    <RegisterCard
      auth={boot.auth}
      invitation={invitation.data}
      pending={pending}
      failure={failure}
      onSubmit={(input) => {
        void submit(input);
      }}
    />
  );
};

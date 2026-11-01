import { Spinner } from "@shared/ui";
import { useBootstrap } from "@entities/session";
import { registerAvailability } from "../lib/registerAvailability";
import { useSignUp } from "../model/useSignUp";
import { RegisterCard } from "./RegisterCard";
import { RegisterResultCard, RegisterUnavailableCard } from "./RegisterNotice";

/** /register: форма по режиму установки, итог после отправки. */
export const SignUpForm = () => {
  const { data } = useBootstrap();
  const { submit, pending, failure, result } = useSignUp(null);
  if (!data)
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
      />
    );
  }
  const availability = registerAvailability(data.auth, false);
  if (availability !== "form") {
    return <RegisterUnavailableCard reason={availability} />;
  }
  return (
    <RegisterCard
      auth={data.auth}
      pending={pending}
      failure={failure}
      onSubmit={(input) => {
        void submit(input);
      }}
    />
  );
};

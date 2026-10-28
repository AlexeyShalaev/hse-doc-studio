import { useState } from "react";
import { useSearchParams } from "react-router";
import {
  DEFAULT_NEXT_PATH,
  safeNextPath,
  useBootstrap,
  wasSessionEnded,
} from "@entities/session";
import { useSignIn } from "../model/useSignIn";
import { ssoStartUrl } from "../lib/ssoStartUrl";
import { LoginCard } from "./LoginCard";

export const SignInForm = () => {
  const { data } = useBootstrap();
  const [params] = useSearchParams();
  const { submit, pending, failure } = useSignIn();
  // Читаем один раз при показе формы: флаг гаснет при следующем входе.
  const [sessionEnded] = useState(wasSessionEnded);
  if (!data) return null;
  const next = safeNextPath(params.get("next"), DEFAULT_NEXT_PATH);
  return (
    <LoginCard
      auth={data.auth}
      pending={pending}
      failure={failure}
      sessionEnded={sessionEnded}
      ssoHref={(id) => ssoStartUrl(id, next)}
      onSubmit={(email, password) => {
        void submit(email, password);
      }}
    />
  );
};

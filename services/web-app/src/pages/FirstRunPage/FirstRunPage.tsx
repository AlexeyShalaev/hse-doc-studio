import { SetupWizard } from "@features/server-setup";
import { SignInForm } from "@features/sign-in";

/**
 * /first-run: мастер первого запуска. Форму входа для нейтрального экрана
 * (админ уже создан, а сессии у человека нет) подставляет страница: фичи друг
 * друга не импортируют.
 */
export const FirstRunPage = () => <SetupWizard signIn={<SignInForm />} />;

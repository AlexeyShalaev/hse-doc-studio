# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.19.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.18.0...v0.19.0) (2026-11-10)


### Features

* **compile:** воспроизводимая сборка LaTeX (R12) ([7ffa10c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7ffa10c75d68d1de619f94e20509008ea2093fda))
* **compile:** воспроизводимая сборка LaTeX (R12) ([9924661](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9924661d495339de8d69e85c4734409b4706aba6))
* **inbox:** «Принять» приглашение подписанта ведёт на страницу подписи ([6f01e52](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6f01e52673b156bf7df2224c88f0471ee7c74369))
* **mcp:** тулы маршрута подписания: get_signing_route, list_signing_tasks и опасный send_for_signing ([ac94181](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ac94181f7839d53afdfffc3483ea1c64ba5278d8))
* **signatures:** R10 signer profile with saved image, public key for the plate and plate data port ([547d07e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/547d07eaf4aa9fe856165d771d5d5dcdb9548faa))
* **signatures:** R2 — порядок маршрута подписания из пака и default_route ([97a0115](https://github.com/AlexeyShalaev/hse-doc-studio/commit/97a01157492bbf1e0b6aa9906ce678cce56abc6a))
* **signatures:** R3 маршрута подписания, придержанные слоты withheld и причина плана awaiting_approval ([19974de](https://github.com/AlexeyShalaev/hse-doc-studio/commit/19974deb7d7b9bad4955d22a7783d061fff288ce))
* **signatures:** signer profile with saved image and public key, plate data port (R10) ([aa58f09](https://github.com/AlexeyShalaev/hse-doc-studio/commit/aa58f09bc7bda7ae5e464147c4c25545fe3add79))
* **signatures:** порядок маршрута подписания из пака и default_route (R2) ([f1aa4b0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f1aa4b0e94e43cd96afddc2847ec9d7af81614a0))
* **signatures:** придержанные маршрутом слоты withheld и причина плана awaiting_approval (R3) ([2bb6ca0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2bb6ca08189c16f34e324780d87f9a32b9f49af5))
* **signing-route:** «Показать» картинку, придержанную маршрутом, после его отмены ([c3f5087](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c3f5087460b85fd85062bc00840bbf2c1d07e62b))
* **signing-route:** «Скопировать ссылку» у каждого, кто ещё не подписал ([b894aea](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b894aea1b2ee2292a053e97f6026996bb5c7aa39))
* **signing-route:** R1 — ядро маршрута подписания: сущности, состояния и evaluate() ([035ff29](https://github.com/AlexeyShalaev/hse-doc-studio/commit/035ff29066310638678ddb7687a4d119621ef0b8))
* **signing-route:** R1 ядро маршрута подписания: сущности, состояния и evaluate() ([b022f40](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b022f40b24434740cab5da6c405f78a1761d61b1))
* **signing-route:** R11 — «Напомнить» и автонапоминания подписантам ([90be093](https://github.com/AlexeyShalaev/hse-doc-studio/commit/90be0933bab28fd70616a0ea84fe50874693790b))
* **signing-route:** R11 «Напомнить» и автонапоминания подписантам ([5176839](https://github.com/AlexeyShalaev/hse-doc-studio/commit/51768394e04cf428fca012252636b2ce9128a984))
* **signing-route:** R4 — хранение маршрутов подписания в Postgres: таблицы, ISigningRouteRepository, версия записи ([a32be28](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a32be28072d1aebe61d2baf9becae50ec56c1fc8))
* **signing-route:** R4 хранение маршрутов подписания в Postgres: таблицы, ISigningRouteRepository, версия записи ([7ab536e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7ab536e70f0dc9fc7fae08575130e466e520df33))
* **signing-route:** R5 — сценарии автора и API маршрута подписания ([f770a19](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f770a195c67bcd7f89c8efbad3db9f77140febbe))
* **signing-route:** R5 сценарии автора и API маршрута подписания ([65585d2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/65585d2d90dd4bf4951f9db3f627c246b61d6907))
* **signing-route:** R8 — уведомления маршрута подписания: виды signing_*, письма, «На подпись», хук принятия приглашения ([8f137b9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8f137b93771e371ff5b7add46d0004277b21ae1e))
* **signing-route:** R8 уведомления маршрута подписания: виды signing_*, письма, «На подпись», хук принятия приглашения ([483e98a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/483e98a7d7ba10b054529564ca4698f5d3e9582d))
* **signing-route:** R9 аудит маршрута и тулы MCP ([70b9081](https://github.com/AlexeyShalaev/hse-doc-studio/commit/70b90815d8233fa25291b99101e5c8fe436e2427))
* **signing-route:** аудит маршрута: события signing_route.* и route_id у подписей маршрута ([099d176](https://github.com/AlexeyShalaev/hse-doc-studio/commit/099d176125be87f79b985d5f52adeed57f182f2b))
* **signing-route:** коды отказов ключа, проверка пароля до согласия, очередь у других входов подписи, предпросмотр своей картинки ([fdf6dee](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fdf6dee048ec7a2f656e715c5c91647ed8542fed))
* **signing-route:** контракт задачи подписанта: эталоны, zod-схемы, моки и тексты отказов ([27da674](https://github.com/AlexeyShalaev/hse-doc-studio/commit/27da6740f100558b5e579597e82076abcbbcbdb4))
* **signing-route:** контракт и моки: ссылка подписанту, помеха placement_off, sent у sign_failed ([4436561](https://github.com/AlexeyShalaev/hse-doc-studio/commit/44365610e2a7d639fb7180667a97c7734b06260d))
* **signing-route:** люди по персонам в правке, кандидаты на персону и next в приглашении из маршрута ([db992a5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/db992a54d93d425ca04aae73ea918ffeaaeb0cb5))
* **signing-route:** маршрут в плане подписей на фронтенде, ссылка на страницу подписи в «Подписать комплект», тесты сверки и документация ([25fb6f6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/25fb6f6919d1f9e81b1395bdd164d950b5d79079))
* **signing-route:** подписи событий маршрута в разделе «Аудит» и документация тулов MCP ([63e605c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/63e605c9a85d6521c98881f2070e8787e970fa44))
* **signing-route:** правила действий подписанта, вид задачи и импорт ключа профиля при заполнении плашки ([536c835](https://github.com/AlexeyShalaev/hse-doc-studio/commit/536c835c7d2cd0b501995af270a14788855769f7))
* **signing-route:** свои записи маршрута не зовут сверку, «Подписать комплект» пересчитывает маршрут одним проходом ([9a45fb9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9a45fb9786a09c816d9317d491e217b1973b50f6))
* **signing-route:** сторожа правок подписей, «Подписать комплект» в очередь маршрута, сверка с проектом ([8db1678](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8db1678b09c981e9b1267d1037121eb58332eae1))
* **signing-route:** сторожа правок подписей, сверка с проектом и маршрут в плане (R7) ([6b846da](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6b846da211302396fe6cd55418a26c8b238ef647))
* **signing-route:** сценарии подписанта и API задачи task (R6) ([0572ce9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0572ce9daa075a4d4e9c44b5e3bcdd3bdc26bca8))
* **signing-route:** сценарии подписанта и API задачи task (R6) ([50f8c8a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/50f8c8a61e0478907b38d9a5d2b572ae9bb5d674))
* **web:** signer profile block in signing settings (R10) ([f38129a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f38129abb66ff5e34fa653803fcbdfb2cf7ab602))
* **web:** W1 маршрут подписания: entities/signing-route и контракт API ([78e9520](https://github.com/AlexeyShalaev/hse-doc-studio/commit/78e9520556f7db679bd68f76aacde175ee27c4cc))
* **web:** W3 карточка «Подписание» на точке сдачи и плашка документа на подписании ([c4a7fdc](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c4a7fdc5f88bcc09732758b7fec8341bc86dd13c))
* **web:** W3 маршрут подписания: карточка «Подписание» на точке сдачи и плашка в редакторе ([f2e014e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f2e014ebdaee352eded6382450b4933c4bc37cf3))
* **web:** W4 маршрут подписания: страница подписанта /sign/:projectId/:routeId ([9c9bc11](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9c9bc11b4813c8678e04634ea5dd5527e4f43fae))
* **web:** W5 маршрут подписания: подпись прямо на странице подписанта ([58d0494](https://github.com/AlexeyShalaev/hse-doc-studio/commit/58d04943e72c2a199186d9c2065ba6222b4f98f8))
* **web:** W6 маршрут подписания: «На подпись» во «Входящих» и колокольчике ([8038a63](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8038a635fb2723e8bb31492098511957ad8ec0a4))
* **web:** W6 маршрут подписания: «На подпись» во «Входящих», тексты и переходы уведомлений, строка задач в колокольчике ([0587c71](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0587c71ec018037a6bf816a4203f82736a7d65d5))
* **web:** отказ подписи sign_failed на странице подписанта, коды пароля как у отправки (400) ([b6a5f15](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b6a5f15c966c0b5fde385a20294e5f5224e0bed5))
* **web:** подпись на странице подписанта: картинка, ключ Студии, КриптоПро, готовая подпись (W5) ([a126baa](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a126baaf3b412446681104d1d0b9391b1f538dbe))
* **web:** подсказки и бюджеты блока подписи: плашка без ключей сервера, отказ 404, новый маршрут начинает выбор заново (W5) ([2fcb893](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2fcb8933de98336f932defaf71a84493aa6adfa6))
* **web:** после входа и приглашения подписант попадает на страницу подписи (W4) ([a20a4f8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a20a4f8e91c2cfe23fa4db28c7916d49d1edba14))
* **web:** страница подписанта /sign/:projectId/:routeId (W4) ([33aabdf](https://github.com/AlexeyShalaev/hse-doc-studio/commit/33aabdf9d407aaa3919a071dbd9caf45d283ed5a))
* **web:** сущность маршрута подписания: схемы, API, запросы и моки (W1) ([f5e43a4](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f5e43a405abb312f69c6d72a2fad4a77bd792b6c))
* **web:** экран «Отправка на подписание» для точки сдачи (W2) ([ce4ab67](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ce4ab67c42e8d8cdad4b49ab11ce3769df6073d9))
* **web:** экран «Отправка на подписание» для точки сдачи (W2) ([596991d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/596991db2e19b7b244ca76225a2021b2758bf635))


### Bug Fixes

* **ci:** юнит-тесты на Windows: POSIX-пути в mountinfo и справочнике env ([2ea3d53](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2ea3d539f1fc7252dd9be925df836aceda3efd81))
* **diagnostics:** the leader probe only sees the lock in its own database ([647a221](https://github.com/AlexeyShalaev/hse-doc-studio/commit/647a221522751d754ae8c1aeb7d262d3ee6492b4))
* **e2e:** стабильные E2E server-lite, бэкапы в смоуке и Windows-юниты ([80ec897](https://github.com/AlexeyShalaev/hse-doc-studio/commit/80ec8973d169cff44e753ceb92312afb983a7215))
* **mcp:** send_for_signing называет помеху placement_off; тест отправки включает места подписей ([15c1ddf](https://github.com/AlexeyShalaev/hse-doc-studio/commit/15c1ddf2263d1fc22e2b5dd5f1f4a64212760385))
* **signing-route:** вторая доводка: «Показать» после отмены, «Принять» к подписи, помеха другой точки, ссылка заранее, слова, способ и ширина плашки ([8990640](https://github.com/AlexeyShalaev/hse-doc-studio/commit/89906404e3c81555bfab90e6ae5185fdbb33fa88))
* **signing-route:** доводка маршрута: помеха placement_off, выбор человека, ссылка подписанту, «отправлен, не подписан» ([88acfff](https://github.com/AlexeyShalaev/hse-doc-studio/commit/88acfff74f5214be37517631c056df94d7b3efd7))
* **signing-route:** единые слова маршрута: «контрольная точка», «Return for revision», «build the package» ([5f747ac](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5f747ace55d493c6dec819e614bc03d994210fb7))
* **signing-route:** карточка «Подписание»: ссылка приглашённому без пауз напоминания, подпись отправителя не поставлена ([cc0e7b8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/cc0e7b80186f61ea382faee13cb00ddb695abc5f))
* **signing-route:** коды маршрута не в каталоге identity ([ad259c7](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ad259c71420396d88f1b3b7fd15532c8c93e3fa1))
* **signing-route:** периодическая сверка только идущих маршрутов, пересчёт после «Подписать комплект» и при сбое подписи ([0da48b8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0da48b85616a88017e3b6cd89508229aecc2399e))
* **signing-route:** помеха «документ в другом маршруте» называет ту точку и что сделать ([f81f39c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f81f39c550eda8606d99ceb98a8c3b52bf373b19))
* **signing-route:** помеха отправки placement_off у слота без места на странице ([63a3b55](https://github.com/AlexeyShalaev/hse-doc-studio/commit/63a3b55b183b3a243ea0650f25b68027290d283c))
* **signing-route:** при смене способа на ЭП с плашкой узкое место растёт до 70 мм ([2ab4709](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2ab470918c13bb3e4450affc60d131bad4e9883b))
* **signing-route:** редактор маршрута: выбор человека из кандидатов, переход от помехи к размещению, «отправлен, не подписан» ([03c5c58](https://github.com/AlexeyShalaev/hse-doc-studio/commit/03c5c581407690835d190d8557f60f4d3fc5d318))
* **signing-route:** снимок принимает способ и плашку подписанта до согласия ([a9f0086](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a9f008657ff27a18fec3a8f556585ce404a83ed0))
* **signing-route:** способ с картинкой или плашкой без места на странице не предлагается ([83ac19b](https://github.com/AlexeyShalaev/hse-doc-studio/commit/83ac19b51c405f7f7dc73a60791ef1015cc32bd9))
* **signing-route:** ссылка подписанту без пауз повтора приглашения и признак sent у sign_failed отправки ([0494586](https://github.com/AlexeyShalaev/hse-doc-studio/commit/04945863ce0a1cea8a793c1405aa27d06ac360ad))
* **signing-route:** тексты маршрута без рода: «Возвращено на доработку ({кто})», «согласовано», «подписано» ([6b27e5d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6b27e5d1b886fab6c027fdece98547b03c3627ed))
* **signing-route:** тест контейнера под хранилище с аудитом, бюджет словаря аудита 9.7 kB ([b6f0847](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b6f08472b0d011cfbbc4829e020521cd3c477879))
* **ui:** «Входящие» и листание PDF на телефоне, ссылки-кнопки без подчёркивания ([c91f0b8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c91f0b834400bf33031e7cd34f8f4743c10784a0))
* **web:** W3 гостю по ссылке маршруты подписания не запрашиваются ([8c0bb10](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8c0bb1012adf0b9d02b022e9ad6505dd479e903d))
* **web:** контракт маршрута подписания по перечислениям ядра R1 (W1) ([8e62289](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8e62289b693d6f6ba4db13c06fcf95ff028a6429))
* **web:** новый маршрут точки снимает с контроля и отменённый (W1) ([adbdcdc](https://github.com/AlexeyShalaev/hse-doc-studio/commit/adbdcdcbd951e25d0e3bdfc7a83c0deb2dace913))
* **web:** страница подписанта на телефоне: имя слота своей строкой, ссылка во «Входящие» на вкладку «На подпись» ([ec10c1a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ec10c1aa7d7f3ce2577fb671241f39706a72ef82))
* **web:** страница подписанта на телефоне: имя слота своей строкой, ссылка на «На подпись» ([c6a131c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c6a131c0d52e64e781a2344c31f53ab7033aade6))

## [0.18.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.17.2...v0.18.0) - 2026-11-09

- «Signed» download returns the actual signed file. If the PDF is frozen and current, you get it as is, with PAdES signatures when there are any. Without a current freeze you get a print copy with visible stamps but no electronic signatures. Signatures are no longer applied anew on every download.
- With PAdES signatures the signing package holds two PDFs: the final signed one and the original for detached signatures, named as in the LMS package.
- Moving a project folder or switching between the local Studio and the cloud no longer makes signatures outdated: the visible layer fingerprint uses paths inside the project. Existing signatures stay valid.
- SSE coursework template 2026.1.3: at topic approval and final submission signatures are accepted as an image or a detached signature, not PAdES. Existing projects get it as a template update; a slot already set to PAdES asks to change the method.
- MCP create_project creates team projects: several authors, supervisor, co-supervisor and academic supervisor with the same checks as the creation wizard. list_templates shows whether a template supports teams, and set_project_people accepts an author topic.
- The local Studio on macOS gets its document fonts: the installer copies Times New Roman, Arial, Courier New and Consolas from the Mac, since Docker Desktop cannot mount the system fonts folder. If fonts are missing, settings explain why.
- The SSH install dialog on the model servers page no longer shows raw keys instead of text.

## [0.17.2](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.17.1...v0.17.2) - 2026-11-09

- Cloud builds in a separate namespace work again: a build pod no longer gets the runner pod from another namespace as its owner, which made Kubernetes delete it at once and the build failed with a Kubernetes executor error. This affects runner.installFromUi.buildNamespace and runner.kubernetes.namespace.
- A detached OpenPGP signature made with a Studio key is now verified on cloud runners too: the Studio passes the signer's public key to the runner. Previously such a signature showed as an unknown signer key and a signer mismatch. The secret part of the key never leaves the server.
- OpenPGP keys follow the server key storage policy: when storage is forbidden they cannot be created or imported, and stored keys cannot be used to sign, the same as .p12 certificates. Public keys for checking other people's signatures can always be uploaded. The Keys on the server counter in the admin area counts OpenPGP keys, and a secret key disguised as a public one no longer gets into the keyring.
- An OpenPGP key and its passphrase are passed to gpg without temporary files on disk.

## [0.17.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.17.0...v0.17.1) - 2026-11-09

- A successful build without output files no longer stays unfinished: previously its result was not applied and the api retried it on every restart.

## [0.17.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.16.0...v0.17.0) - 2026-11-09

- Signatures by plan: a document has a signature plan (who signs, where and how), and the submission point counts readiness from it. Methods can be mixed in one document: a signature image, an image with a digital signature, an invisible digital signature, a detached signature. Sign bundle signs all your slots in the submission point documents in one step, PAdES is applied over the frozen PDF, and slot permissions are checked.
- The LMS bundle is built from the signature plan. MCP gains get_signature_plan and sign_submission: signing over MCP needs a separate sign permission on the token, a password-protected key is not used over MCP, and passwords and keys never appear in responses.
- MCP is extended: template update (status, plan, apply), document variant selection, project fields and clearing them, editing one author, the author e-mail and the academic supervisor, project members, invitations by e-mail and access revocation, and git_sync as the sync button with a summary and a list of conflicts. All changes go through the same permissions and audit log as the web interface. compile_document and clone_cloud_project wait up to 45 s so they stay within the client timeout.
- Inviting a supervisor or co-author opens with a ready message built from the project data: name, topic, role. The text can be edited before sending.
- Build queue: documents that no runner can take are not queued by Build all and are listed separately, and busy runners are told apart from missing ones. In the admin queue, the jobs of one Build all are grouped into one row that can be cancelled as a whole.
- Cloud builds survive an api restart: jobs are not lost during a rollout, the server stops gracefully, and a build interrupted by a restart is shown as interrupted instead of hanging. The api downtime window during a rollout is shorter.
- Admin-installed runners: a separate namespace for build pods (runner.installFromUi.buildNamespace), a built-in Gotenberg for office jobs (pptx, docx) with its address passed to runners, and office jobs on the isolation screen. Removing an install revokes the runner, a failed update rolls back to the previous version, and the admin area shows whether the runner came back online.
- Templates: the Studio knows the inventory of built-in packs and recognises a mounted template catalog. If the catalog is behind, the message names it instead of suggesting a Studio update, and updating warns about it. The pack binding of a dev build is no longer carried over to the published image.
- Fixes: placeholders in disabled edition branches (\if) no longer count in checks; the ⋯ menu and tooltips on desktop are clickable again over the settings dialog.

## [0.16.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.15.0...v0.16.0) - 2026-11-08

- In-place update of admin-installed runners: a runner installed from the admin area in Kubernetes or Docker is updated to the Studio version without removing and reinstalling it. The name, token, data volume and install limits are kept, the manifest is applied with the current isolation rules, progress is shown step by step, and the update is written to the audit log. The chart adds the update permission on Deployments.
- Admin-installed runners are managed on the Runners page: Update and Remove install in the Actions menu, an Update to vX button for outdated runners, and a separate block for installs whose runner is already revoked.
- The local Studio no longer offers to fetch cloud builds of documents that are not produced as PDF (such as pptx), and build fetch failures now show specific messages instead of a generic connection error.

## [0.15.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.14.0...v0.15.0) - 2026-11-08

- Runner details in the admin area: where each runner runs (Kubernetes pod, container or host) and how it builds documents (Docker or Kubernetes), its CPU, memory and storage limits, and a cluster isolation panel. The panel shows the policies declared in Helm and, with runner.isolationInfo.readCluster enabled, what actually exists in the cluster: NetworkPolicy, ResourceQuota, LimitRange and Pod Security labels.
- MCP: create_project no longer asks for a folder in the cloud, the new set_project_people tool sets the project supervisor and members (recorded in the audit log), and clone_cloud_project in the local Studio clones a project from the cloud.
- Kubernetes builds no longer fail with idle_timeout after the PDF is ready: word and character counting is time limited, and if it hangs the build still succeeds with a warning.
- Local Studio linked to the cloud: the server version is refreshed on sync, a last build id that this Studio does not have is no longer returned, and documents without a PDF (such as pptx) no longer fail PDF autopublish.
- SPI coursework template 2026.1.2: the topic application matches the official 2026 form, names are shown as "Surname I.O.". The released 2026.1.1 is unchanged.

## [0.14.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.13.0...v0.14.0) - 2026-11-07

- Roll back to an earlier version from the admin area: a list of published releases, each with a verdict on database schema compatibility. A rollback is allowed only to a version with the same migration state, a backup is taken first when configured, and if the version does not come up the system returns to the previous image. Requires an updated updater.
- Auto-install switch for updates: while it is off, new versions are not installed on their own, but checks and notifications continue. After a successful rollback auto-install switches to notify-only mode. Rollbacks and toggles are written to the audit log.
- Limits and isolation for Kubernetes runners: requests and limits for CPU, memory and storage on runners and build pods (set in Helm and in the install form in the UI), clear failure reasons for out-of-memory and storage overruns, deny-all network traffic for build pods, optional runner egress policies, ResourceQuota and LimitRange, stricter pod security settings and reduced Studio permissions. Already installed runners stay unchanged until reinstalled.

## [0.13.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.12.0...v0.13.0) - 2026-11-07

- Model servers: the admin area has a new Model servers page. It installs Ollama, vLLM or SGLang on the machine that runs Studio, or on another one over SSH (one-time password or key, with an offer to save the access encrypted). It shows the API address and key. By default a server listens on the loopback interface only; vLLM and SGLang are exposed publicly only with an API key and after confirmation. For gated models a Hugging Face token is set in settings. In Helm, installing on the same machine is off by default (modelServers.local.enabled).

## [0.12.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.11.0...v0.12.0) - 2026-11-07

- Installing a runner with a single command: creating a token now shows a ready docker run line and a script that installs the runner as a service (systemd on Linux, launchd on macOS). The script contains no secrets and supports a dry run, status and uninstall.
- Installing a runner on the same machine as Studio from the admin area: as a container in Docker, or as a separate restricted Deployment in Kubernetes (off by default in Helm, value runner.installFromUi.enabled).
- Installing a runner on other machines over SSH from the admin area: host key fingerprint confirmation, password or key with passphrase, a plan and step-by-step progress. Credentials are one-time by default; you can optionally save them encrypted for updates and reinstalls. Internal networks stay blocked until the address is added to HSE_STUDIO__RUNNER_INSTALL__SSH_ALLOWLIST.
- For administrators: the server applies the new migration on first start (ri_01_runner_ssh_credentials), no manual steps are needed. SSH installation requires asyncssh (included in the server build).

## [0.11.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.10.0...v0.11.0) - 2026-11-06

- "Build all" no longer leaves jobs queued forever when the personal runner is busy and there are no shared runners: jobs wait for a free slot on the personal runner. Jobs that are already stuck are picked up on the runner's next poll.
- Self-diagnostics: every problem row can be opened to reach the page where it is fixed, for example a queue failure leads to the runners queue tab and backups lead to the backups page.
- Settings, Disk: Studio offers to clean up old system versions (images of earlier versions, stale tags of helper images, the stopped updater). The latest previous version kept for rollback is protected from bulk cleanup.

## [0.10.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.9.0...v0.10.0) - 2026-11-06

- A stale tab after an update no longer breaks the admin area: the app picks up the new version and offers to reload the page.
- The build queue shows real phases (queued, building), and the "Build is not responding" warning counts from the actual start, not from the click.
- Stopping a build in the cloud is synced with the local Studio and back: the status updates in both places.
- Warnings about missing backups and public runners can be acknowledged on purpose, and they stop nagging.
- The documents panel and the agent chat no longer overflow at narrow widths and large text sizes: buttons, labels and the model picker fit.

## [0.9.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.8.0...v0.9.0) - 2026-11-05

- The topic application and the presentation build without supervisor or author data: the new course project template version 2026.1.1 fixes the There's no line here to end error that broke the build when a signature field was empty. New projects are created on it right away, existing ones see it as a recommended small update: accept it in the project settings
- Cloud builds on a personal runner get the same fonts as local builds: Times New Roman, Arial and Consolas, which the local Studio takes from your computer when the runner connects if the fonts folder is empty. For a shared runner and a runner in Kubernetes the fonts folder is set by a setting (a volume). Microsoft fonts are not shipped with the Studio or its images. If a template asks for a font directly and it is missing, the build fails with a clear font missing reason and the font name
- Fixed a false upload error: when Build all started several builds of one project, the second build could delete the first one's finished PDF and the first reported that the result could not be uploaded. The result is now copied aside before uploading, and if the file really is missing the reason is named PDF not received. A failed build also no longer shows an endless Build is not responding warning and the Stop build button
- Text size: the step you pick no longer snaps back to the account value. Before, choosing 100 % right after 140 % could roll back until the save reached the server. Now an explicit choice on the device always beats the account value and is saved to the account, retrying on error
- For administrators, upgrading from 0.8.0: no database migrations. New runner settings: HSE_RUNNER__FONTS_DIR, HSE_RUNNER__FONTS_HOST_DIR and HSE_RUNNER__FONTS_MOUNT_TARGET (Docker runner), HSE_RUNNER__K8S__FONTS_CLAIM and runner.kubernetes.fonts.existingClaim in Helm (Kubernetes runner). Template 2026.1.1 is used automatically for new projects

## [0.8.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.7.0...v0.8.0) - 2026-11-04

- Text size: in Settings, Appearance you can choose the interface text size (90, 100, 112, 125 or 140 %). It changes at once across the whole app (menus, forms, dialogs, the editor, the admin area, the landing page), is remembered in your account and applies without flicker on load. Document content and the PDF page are not scaled. On a phone the 90 % step does not shrink buttons and fields below a comfortable size
- A failed build explains itself: the Build tab shows the failure code and reason, what to do and a Build again button, and the document list and the Now block show the reason under the name. The build log now reaches the cloud (before it was empty even for successful builds), including live, and refusals before start (no Docker, TeX image or runner) are recorded as a failed build. Reasons are named in plain words: no output for too long, no disk space, the result could not be uploaded to storage and others. The build silence timeout is raised from 120 to 300 seconds: the first build on a fresh font cache can stay quiet for a long time
- Presentations and other office documents in the cloud through your Studio: if Docker runs on your computer and the Gotenberg image is pulled (docker pull gotenberg/gotenberg:8), the local Studio tells the cloud it can convert, and the Build button for presentations and Word documents is no longer blocked. Without Docker or the image the previous explanatory message stays
- For administrators, upgrading from 0.7.0: the release has one database migration (cf_01_compile_failure, two optional columns in the build record), the server applies it itself on first start, take a backup before updating. New settings: HSE_STUDIO__COMPILE__IDLE_TIMEOUT_S (300 seconds by default) and HSE_RUNNER__TEX_IDLE_TIMEOUT_S for the runner. Runner build logs are kept on the api volume (meant for a single api replica)

## [0.7.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.6.0...v0.7.0) - 2026-11-04

- Mobile cloud version: the Studio is comfortable on a phone from 360 px. Dialogs and menus open as bottom sheets, tables become cards, input fields no longer zoom the page in iOS, buttons are at least 40 px, and the screen notch and on-screen keyboard are accounted for. Sign-in, the landing page, the home screen with the project list and filters, the inbox and Studio connection all work
- The project workspace on a phone: a bottom bar of sections (documents, remarks, submission, files, more), a project header with people online, connected Studios and sync, an editor with a scrollable toolbar and a distraction-free mode while typing, a PDF with zoom by buttons and pinch, and the agent chat full screen. Settings and the admin area also work well on a phone: sections in a sheet, single-column forms and tables as cards
- Not yet working on a phone: the ONLYOFFICE editor, side-by-side mode, keyboard shortcuts (the command palette and help are in the account menu), drag-and-drop of files into the window, CryptoPro signing and the onboarding tour with highlights. Tablets keep the desktop layout. The mobile version was tested on emulation, please report anything you find on real devices
- Fixes: the Help window opened from the account menu crashed on a phone; the Signatures and Authors pages of a project were clipped on narrow screens
- For administrators, upgrading from 0.6.0: this release has no database migrations and no new required settings, only the interface changes

## [0.6.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.5.0...v0.6.0) - 2026-11-04

- Cloud landing page: someone who opens the server address and is not signed in sees a page describing the Studio (who it is for, what it does, how to start, security) with the sign-in form right on it. The link to the cloud can be shared: messengers show it with a title, a description and a picture. Invitations, password reset, OIDC and passkey sign-in work as before. An administrator can turn the landing off in the installation settings, then the sign-in page opens straight away
- Connected Studios: a cloud project shows which of your local Studios are connected, whether they are online (or when they last were), the version, project sync, PDF upload, the state of your personal runner and of AI through your machine. The local Studio shows the same the other way round: the link to the cloud, what the cloud sees, who else is online in the project. For each document you can see where and when it was built and whether the build is current. A cloud PDF can be fetched into the local Studio with the Get build button, and with automatic sync on it is fetched by itself. The cloud has a My Studios list with a Forget device button. Only state metadata is sent: no paths, contents or keys
- People in the project: the project header shows avatars of members who are online right now, with a caption of what and where they are doing (editing the Application, viewing remarks, working locally) and a jump to the same document. Another person's cursor in a document shows their name, and the cursor colour matches their avatar. Members see each other in the browser and in the local Studio, guests with an access link are not listed. The load is minimal: one light signal a minute per person, nothing written to the database
- Bell and settings: the bell opens a small window with the latest notifications, a mark-as-read action and a Show all link instead of going to a page. The settings window is taller and wider, its menu scrolls and section names no longer wrap. When a local Studio cannot use AI through its runner, the reason and what to do are now shown, and the cloud has an Add in the cloud button for the Through my runner provider
- For administrators, runners outside the server network and storage: personal runners and browsers get S3 links at a public address. Set it with s3.publicEndpoint in Helm (HSE_STUDIO__S3__PUBLIC_ENDPOINT); the storage has to be published under its own name with TLS (see the runners section). Without a public address a cloud build on a runner outside the network fails with a clear storage_unreachable error and the self-diagnostics page warns. A fallback without publishing the storage: s3.outsideRunnerAccess: proxy, results go through the server
- For administrators, upgrading from 0.5.0: the release has one database migration (cd_01_connected_devices, connected devices and build data), the server applies it itself on first start, take a backup before updating. New settings: s3.publicEndpoint, s3.outsideRunnerAccess, s3.sharedRunnersOutside (Helm), HSE_STUDIO__SERVER__LANDING_ENABLED and the landing switch in the admin area. Fixed: for a cloud project the open repository button led to a 404 page, now it opens the project page

## [0.5.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.4.0...v0.5.0) - 2026-11-03

- Cloud projects in the local Studio: once connected to a server, the local Studio lists your cloud projects itself, in the same list as local ones and marked Cloud. One click on Open downloads the project into the projects folder (changeable in settings), shows the progress and opens it, with no clone wizard and no git on this path. The Open in local Studio link from the cloud takes you straight to the right project. Automatic sync and PDF upload need no setup and work for cloud projects from the start. If an open project is not linked to the cloud, the build panel says so: the PDF will stay on this computer
- Nicer e-mails: invitations, e-mail confirmation, password reset, address change, passkey notifications and project access e-mails now arrive designed, with a large button, a fallback link, a note on why you received it and a security block, along with a plain-text version. An e-mail is written in the recipient's account language (Russian or English) and the subject is translated too. In the admin area (Sign-in and registration) you can preview every e-mail in both languages and send a test one
- For administrators, one-button updates in Kubernetes: on the Updates page the Update and Roll back buttons now work in a cluster too. Turn it on with the updater.enabled flag in the Helm chart (off by default) and HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes: a separate pod changes the api Deployment image, runs migrations as a Job and waits for health, and the image is checked against the digest from the release. Permissions are limited to its own namespace. A backup runs first if one is configured, otherwise you must confirm the risk. If migrations were applied but the new version did not come up, the image is not rolled back automatically: the status is Needs hands, with ready commands. After such an update set the version in your values (image.tag), otherwise the next helm upgrade will bring the old image back
- Fixes: in the dark theme the answer options in the welcome questionnaire were black on dark and unreadable; the settings sidebar did not scroll, so lower sections (such as AI clients (MCP)) were out of reach, and the AI group heading was shown twice; on the server every start logged a local Ollama sync error
- For administrators, upgrading from 0.4.0: there are no database migrations in this release, the schema stays at pk_01_passkeys. New settings: updater.enabled in Helm (off by default), HSE_STUDIO__SERVER_UPDATE__EXECUTOR=kubernetes, and for the local Studio the cloud projects folder (Settings, Repository access). E-mails are sent as HTML together with a plain-text version: without SMTP nothing changes and links are still shown on screen

## [0.4.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.3.0...v0.4.0) - 2026-11-03

- Passkey sign-in: sign in with a fingerprint, Face ID or a hardware key instead of a password. Keys are added and removed in the profile, sensitive actions ask you to confirm your identity again, and an admin can reset a person's keys. An invitation to a specific address lets the person create an account with a key right away, with no password; an e-mail is sent when a key is added or reset. The admin people list shows the number of keys
- MCP: AI clients (Claude, Cursor and others) work with the Studio over the Model Context Protocol, both in the cloud at /mcp and in the local Studio on localhost. 51 actions are available: projects, files, builds, checks and the norm-control report, requirements, review comments and history. It works with a personal token carrying the MCP permission; dangerous actions are off by default, an admin turns each one on or off in the installation settings, and e-signatures are not available over MCP. For a local client there is the hse-doc-studio mcp bridge. See the AI clients (MCP) section for setup
- In-app help: articles with screenshots and short videos in Russian and English, in light and dark themes. Onboarding for new people: a short questionnaire and a guided tour that highlights interface elements on a demo project (creating a project, editing, AI, git) without risking your data; it can be run again
- Local version from the cloud: the server has a Local version page explaining how to download and install the local Studio and connect it to this server; installers run with HSE_STUDIO_CONNECT open the connection screen straight away. The server is checked before connecting
- Builds without runners: instead of a 503 error the Studio plainly says there are no cloud runners, blocks the build buttons and suggests building the document locally. The same applies when no runner has the required tags
- For administrators, runners in Kubernetes: in the Helm chart runner.executor=kubernetes starts a pod per build in its own namespace (permissions on pods only, with a NetworkPolicy), so the node's docker.sock is not needed. The default is still docker
- For administrators, upgrading from 0.3.0: the server applies the new migrations on first start (ob_01_user_onboarding, pk_01_passkeys), no manual steps are needed. New settings: passkey sign-in (admin → Sign-in, or HSE_STUDIO__AUTH__PASSKEYS_ENABLED; HSE_STUDIO__AUTH__PASSKEY_RP_ID for a shared parent domain of keys) and MCP (admin, off by default). If you change the server address public_url, existing passkeys stop working

## [0.3.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.2.0...v0.3.0) - 2026-11-02

- Shared server: teams can use the Studio together. Accounts and organisations, role-based project access, an installation admin area (/admin: people, sign-in and OIDC, mail, runners, queue, audit), builds on runners in isolated containers. Deploy with Docker Compose or Helm, see the Shared server section of the docs
- Collaboration: access links with a role, expiry, password and guest sign-in; invitations by e-mail or login, access requests and project ownership transfer; reviewers comment on the text and several people edit one document at the same time, seeing each other's cursors
- The Studio server as a git remote: the local Studio signs in to the server with a device code (device flow), sees the server's projects and clones and syncs them over git via HTTPS. Projects can be moved from the local Studio to the server together with their data
- Local Studio: automatic project sync with the server (on by default for projects obtained by signing in to a server, can be turned off per project) and PDF upload after a successful build, so supervisors and reviewers see the result without building
- Personal runners and AI providers: attach your own machine as a runner with a pairing code and build documents on it; the AI agent can work through your runner while your keys stay with you. Cloud builds on this machine are available right from the local Studio
- Quotas, AI gateway and runner autoscaling: limits on storage, builds per month, AI tokens per day and month and project members (installation default, organisation, user); when exhausted, choose low priority (default), reject or warn. The AI gateway records calls and fails over to another provider. The runner count can follow the queue automatically (webhook, compose or KEDA metrics); off by default
- Data autonomy: everything that grows has a retention period and background cleanup (audit 365 days, AI log 90, build logs 30 and so on; adjust them on the Data retention admin page). Audit and AI logs are split into monthly partitions, container logs are rotated, and when a disk reaches 90% a safe mode rejects large uploads while everything else keeps working
- Backups: schedule, full backup of the database, files and objects, server-side encryption, S3 or directory destinations (your own MinIO via one compose overlay), a connection test and failure alerts. Restore from the admin area with a preview, confirmation and maintenance mode, or with the hse-doc-studio backup restore command
- Self-diagnostics: the Self-diagnostics admin page checks the database, migrations, storage, disk, runners, queue, scheduler, TLS, backups and mail, explains the cause and suggests what to do; it alerts only on persistent problems. hse_diag_* metrics and a public /health/diagnostics
- Automatic server updates: release check every 6 hours, install by button or automatically in a maintenance window, backup and database snapshot first, image digest and cosign signature verification, automatic rollback if the new version does not come up. Default mode: notify only
- For administrators, upgrading: 0.2.0 was local-only, so there are no server installs on it and no database migration from 0.2.0 is needed: the server applies the whole chain on first start, from 0001 to dg_01_diagnostics (the latest being lc_02_partition_logs, bk_01_backups, up_01_server_updates, dg_01_diagnostics). Local 0.2.0 installs update with the Update button or update.sh / update.ps1 and their data is untouched. The server auto-updater installs only releases that ship an image-digest.json, i.e. 0.3.0 and later: it cannot install anything older, and when the digest is missing the run is cancelled (digest_missing) unless verification is set to None
- For administrators, environment and images: MinIO in compose is replaced with the pgsty/minio fork (web console restored, tag pinned); set S3_ACCESS_KEY and S3_SECRET_KEY, and keep SECRETS_KEY safe, since it encrypts secrets and backups. Auto-update is enabled by the updater profile: UPDATER_TOKEN in .env and docker compose --profile updater up -d (the service gets the docker socket, so it is off by default). New variables: HSE_STUDIO__SERVER_UPDATE__*, HSE_STUDIO__BACKUPS__*, HSE_STUDIO__LIFECYCLE__*, LOG_MAX_SIZE and LOG_MAX_FILE; see the variable reference for the full list. Off by default: automatic update installation (notify-only mode) and runner autoscaling; scheduled backups start working once a destination is added
- The code and tests run on Windows and macOS: fixed paths, directory permissions, encodings and network checks that broke running on those systems

## [0.2.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.3...v0.2.0) - 2026-10-26

- Master's programme: a 1st-year coursework template for System and Software Engineering — topic and application, report and slides
- Detached electronic signatures: freeze a PDF, sign it with an OpenPGP key or a qualified signature via the CryptoPro browser plug-in right in the Studio, or upload an existing signature. The Studio verifies it, adds an HSE-style signature stamp and builds the submission package
- Update a project to a new template version: project settings now have a Template version section. You see which files change before updating, your own edits are kept, conflicts are shown separately, and the update can be undone
- An available template update is flagged by a badge on Project settings, a dot in the outline, the status bar and a notification when you open the project
- A project saved by a newer Studio opens read-only, so an older version cannot accidentally damage its data
- New Topic and application document group, the academic supervisor's name fills the signature slot, and the Group field hint depends on the programme
- Dependencies and the base image updated, closing the vulnerabilities found in it

## [0.1.3](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.2...v0.1.3) - 2026-07-28

- The AI agent now works with any local model: if a model lacks tool support (e.g. phi3.5), it switches to a text protocol and keeps answering
- Agent errors are no longer lost — the failure reason shows up right in the chat
- Terminal updates: the update.sh and update.ps1 scripts run the same updater as the Update button — settings preserved, automatic rollback on failure
- Docs site polish: the banner always announces the current release; fixed the What's-new link, tab underline and buttons

## [0.1.2](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.1...v0.1.2) - 2026-07-28

- Fixed the app-error crash on the AI agent's very first reply (a duplicate router instance after a dependency update)
- The error screen now has a “Report an issue” button: it opens GitHub with the error, stack trace and version pre-filled — just add what you were doing

## [0.1.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.0...v0.1.1) - 2026-07-28

- The one-command install now also works in stock Windows PowerShell 5.1
- Install scripts speak English by default and Russian with HSE_STUDIO_LANG=ru; the docs pick the flag to match the page language
- A running local Ollama now registers itself as a provider — no more manual setup; the settings offer a one-click connect as well
- Every AI-agent tool is now translated in the tools menu: PDF reading, versions, projects, ask-the-user
- The data folder now ships with a ready-made projects directory — the project wizard suggests it right away

## 0.1.0 - 2026-07-28

- First release: a local studio for academic documents — projects from templates (thesis, coursework, Project Proposal) with every accompanying document and presentation
- One-click PDF builds: LaTeX runs inside a Docker container, nothing to install on your machine
- Code and visual editors with a built-in PDF viewer and text↔layout jumps (SyncTeX)
- GOST formatting checks: findings are anchored to source lines, many fix themselves automatically
- Submissions: the studio assembles the checkpoint package together with signatures and forms
- An AI assistant inside your project: bring your own provider (Claude, OpenAI and compatibles) or a local model via Ollama
- Project version history: timeline, diffs and restore — no git knowledge required

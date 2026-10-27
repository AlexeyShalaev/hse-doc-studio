# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.3.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.2.0...v0.3.0) (2026-10-27)


### Features

* **api:** гард прав project_access_guard рядом с гардом записи ([14e11ec](https://github.com/AlexeyShalaev/hse-doc-studio/commit/14e11ec54bbbbec0c9db9d0bb98204e660d4fcac))
* **api:** таблица действий по маршрутам проекта и тест её полноты ([2870fcf](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2870fcfacace157f5f7d03c5609807f57aaacd91))
* **api:** флаг режима StudioMode и отказ на старте в режиме server ([c3fcbfd](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c3fcbfde8d215f7ecc335b0a3307fee9efa68d3b))
* **collab:** этап 0, диспетчер задач: сборка, office, пакет сдачи, проверка подписей ([a7a55fe](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a7a55feabde9d8005e4157b9611c31fa096cf0b7))
* **collab:** этап 0, доступы: режим, core/access, гард прав, автор коммита ([e703683](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e703683f4112a790f103050bcd77336666fd4669))
* **core:** модель доступа core/access с единой политикой и актором запроса ([841802d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/841802dbb3c4fadb1c4e3c270e5fbd318fc2d9f8))
* **git-sync:** CI для сборки документов и команда hse-doc-studio build ([34bf032](https://github.com/AlexeyShalaev/hse-doc-studio/commit/34bf0323a31e0e9f0b3ea4c1b91c1efaf63c8df6))
* **git-sync:** Git-синхронизация проектов (этап 1) ([2fd6d00](https://github.com/AlexeyShalaev/hse-doc-studio/commit/2fd6d00c7319168b544c3a7af1af3795eff2f69c))
* **git-sync:** ssh-ключи доступа, свой known_hosts и подтверждение ключа сервера ([c39490d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c39490dc5b3d410a8429983c619878d5ae97bdc3))
* **git-sync:** выборка из удалённого репозитория и фоновый планировщик ([f023a4d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/f023a4d3eebea3e4e93a0652d5cb48951c4f4e25))
* **git-sync:** доступы к удаленным репозиториям: шифрование секретов, токены и ключи ssh, API доступов ([8d64320](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8d64320521153b44c125c4a6961f1cf806581992))
* **git-sync:** каталог git-провайдеров и расширение контракта (P1) ([47fec72](https://github.com/AlexeyShalaev/hse-doc-studio/commit/47fec72e0c6786dffd04946683a67f488426f096))
* **git-sync:** клонирование проекта из удалённого репозитория в новую папку ([48c38c8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/48c38c8de8d8422048c1071db50936a6f1b2821d))
* **git-sync:** обмен проектом файлом bundle: выгрузка, слияние, проект из файла ([24a4061](https://github.com/AlexeyShalaev/hse-doc-studio/commit/24a40613d4df35766c0ec256ed17f7fa95f1e427))
* **git-sync:** общий журнал для обновления шаблона и слияния синхронизации ([393e65d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/393e65d5485f78596e56ae19d0547f29afeaa423))
* **git-sync:** общий контракт синхронизации с git, коды ошибок, эталонные JSON и схемы pydantic и zod ([42bdaa4](https://github.com/AlexeyShalaev/hse-doc-studio/commit/42bdaa46c3538158c1c7c2b52bf366ce9395b35f))
* **git-sync:** определение провайдера, проверка токена и доверие к серверам со своим сертификатом (P2) ([2652125](https://github.com/AlexeyShalaev/hse-doc-studio/commit/26521256cb9c6b9fcc4639fb995daf0197123caf))
* **git-sync:** основа домена синхронизации: адрес репозитория, разбор ошибок git, состояния, порты, GitConfig ([233d7e1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/233d7e1f85ab6313504875e29a14f2c0f88679ff))
* **git-sync:** подключение проекта к удалённому репозиторию, статус синхронизации и проверка адреса ([3ed6d28](https://github.com/AlexeyShalaev/hse-doc-studio/commit/3ed6d286092bb5579e760436d00a5089655f8448))
* **git-sync:** предупреждение о синхронизируемых папках, состав публикации и папка для клонирования ([9de7c07](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9de7c079a8e77a96d7b7f62a637fd137dddee9d6))
* **git-sync:** раннер и транспорт сетевого git: токен через окружение, probe, выборка и отправка ([a68ec49](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a68ec4991aab90bdfac83c539f647397fcb14aa9))
* **git-sync:** расширения хранилища: файл состояния, чтение истории, коммит слияния, проверка чужого хранилища ([bd2793a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/bd2793a67f0d7b19c54afaee056d3bb45d5fe59d))
* **git-sync:** синхронизация проекта с удалённым репозиторием: снимок, выборка, перемотка, слияние, отправка ([9079bf8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9079bf8bf2ef98f2f10e6140dbb7a0b503093bfe))
* **git-sync:** слияние файлов состояния по полям: project.json, подписи, формы, история шаблона ([ddf47b3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ddf47b3a71fad90ee2a2f7e9b5d9045b51791a21))
* **git-sync:** стыковка настоящего бэкенда с интерфейсом, демо-стенд и сверка ответов с контрактом ([1fb84b3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1fb84b37952469450f01f4296a6a99410c4b3856))
* **git-sync:** экран конфликтов: сессия, подробности файлов, черновики, применение решений, отказ ([210ce20](https://github.com/AlexeyShalaev/hse-doc-studio/commit/210ce2023bcec413f5f8da7faa067844a2f80dbe))
* **git-sync:** ядро слияния: планировщик трех деревьев, участки текста, бинарники по новизне, безопасные пути ([93bd287](https://github.com/AlexeyShalaev/hse-doc-studio/commit/93bd28710fc4a4286d72dd6c1693f5cca827d9ea))
* **jobs:** LocalJobDispatcher с режимами compile, run и detached и реестр обработчиков ([21eee5e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/21eee5e5954a7cba767526363608c366ba5a437d))
* **jobs:** вид задачи office.convert и единая конвертация office в PDF ([90206a1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/90206a1bbb9d056c929ab0289810efb799f12560))
* **jobs:** вид задачи signature.verify_detached, провайдер доверенного материала и обработчик проверки ([fefcd07](https://github.com/AlexeyShalaev/hse-doc-studio/commit/fefcd07e77a573ca0693332afc94553ff5e176bc))
* **jobs:** встроенный раннер compile, хуки записи сборки и материализатор шаблона ([2374778](https://github.com/AlexeyShalaev/hse-doc-studio/commit/23747785b4193eaea760b72cd8be4a04577d8af7))
* **jobs:** общий словарь задач core/jobs и ошибки сборки в core ([5b149f6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5b149f6b009849c436e039f511c5d3070c3487ba))
* **jobs:** типы задачи pack.submission в core/jobs ([6245427](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6245427ad6c0a6e92e42dce8159e878bf6ff1588))
* **profile:** профиль автора коммитов, подпись берется из него, а не у служебного бота ([71a2ac4](https://github.com/AlexeyShalaev/hse-doc-studio/commit/71a2ac433d665a56de88b9d7ba0ef0818dfe2749))
* **submission:** PackExecutor и PackHandler исполняют план pack.submission ([51ab2ec](https://github.com/AlexeyShalaev/hse-doc-studio/commit/51ab2ecdc95dc629e4058100784045ee1096a895))
* **submission:** PackPlanner собирает нагрузку pack.submission из проекта ([3479302](https://github.com/AlexeyShalaev/hse-doc-studio/commit/347930212fd90d7b31a9d24b9f1197dd8d527187))
* **vcs:** фильтры, фасеты и метки синхронизации в истории версий ([5cde0a7](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5cde0a70b95f85178222cb546d98f2031baf247b))
* **vcs:** шов автора коммита ICommitAuthorProvider со служебной подписью по умолчанию ([e611951](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e611951df17221ab9072040f5e3957c05c2cdf59))
* **web-app:** вход в синхронизацию с git: кнопка в заголовке, панель состояния, сегмент строки состояния, бейдж рейки и баннер конфликтов ([ca3a782](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ca3a782e52300fa514cbafe3a896260188e26946))
* **web-app:** выпуск токена по ссылке, тип сервера и проверка токена при вставке (P3) ([458a8c8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/458a8c81d15419c4f1053026ba42cb16b4327c2b))
* **web-app:** галерея состояний синхронизации /dev/sync-states для просмотра без сервера git ([bfd8fd5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/bfd8fd59aab7747cbd1674afce6fc0337ee20c72))
* **web-app:** демо отдаёт различия чужих версий из репозитория ([423b5b3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/423b5b3e0d7ccc6140557d97ec8f6ded0e8a31c1))
* **web-app:** запросы синхронизации с git, демо-транспорт и профиль автора в сущностях ([eadf345](https://github.com/AlexeyShalaev/hse-doc-studio/commit/eadf345a223fbde05ba07ab5f0eb34beae23e4f4))
* **web-app:** история с фильтрами по виду, автору и отправке, метки синхронизации в ленте, панель синхронизации на странице версий ([9761f42](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9761f4211c6e0647c6c621be8d57d1aaf43fdd95))
* **web-app:** мастер «Клонировать проект из git»: источник, папка, загрузка и точки входа ([929bfbb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/929bfbb6c20c4c0a5657766a7ea283dfee6db44c))
* **web-app:** настройки синхронизации в проекте и раздел «Доступ к репозиториям» в настройках приложения ([534c1dd](https://github.com/AlexeyShalaev/hse-doc-studio/commit/534c1dde46d7b28b4dedea3449a7a0f0714b64d2))
* **web-app:** обмен файлом без сервера и настройка автосборки: окна выгрузки, загрузки и CI ([71d5df2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/71d5df2bbe51cd663ec5a17d3c67704bc7540f07))
* **web-app:** общие примитивы интерфейса для git-синхронизации ([24fbd7d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/24fbd7db0fe54aceb9434bcacfe2eac36e3cb027))
* **web-app:** окно подключения репозитория: адрес, доступ, проверка, ключ сервера и обновление доступа ([23859c0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/23859c01a86e0066e671274628d20f9ef557f6aa))
* **web-app:** профиль автора версий: форма, раздел настроек и окно «Представься» ([4175c64](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4175c64e2890be408f0423e1e1bb1e29c51399d3))
* **web-app:** разбор остальных видов конфликтов синхронизации: поля формы, картинки, удаление против правки, подписи, предупреждения ([e18f596](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e18f596d487b5dd1a5693accb21b4a00bd798f28))
* **web-app:** смена сертификата сервера с двумя отпечатками, серверы со сроками токенов и галерея доступа к git (P3c) ([d89fc01](https://github.com/AlexeyShalaev/hse-doc-studio/commit/d89fc01e26bcae5b78105bfed8b2599e2e3309d4))
* **web-app:** способы доступа вкладками, deploy-ключ репозитория и публичный репозиторий без токена (P3b) ([23ca9f1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/23ca9f1f0c6ac7065975e6c20789f549114d3e2d))
* **web-app:** экран разбора конфликтов синхронизации: список файлов, выбор по частям, итог, ручная правка, завершение и отмена ([4150b1e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4150b1e10bda89054aff5de25069e14ab8fd22cf))


### Bug Fixes

* **access:** читатель не видит промежуточные файлы сборки, проверка OpenPGP не читает сертификаты ([222a4a6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/222a4a6145db362fa44b7a5adc813a3e970b48c0))
* **api:** 422 на маршрутах git не возвращает тело запроса ([ae8ef66](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ae8ef660f9fdb9fd637c46318025d78ea38958cc))
* **api:** uv.lock синхронизирован с pyproject (hypothesis, версия 0.2.0) ([ad68996](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ad6899665cb726565550995369ab73aa477c758e))
* **api:** журнал сервера без локальных переменных в трассировках ([537f790](https://github.com/AlexeyShalaev/hse-doc-studio/commit/537f790ceeb41f524be99efca3e6a752738be8ef))
* **api:** журнал сервера снова в местном времени и без escape-кодов вне терминала ([5fac780](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5fac780de2bd25bf9cac71ab77268787f45e5742))
* **api:** исключения гарда записи сверяются по шаблону маршрута ([3f9d6e7](https://github.com/AlexeyShalaev/hse-doc-studio/commit/3f9d6e78364b728588c0f0b5fa6f6048f1c4258d))
* **files:** записи файлов проекта идут под блокировкой папки, которую держит применение синхронизации ([d063f85](https://github.com/AlexeyShalaev/hse-doc-studio/commit/d063f8570220665196142c119d9a020c5e5bf540))
* **git-sync:** 401 от проверки токена GitLab больше не считается отказом токена ([751e8e2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/751e8e25e25fcd773a705807f7375b8991ba5d97))
* **git-sync:** GIT_SSL_CAINFO из окружения не перекрывает CA сервера из Студии ([3a008a0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/3a008a0e1445420212c5d4fcd495419e0e2638d3))
* **git-sync:** http-корень API из настроек хоста не используется без согласия на http ([13fd2c9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/13fd2c95923ceb383bd3d527081b4acbba795831))
* **git-sync:** адрес без .git получает суффикс при работе с токеном, чтобы GitLab не отвечал редиректом ([cc14eec](https://github.com/AlexeyShalaev/hse-doc-studio/commit/cc14eec779f3a06f7fcc1e3f6c94264b19e3dacd))
* **git-sync:** адрес с символами, которые nameprep подменяет, отвергается ([c9d5381](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c9d5381128bd3bc71214ede74bee06628633b332))
* **git-sync:** выборки сериализованы с отключением, переносом и синхронизацией, просьбы присоединяются к идущей ([87d3d53](https://github.com/AlexeyShalaev/hse-doc-studio/commit/87d3d5393ecacc10c46d9b7b0401cdb6074a2b59))
* **git-sync:** выключенная настройкой синхронизация отвечает своим кодом и не копит доступы ([13cadf9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/13cadf92078389716a1a26d7e05ba3abbee479c9))
* **git-sync:** глубоко вложенный JSON из чужой ветки не роняет синхронизацию ([31758e3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/31758e318cf1444170bebcba621472fb58d6b7f0))
* **git-sync:** детектор общих папок подключён к статусу проекта и к состоянию секретов ([ad9c035](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ad9c0351566ae4261386f07caaec055c86b6cd3e))
* **git-sync:** запись CI-файла идёт под замком папки проекта ([1a6685c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1a6685cd220224060bedc13551f977605a7fefca))
* **git-sync:** имя с двоеточием принимается там, где файловая система его допускает ([1075f04](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1075f04a0e705a9af39f6003288aeb146e9b3731))
* **git-sync:** клонирование отказывает, если имена в дереве слились бы на файловой системе ([47f06d2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/47f06d2df2dc5f4e31342230b9036674b5c92c5e))
* **git-sync:** не следовать редиректам, пока git работает с токеном ([dc1bbe0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/dc1bbe048fc43df919673c84d23edc65e93eefb6))
* **git-sync:** неизвестный центр сертификата распознаётся и у git из образа Студии ([1e2535e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1e2535ec6a8cac21fe02a0b9435ced52680d69d9))
* **git-sync:** обрыв ответа прокси на CONNECT даёт offline, а не необработанное исключение ([5ab6705](https://github.com/AlexeyShalaev/hse-doc-studio/commit/5ab67053f45d52e50fb815145089f093c7ab5f52))
* **git-sync:** определение провайдера не запоминает сбои надолго и держит кэш в пределах ([78099c5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/78099c5a964b54346128b55b7b669f4ef545b255))
* **git-sync:** открытая из готовой папки связь с репозиторием сразу попадает в фоновую выборку ([596c69c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/596c69c476dc116446b6b95a0e6437fe8ba215f8))
* **git-sync:** отправка, дошедшая до сервера, больше не отменяется ([8f61ca2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8f61ca282b945fb6522b7a30f853aacd144765df))
* **git-sync:** параллельные клонирования не удаляют и не дублируют друг друга ([8f71bd5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8f71bd510328e9ca6fa49129d8777896872de195))
* **git-sync:** предел размера и общий срок для ответов API хостинга ([6bd5d40](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6bd5d40c6ea896e84b9f06ad496b32da139ec8d3))
* **git-sync:** проверка адреса и клонирование по открытому http берут согласие человека ([c382ca8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c382ca8bbd3b25e7170c5a71b989aaf547da46fb))
* **git-sync:** пропущенные как небезопасные чужие записи переносятся в дерево слияния ([8312155](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8312155be1428b0570e473240c2633e062153156))
* **git-sync:** процент операции не откатывается назад внутри фазы ([12b5e72](https://github.com/AlexeyShalaev/hse-doc-studio/commit/12b5e724941343c62c7817775f6d564c7de13fbc))
* **git-sync:** размер файлов чужой ветки ограничен до чтения и записи ([6d3d016](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6d3d016916a05db1d127135eff15ffb2c6f86c23))
* **git-sync:** сбой тика фоновой выборки пишется в журнал ([428ff87](https://github.com/AlexeyShalaev/hse-doc-studio/commit/428ff87ff6fde690e503d154a8652e4065953c60))
* **git-sync:** сбой чтения файла хранилища больше не считается порчей ([8ed8a55](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8ed8a55cf889257c7c900d1f73b01083ce2d0979))
* **git-sync:** сертификат сервера читается через прокси из окружения, как это делает git ([3c59027](https://github.com/AlexeyShalaev/hse-doc-studio/commit/3c5902795fad0fc4189b9ba3f28f36038bbaaccf))
* **git-sync:** сквозная сверка бэкенда: подпись тегов, отмена клонирования, секции DI ([7674a9d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7674a9d60792f430060f834abd0f977b42001112))
* **git-sync:** создание первого ключа шифрования не затирает ключ другого процесса ([1bed4d5](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1bed4d586bc27eb45d47b95774718612de5acace))
* **git-sync:** состояние синхронизации сбрасывается после коммита слияния, а не до него ([135ff42](https://github.com/AlexeyShalaev/hse-doc-studio/commit/135ff42c5599714c6c1033fcfe7b579e3481c800))
* **git-sync:** статус и проверка адреса отдают provider_info и token_info по контракту P1 ([e1076a3](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e1076a3033e37f6eed56bc5fd6b97a21b5841df0))
* **git-sync:** тест зависшего ssh не гонится с запуском поддельного ssh ([6bd1fc6](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6bd1fc6d295e9034ae5fb2408a54c14df036c76b))
* **git-sync:** тик расписания убирает из реестра проект без подключения, когда ему пора на выборку ([cfe115e](https://github.com/AlexeyShalaev/hse-doc-studio/commit/cfe115e70dd61d43c98c17132a504bd8e5496b4b))
* **git-sync:** упаковка переносного файла больше не держит блокировку папки ([21054cb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/21054cb5d3d0f54ec453e4a628f630df4a3cd4c1))
* **git-sync:** успешная проверка токена снимает с доступа отметку auth_failed ([ec29399](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ec293990c2edee888cc07f9ce148e4d936d14a82))
* **git-sync:** файл и папка с одним именем останавливают слияние понятной ошибкой без мусора на диске ([4e05b06](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4e05b065c2177a2ad7ccf99ae42281ebeac746fd))
* **git-sync:** чужой project.json, который Студия не откроет, отвергается до записи на диск ([8926c71](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8926c7144957a27577729f9789a55000fb1ef219))
* **image:** apt-get upgrade в production-образе (CVE-2026-84782 openssl) ([9e733b1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/9e733b1b4cf5e288d890c15c69d255057a83344f))
* **image:** apt-get upgrade в production-образе закрывает свежие CVE openssl до обновления базового образа ([c232409](https://github.com/AlexeyShalaev/hse-doc-studio/commit/c232409d0da865a4ea022932a7d293006e1a4c2f))
* **jobs:** сборка пакета видна проверкам переноса и обновления, превью office не роняет сборку ([074fb1a](https://github.com/AlexeyShalaev/hse-doc-studio/commit/074fb1a4784c5ce14ca6b566014436c80435d2f2))
* **settings:** загрузка файла переноса проверяет числовые настройки так же, как PUT /settings ([179f6b7](https://github.com/AlexeyShalaev/hse-doc-studio/commit/179f6b73c896c95ece9f74079de2dfc215e75518))
* **submission:** пакет не уносит файлы по ссылкам наружу, замороженные записи не теряются молча ([d593964](https://github.com/AlexeyShalaev/hse-doc-studio/commit/d593964ec8239d713f30c5c4c9819b29a8fa8470))
* **template-update:** переименование файла только в регистре букв при том же содержимом больше не стирает файл ([ebcbdc9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ebcbdc991e7a874f4958bfe342de002f4c50606c))
* **template-update:** удаления применяются раньше записей, переименование по регистру не стирает файл ([715f1ef](https://github.com/AlexeyShalaev/hse-doc-studio/commit/715f1ef0879b2235e8deaa045caa4740064943db))
* **vcs:** .gitattributes из рабочей папки не влияет на снимки проекта ([75b3bfb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/75b3bfb3eb7dec3aa2f7e7a74a5915d986af52f3))
* **vcs:** git над хранилищем проекта не доверяет чужому конфигу и окружению, детали слияния показывают файлы ([6a79f44](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6a79f44258f8d3e713f16f138a7817d248f9b6c7))
* **vcs:** в тексте ошибки git-команды нет разделителя -- ([50dc924](https://github.com/AlexeyShalaev/hse-doc-studio/commit/50dc9246ce188a8d13c66cff6820bdd00ffeaba0))
* **web-app:** демо-адаптер отдаёт обработчику разобранный JSON при forward ([8adc3fe](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8adc3fe6fc2937ef81e246785ffc5bf04d3c0a78))
* **web-app:** закрывать окно «Обмен файлом» при уходе из импорта ([ed9a6f8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ed9a6f89da52665be8bb4bcf75605c6fcf6309de))
* **web-app:** окна «Представься» и «Обмен файлом» подключены к оболочке приложения ([7128de9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7128de9a936e9533e82befe13ba505a67f088369))

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

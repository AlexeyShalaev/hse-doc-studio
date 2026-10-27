"""Провайдер identity серверного режима.

Каркас: срезы identity регистрируют здесь репозитории пользователей и сессий, цепочку резолверов
актора, почтовик и ограничитель. Подключается лениво, только из ``create_container(server)``.
"""

from __future__ import annotations

from dishka import Provider, Scope


class ServerIdentityProvider(Provider):
    scope = Scope.APP

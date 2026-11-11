"""Правила «Диска»: что из Docker принадлежит Студии, что считается старым и что разрешено удалить.

Один код для локальной Студии (Настройки, «Диск») и для раннера (диск раннера в админке,
docs/design/storage-cleanup.md, S1 и S2). Здесь нет ни настроек api, ни хранилища настроек:
каждый процесс собирает `DockerDiskPlanner` из своей конфигурации. Docker вызывает только
реализация порта `DockerDiskProbe` (`infra/docker/system_manager.py`), шаги выполняет
`DockerCleanupJobManager` (`infra/docker/cleanup_jobs.py`).
"""

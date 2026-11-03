"""Журнал исполнителя kubernetes: файл на томе пода (как у compose) плюс копия состояния в аннотациях Deployment.

Файл держит очередь событий, которые не дошли до api (он гасится на время обновления). Поду апдейтера в Kubernetes
не на что положиться: emptyDir умирает вместе с подом, а PVC в чарте нет, поэтому запуск и последний успешный
дублируются в аннотациях Deployment api (права patch на него и так нужны). Новый под по ним понимает, на каком
шаге остановился предшественник, и доводит откат.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.update.server_updater import kube_plan
from hse_doc_studio.infra.update.server_updater.journal import Journal
from hse_doc_studio.infra.update.server_updater.kube import MERGE, IKube

log = logging.getLogger("hse-updater")


class KubeJournal(Journal):
    def __init__(self, path: Path, kube: IKube) -> None:
        super().__init__(path)
        self._kube = kube
        self._mirrored: str | None = None

    def adopt(self, deployment: dict[str, Any]) -> None:
        """Старт пода: файла нет (под пересоздан), берём состояние из аннотаций."""
        run = kube_plan.read_annotation(deployment, kube_plan.ANNOTATION_RUN)
        last_ok = kube_plan.read_annotation(deployment, kube_plan.ANNOTATION_LAST_OK)
        if self.data["run"] is None and run is not None:
            self.data["run"] = run
        if self.data.get("last_ok") is None and last_ok is not None:
            self.data["last_ok"] = last_ok
        self._mirrored = json.dumps([run, last_ok], sort_keys=True)
        self.save()

    def save(self) -> None:
        super().save()
        self.mirror()

    def mirror(self, *, strict: bool = False) -> None:
        """Копирует запуск и последний успешный в аннотации; без изменений ничего не шлёт. Сбой не роняет запуск:
        файл на томе остаётся основным, а `strict` проверяет доступность записи до начала работ."""
        state = [self.data["run"], self.data.get("last_ok")]
        text = json.dumps(state, sort_keys=True)
        if text == self._mirrored:
            return
        try:
            self._kube.patch_deployment(kube_plan.journal_patch(*state), content_type=MERGE)
        except KubeApiError as exc:
            if strict:
                raise
            log.warning("cannot mirror the run journal into the deployment annotations: %s", exc)
            return
        self._mirrored = text

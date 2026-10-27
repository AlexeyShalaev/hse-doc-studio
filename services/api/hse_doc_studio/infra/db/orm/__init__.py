"""ORM-модели. Каждая зона держит свои таблицы в своём модуле и импортирует их здесь для autogenerate."""

from hse_doc_studio.infra.db.orm.instance_meta import InstanceMetaRow

__all__ = ["InstanceMetaRow"]

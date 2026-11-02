"""Из рендера runner-kubernetes.yaml оставляет ServiceAccount, Role, RoleBinding и NetworkPolicy (джоба CI на kind).

Использование: k8s_runner_rbac.py <рендер> <namespace релиза>; объекты без namespace получают namespace релиза.
"""

import sys

import yaml

_KINDS = ("ServiceAccount", "Role", "RoleBinding", "NetworkPolicy")


def main() -> None:
    path, namespace = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as fh:
        docs = [doc for doc in yaml.safe_load_all(fh) if doc and doc["kind"] in _KINDS]
    for doc in docs:
        doc["metadata"].setdefault("namespace", namespace)
    sys.stdout.write(yaml.safe_dump_all(docs))


if __name__ == "__main__":
    main()

from __future__ import annotations

from hse_doc_studio.core.value_objects import RequirementsFormat
from hse_doc_studio.use_cases.requirements.get_requirements import GetRequirementsOutput, RequirementEntry


def _matrix(fmt: RequirementsFormat, *, overridden: bool = False) -> GetRequirementsOutput:
    return GetRequirementsOutput(
        items=[
            RequirementEntry(id="R-01", title="t", source="tz", referenced_in=["vkr"], status="ok"),
            RequirementEntry(id="R-02", title="t2", source="tz", referenced_in=[], status="warn"),
        ],
        requirements_format=fmt,
        overridden=overridden,
    )

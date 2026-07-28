from fastapi import APIRouter

from hse_doc_studio.api.routers.v1 import (
    agent_personas,
    ai_providers,
    ai_runtime,
    catalog,
    changelog,
    chat,
    checks,
    compile,
    docker_system,
    documents,
    export_import,
    files,
    fonts,
    forms,
    fs,
    hse_persons,
    images,
    languagetool,
    office_editor,
    office_services,
    projects,
    requirements,
    settings,
    setup,
    signatures,
    signing_identities,
    submission,
    synctex,
    system,
    vcs,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(catalog.router, tags=["catalog"])
api_router.include_router(projects.router, tags=["projects"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(compile.router, tags=["compile"])
api_router.include_router(images.router, tags=["images"])
api_router.include_router(languagetool.router, tags=["languagetool"])
api_router.include_router(office_editor.router, tags=["office-editor"])
api_router.include_router(office_services.router, tags=["office-services"])
api_router.include_router(signatures.router, tags=["signatures"])
api_router.include_router(forms.router, tags=["forms"])
api_router.include_router(submission.router, tags=["submission"])
api_router.include_router(changelog.router, tags=["changelog"])
api_router.include_router(vcs.router, tags=["vcs"])
api_router.include_router(files.router, tags=["files"])
api_router.include_router(fonts.router, tags=["fonts"])
api_router.include_router(fs.router, tags=["fs"])
api_router.include_router(requirements.router, tags=["requirements"])
api_router.include_router(hse_persons.router, tags=["hse-persons"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(system.router, tags=["system"])
api_router.include_router(setup.router, tags=["setup"])
api_router.include_router(docker_system.router, tags=["system"])
api_router.include_router(checks.router, tags=["checks"])
api_router.include_router(synctex.router, tags=["synctex"])
api_router.include_router(ai_providers.router, tags=["ai-providers"])
api_router.include_router(agent_personas.router, tags=["agent-personas"])
api_router.include_router(ai_runtime.router, tags=["ai-runtime"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(export_import.router, tags=["data"])
api_router.include_router(signing_identities.router, tags=["signing-identities"])

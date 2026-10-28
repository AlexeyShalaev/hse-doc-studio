from hse_doc_studio.api.entrypoint import CORS_EXPOSE_HEADERS


def test_retry_after_is_readable_cross_origin() -> None:
    # Форма входа читает Retry-After из ответа 429; без expose_headers браузер его скрывает.
    assert "Retry-After" in CORS_EXPOSE_HEADERS
    assert "Content-Disposition" in CORS_EXPOSE_HEADERS

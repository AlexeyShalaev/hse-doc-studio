"""TCP-проброс к minio:9000 без разбора HTTP: заголовок Host доходит до MinIO как есть, подпись v4 сходится.

Играет роль шлюза, который администратор ставит перед хранилищем (Gateway или Ingress с TLS на проде).
"""

import asyncio


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    print("connection accepted", flush=True)
    upstream_reader, upstream_writer = await asyncio.open_connection("minio", 9000)
    await asyncio.gather(pipe(client_reader, upstream_writer), pipe(upstream_reader, client_writer))


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 9000)
    async with server:
        await server.serve_forever()


asyncio.run(main())

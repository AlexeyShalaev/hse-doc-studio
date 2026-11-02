"""`python -m hse_doc_studio.infra.update.server_updater`: сервис-апдейтер серверной установки."""

import sys

from hse_doc_studio.infra.update.server_updater.service import main

sys.exit(main())

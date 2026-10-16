"""Log estruturado para o Cloud Run (16/10/2026).

O Cloud Run so' reconhece `severity` quando a linha de stdout e' um JSON com esse campo;
`print` e `logging.basicConfig(format=...)` saem como DEFAULT, e o monitor de erros de
producao (filtro severity>=ERROR) nao os enxerga. `setup()` e' idempotente e tambem
religa os loggers do uvicorn, cujos handlers proprios ignoram o root.
"""
import json
import logging
import os
import sys

_NIVEIS = {"WARNING": "WARNING", "ERROR": "ERROR", "CRITICAL": "CRITICAL", "DEBUG": "DEBUG"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        return json.dumps(
            {
                "severity": _NIVEIS.get(record.levelname, "INFO"),
                "message": msg,
                "logger": record.name,
            },
            ensure_ascii=False,
        )


def setup() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    for nome in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(nome)
        lg.handlers.clear()
        lg.propagate = True

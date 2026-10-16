"""GET /health com commit_sha e log estruturado com severity (16/10/2026).

Hermetico: o monitor de erros de producao filtra `severity>=ERROR` no Cloud Logging, entao
um ERROR precisa sair como JSON com `severity` no stdout, inclusive os do uvicorn.
"""
import json
import logging
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api  # noqa: E402
from core import log_json  # noqa: E402


def test_health_publico_devolve_commit_sha(monkeypatch):
    monkeypatch.setattr(api, "COMMIT_SHA", "abc1234")
    r = TestClient(api.app).get("/health")
    assert r.status_code == 200
    assert r.json()["commit_sha"] == "abc1234" and r.json()["status"] == "ok"


def test_error_sai_como_json_com_severity(capsys):
    log_json.setup()
    log = logging.getLogger("monitoria.teste")
    log.info("informativo")
    try:
        raise ValueError("boom")
    except ValueError:
        log.error("falha ao processar", exc_info=True)
    linhas = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    por_nivel = {x["severity"]: x["message"] for x in linhas}
    assert "informativo" in por_nivel["INFO"]
    assert "falha ao processar" in por_nivel["ERROR"] and "ValueError: boom" in por_nivel["ERROR"]


def test_uvicorn_propaga_para_o_json(capsys):
    log_json.setup()
    logging.getLogger("uvicorn.error").error("Exception in ASGI application")
    saida = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert saida and saida[-1]["severity"] == "ERROR"

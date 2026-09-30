"""Caminhos de upload (Pub/Sub e reserva in-process) e boot sem Transcriber (30/09/2026).

Hermetico: sem Firestore, GCS, Pub/Sub, Whisper ou LLM reais. O Whisper continua
sendo o caminho de reserva (worker indisponivel ou audio > 50MB); o que mudou e' que
o Transcriber so' e' construido no primeiro uso, nao no startup.
"""
import io
import json
import os
import sys
import types

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api  # noqa: E402


class FakeDb:
    def __init__(self):
        self.linhas = {}

    def create(self, call_id, dados):
        self.linhas[call_id] = dict(dados)

    def update(self, call_id, dados):
        self.linhas.setdefault(call_id, {}).update(dados)


class FakeBlob:
    def upload_from_filename(self, _):
        pass


class FakeGcsClient:
    def bucket(self, _):
        return types.SimpleNamespace(blob=lambda _p: FakeBlob())


class FakePublisher:
    publicados = []

    def topic_path(self, projeto, topico):
        return f"projects/{projeto}/topics/{topico}"

    def publish(self, topico, dados):
        FakePublisher.publicados.append((topico, json.loads(dados)))
        return types.SimpleNamespace(result=lambda timeout=None: "msg-1")


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    db = FakeDb()
    FakePublisher.publicados = []
    monkeypatch.setattr(api, "get_db", lambda: db)
    monkeypatch.setattr(api, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(api, "_probe_audio_duration", lambda _p: 1.0)
    monkeypatch.setattr("google.cloud.storage.Client", lambda *a, **k: FakeGcsClient())
    monkeypatch.setattr("google.cloud.pubsub_v1.PublisherClient", lambda *a, **k: FakePublisher())
    api.app.dependency_overrides[api.get_current_user] = lambda: {"sub": "u1", "email": "u@example.com"}
    yield db
    api.app.dependency_overrides.clear()


def _enviar(cliente):
    return cliente.post("/api/upload", files={"file": ("chamada.wav", io.BytesIO(b"RIFF" + b"0" * 64), "audio/wav")})


def test_upload_com_worker_saudavel_vai_para_a_fila_pubsub(ambiente, monkeypatch):
    monkeypatch.setattr(api, "_worker_healthy", lambda: True)
    r = _enviar(TestClient(api.app))
    assert r.status_code == 200 and r.json()["mode"] == "pubsub"
    (topico, msg), = FakePublisher.publicados
    assert topico.endswith("monitoria-whisper-jobs") and msg["call_id"] == r.json()["id"]
    assert ambiente.linhas[r.json()["id"]]["status"] == "Na Fila de Processamento..."


def test_upload_com_worker_fora_usa_o_whisper_in_process_com_transcriber_duble(ambiente, monkeypatch):
    monkeypatch.setattr(api, "_worker_healthy", lambda: False)
    chamadas = []

    class TranscriberDuble:
        def transcribe(self, caminho, on_progress=None, audio_duration_sec=None):
            chamadas.append(caminho)
            return "ola", [{"start": 0.0, "end": 1.0, "text": "ola"}]

    class AvaliadorDuble:
        client = types.SimpleNamespace(last_provider_used="duble")

        def diarize(self, texto):
            return f"[A] {texto}"

        def evaluate(self, texto, **kwargs):
            return {"nota_geral": 80}

    monkeypatch.setattr(api, "get_transcriber", lambda: TranscriberDuble())
    monkeypatch.setattr(api, "get_evaluator", lambda: AvaliadorDuble())
    monkeypatch.setattr(api, "get_user_settings", lambda _u: {})
    monkeypatch.setattr(api, "get_call", lambda _c: {"audio_duration_sec": 1.0})

    r = _enviar(TestClient(api.app))  # a BackgroundTask roda antes de o TestClient devolver
    assert r.status_code == 200 and r.json()["mode"] == "local" and r.json()["reason"] == "worker_unhealthy"
    assert FakePublisher.publicados == [] and len(chamadas) == 1
    linha = ambiente.linhas[r.json()["id"]]
    assert linha["status"] == "Concluído" and linha["nota"] == 80


def test_startup_nao_constroi_o_transcriber(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("Transcriber construido no startup")

    monkeypatch.setattr(api, "Transcriber", proibido)
    monkeypatch.setattr(api, "transcriber", None)
    with TestClient(api.app):
        assert api.transcriber is None
    with pytest.raises(AssertionError):  # no primeiro uso, sim
        api.get_transcriber()


def test_assets_com_hash_ganham_cache_imutavel_e_gzip_e_index_continua_sem_cache():
    from fastapi.responses import Response as R

    api.app.add_api_route("/assets/teste-abc123.js", lambda: R("var a=1;" * 500, media_type="application/javascript"))
    rota = api.app.router.routes.pop()
    api.app.router.routes.insert(0, rota)  # antes do mount de /assets, que so' existe com o dist construido
    try:
        c = TestClient(api.app)
        r = c.get("/assets/teste-abc123.js", headers={"Accept-Encoding": "gzip"})
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert r.headers["content-encoding"] == "gzip"
        assert "immutable" not in c.get("/").headers.get("cache-control", "")
    finally:
        api.app.router.routes.remove(rota)

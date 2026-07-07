"""
core/masker.py - Utilidade de mascaramento de PII (LGPD Art. 46)

Mascara automaticamente dados pessoais antes de:
  1. Armazenar no Firestore (campo transcricao, transcricao_diarizada)
  2. Enviar prompts para LLM (MiniMax M3)

Padroes detectados:
  - CPF: 000.000.000-00
  - Telefone: (XX) XXXX-XXXX ou (XX) XXXXX-XXXX
  - Email: usuario@dominio.com
  - RG: XX.XXX.XXX-X (heuristica basica)

Uso:
  from core.masker import mask_pii
  texto_limpo = mask_pii(transcricao_raw)
"""

import re

_CPF_RE = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
_PHONE_RE = re.compile(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_RG_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}-\d{1}")

_CPF_MASK = "***.***.***-**"
_PHONE_MASK = "(**) ****-****"
_EMAIL_MASK = "****@****.***"
_RG_MASK = "**.***.***-*"


def mask_pii(text: str) -> str:
    if not text:
        return text

    text = _CPF_RE.sub(_CPF_MASK, text)
    text = _PHONE_RE.sub(_PHONE_MASK, text)
    text = _EMAIL_RE.sub(_EMAIL_MASK, text)
    text = _RG_RE.sub(_RG_MASK, text)
    return text


def has_pii(text: str) -> bool:
    if not text:
        return False
    return bool(
        _CPF_RE.search(text)
        or _PHONE_RE.search(text)
        or _EMAIL_RE.search(text)
        or _RG_RE.search(text)
    )

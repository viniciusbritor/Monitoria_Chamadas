import os
import sys
import time
import requests
import json
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secrets_manager


class DeepSeekClient:
    """DeepSeek V4 Flash — API direta (api.deepseek.com). OpenAI-compatible.

    Docs: https://api-docs.deepseek.com
    Model: deepseek-v4-flash (fast, cheap, 1M context, JSON mode nativo)
    Base URL: https://api.deepseek.com (sem /v1)
    JSON mode: response_format={"type":"json_object"} + palavra "json" no prompt
    Thinking: desabilitado para tarefas deterministicas (JSON/diarize)
    """

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            self.api_key = secrets_manager.get_secret("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com"
        self.model = "deepseek-v4-flash"
        self.enabled = bool(self.api_key)

    def _execute(self, payload, max_retries=3):
        if not self.enabled:
            raise Exception("[DeepSeek] DEEPSEEK_API_KEY nao configurada")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        retries = 0
        base_delay = 1

        while retries <= max_retries:
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 429:
                    retries += 1
                    if retries > max_retries:
                        raise Exception(f"[DeepSeek] Max retries atingido (429)")
                    sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                    print(f"[DeepSeek] 429 rate limit. Aguardando {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue
                if resp.status_code == 402:
                    raise Exception(f"[DeepSeek] Quota/credito insuficiente: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
                return None
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > max_retries:
                    raise Exception(f"[DeepSeek] Erro apos {max_retries} retries: {e}")
                sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                print(f"[DeepSeek] Erro {e}. Retry {retries}/{max_retries} em {sleep_time:.2f}s...")
                time.sleep(sleep_time)

    def chat(self, system_prompt, user_prompt, json_mode=False,
             temperature=None, max_tokens=None):
        if temperature is None:
            temperature = 0.3 if json_mode else 0.1
        if max_tokens is None:
            max_tokens = 1500 if json_mode else 2000

        sp = system_prompt
        if json_mode and "json" not in sp.lower():
            sp = "JSON: " + sp

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "messages": [
                {"role": "system", "content": sp},
                {"role": "user", "content": user_prompt},
            ],
            "thinking": {"type": "disabled"},
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return self._execute(payload)


class NvidiaNimClient:
    """DeepSeek V4 Flash via NVIDIA NIM — fallback se DEEPSEEK_API_KEY ausente.

    Model: deepseek-ai/deepseek-v4-flash
    Base URL: https://integrate.api.nvidia.com/v1
    """

    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY", "")
        if not self.api_key:
            self.api_key = secrets_manager.get_secret("NVIDIA_API_KEY")
        self.base_url = "https://integrate.api.nvidia.com/v1"
        self.model = "deepseek-ai/deepseek-v4-flash"
        self.enabled = bool(self.api_key)

    def _execute(self, payload, max_retries=3):
        if not self.enabled:
            raise Exception("[NVIDIA] NVIDIA_API_KEY nao configurada")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        retries = 0
        base_delay = 1

        while retries <= max_retries:
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 429:
                    retries += 1
                    if retries > max_retries:
                        raise Exception(f"[NVIDIA] Max retries atingido (429)")
                    sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                    print(f"[NVIDIA] 429 rate limit. Aguardando {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue
                if resp.status_code == 402:
                    raise Exception(f"[NVIDIA] Quota/credito insuficiente: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
                return None
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > max_retries:
                    raise Exception(f"[NVIDIA] Erro apos {max_retries} retries: {e}")
                sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                print(f"[NVIDIA] Erro {e}. Retry {retries}/{max_retries} em {sleep_time:.2f}s...")
                time.sleep(sleep_time)

    def chat(self, system_prompt, user_prompt, json_mode=False,
             temperature=None, max_tokens=None):
        if temperature is None:
            temperature = 0.3 if json_mode else 0.1
        if max_tokens is None:
            max_tokens = 1500 if json_mode else 2000

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return self._execute(payload)


class MiniMaxClient:
    """MiniMax M3 — API proprietaria chatcompletion_v2 (ultimo fallback)."""

    def __init__(self):
        self.api_key = secrets_manager.get_secret("MINIMAX_API_KEY")
        self.base_url = "https://api.minimax.io/v1/text/chatcompletion_v2"
        self.model = "MiniMax-M3"
        self.enabled = bool(self.api_key)

    def _execute(self, payload, max_retries=3):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        retries = 0
        base_delay = 2

        while retries <= max_retries:
            try:
                resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
                if resp.status_code == 429:
                    retries += 1
                    if retries > max_retries:
                        raise Exception(f"[MiniMax] Max retries atingido (429)")
                    sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                    print(f"[MiniMax] 429 rate limit. Aguardando {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue
                resp.raise_for_status()
                data = resp.json()
                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    msg = base_resp.get("status_msg", "Erro desconhecido")
                    raise Exception(f"API Error: {msg}")
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
                return None
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > max_retries:
                    raise Exception(f"[MiniMax] Erro apos {max_retries} retries: {e}")
                sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                print(f"[MiniMax] Erro {e}. Retry {retries}/{max_retries} em {sleep_time:.2f}s...")
                time.sleep(sleep_time)

    def chat(self, system_prompt, user_prompt, json_mode=False,
             temperature=None, max_tokens=None):
        if temperature is None:
            temperature = 0.3 if json_mode else 0.1
        if max_tokens is None:
            max_tokens = 1500 if json_mode else 400

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if json_mode:
            payload["reply_constraints"] = {
                "sender_type": "BOT",
                "sender_name": "Assistente",
            }

        return self._execute(payload)


class LLMClient:
    """Multi-provider cascata: DeepSeek direto -> NVIDIA NIM -> MiniMax M3.

    Mantem a mesma interface cached_chat() para compatibilidade com
    evaluator, worker, api.
    """

    def __init__(self):
        self.providers = []
        active = []

        deepseek = DeepSeekClient()
        self.providers.append(("DeepSeek", deepseek))
        if deepseek.enabled:
            active.append("DeepSeek (api.deepseek.com)")

        nvidia = NvidiaNimClient()
        self.providers.append(("NVIDIA", nvidia))
        if nvidia.enabled:
            active.append("NVIDIA NIM")

        minimax = MiniMaxClient()
        self.providers.append(("MiniMax", minimax))
        if minimax.enabled:
            active.append("MiniMax M3")

        print(f"[LLM] Provedores ativos: {', '.join(active) if active else 'NENHUM'}", flush=True)

    def cached_chat(self, system_prompt, user_prompt, json_mode=False,
                    cache_key=None, temperature=None, max_tokens=None):
        for name, provider in self.providers:
            resultado = self._try_provider(
                provider, name,
                system_prompt, user_prompt, json_mode, temperature, max_tokens,
            )
            if resultado is not None:
                return resultado
            print(f"[LLM] {name} falhou, tentando proximo...", flush=True)

        raise Exception("Todos provedores LLM falharam (DeepSeek + NVIDIA + MiniMax)")

    def _try_provider(self, provider, name, system_prompt, user_prompt,
                      json_mode, temperature, max_tokens):
        try:
            print(f"[LLM] Chamando {name} (json_mode={json_mode})...", flush=True)
            result = provider.chat(
                system_prompt, user_prompt,
                json_mode=json_mode,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if result:
                print(f"[LLM] {name} OK: {len(result)} chars", flush=True)
                return result
            print(f"[LLM] {name} retornou None", flush=True)
            return None
        except Exception as e:
            err_msg = str(e)[:150]
            print(f"[LLM] {name} FALHOU: {err_msg}", flush=True)
            return None

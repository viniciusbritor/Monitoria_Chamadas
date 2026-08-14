import os
import sys
import time
import requests
import json
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secrets_manager


def extract_json_from_text(text: str) -> str | None:
    """Extrai substring JSON valida de um texto contendo raciocinio/markdown."""
    if not text or not text.strip():
        return None
    t = text.strip()
    # 0. Tenta o texto bruto diretamente (se ja for JSON valido)
    try:
        json.loads(t)
        return t
    except Exception:
        pass
    # 1. Tenta extrair de bloco ```json ... ```
    if "```" in t:
        parts = t.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") and p.endswith("}"):
                try:
                    json.loads(p)
                    return p
                except Exception:
                    pass
    # 2. Tenta encontrar a primeira chave '{' e a ultima '}'
    first_brace = t.find("{")
    last_brace = t.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = t[first_brace:last_brace + 1].strip()
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    return None


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

    def _execute(self, payload, json_mode=False, max_retries=3):
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
                    choice = data["choices"][0]["message"]
                    content = choice.get("content", "") or ""
                    reasoning = choice.get("reasoning_content", "") or ""

                    if json_mode:
                        # 1. Tenta extrair JSON do content
                        extracted = extract_json_from_text(content)
                        if extracted:
                            return extracted
                        # 2. Se content nao tem JSON valido, tenta no reasoning_content
                        extracted_reasoning = extract_json_from_text(reasoning)
                        if extracted_reasoning:
                            print("[DeepSeek] Aviso: JSON extraido com sucesso de reasoning_content", flush=True)
                            return extracted_reasoning
                        print("[DeepSeek] ERRO: Resposta em json_mode nao contem JSON valido", flush=True)
                        return None
                    else:
                        # Modo texto (diarização)
                        if content and content.strip():
                            return content
                        if reasoning and reasoning.strip():
                            print("[DeepSeek] Aviso: content vazio em modo texto, usando reasoning_content", flush=True)
                            return reasoning
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
            temperature = 0.0  # (14/07/2026): alterado de 0.3 para 0.0 (consistencia maxima e determinismo de notas)
        if max_tokens is None:
            max_tokens = 8192  # (13/08/2026): aumentado para 8192 (suporte a reasoning_tokens + JSON)

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
            "cache_mode": "default",
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return self._execute(payload, json_mode=json_mode)

    def batch_chat(self, tasks: list[dict], json_mode=True) -> list:
        """NEW (08/07/2026 - Plano Ultra-Economico): executa 2 inferencias em 1 chamada.

        Para 2 tasks (caso comum: diarize + evaluate), combina em 1 prompt estruturado
        que pede ao LLM um JSON com 2 campos: 'diarizacao' e 'avaliacao'.
        Economia: -50% chamadas DeepSeek e -50% latencia LLM (~5-10s por chamada).

        Args:
            tasks: lista de dicts com chaves 'system_prompt' e 'user_prompt'
            json_mode: se True, forca JSON output

        Returns:
            lista de strings (respostas na mesma ordem das tasks)
            Retorna [None, None] se LLM falhar.
        """
        if not self.enabled:
            raise Exception("[DeepSeek] DEEPSEEK_API_KEY nao configurada")

        if len(tasks) == 2:
            combined_system = (
                "Voce deve responder em JSON com 2 campos: "
                "'diarizacao' (string com dialogo Operador:/Cliente:) e "
                "'avaliacao' (objeto JSON com campos nota_geral, etc).\n\n"
                f"TAREFA 1 (DIARIZACAO):\n{tasks[0]['system_prompt']}\n\n"
                f"TAREFA 2 (AVALIACAO):\n{tasks[1]['system_prompt']}"
            )
            combined_user = (
                f"TEXTO PARA DIARIZAR:\n{tasks[0]['user_prompt']}\n\n"
                f"TEXTO PARA AVALIAR:\n{tasks[1]['user_prompt']}"
            )
            payload = {
                "model": self.model,
                "temperature": 0.0,
                "max_tokens": 8192,
                "messages": [
                    {"role": "system", "content": combined_system},
                    {"role": "user", "content": combined_user},
                ],
                "response_format": {"type": "json_object"},
                "cache_mode": "default",
            }
            resp_text = self._execute(payload)
            if not resp_text:
                return [None, None]
            try:
                data = json.loads(resp_text)
                return [data.get("diarizacao"), json.dumps(data.get("avaliacao")) if data.get("avaliacao") else None]
            except Exception as e:
                print(f"[DeepSeek] batch parse falhou: {e}", flush=True)
                return [None, None]

        # Fallback: chamadas paralelas via threads
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = [pool.submit(self.chat, t["system_prompt"], t["user_prompt"],
                                   json_mode=json_mode) for t in tasks]
            return [f.result() for f in futures]


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
        self.enabled = False  # (14/08/2026): desativado (endpoint NVIDIA retornando 410 Gone)

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
            temperature = 0.0  # (14/07/2026): alterado de 0.3 para 0.0 (consistencia maxima e determinismo de notas)
        if max_tokens is None:
            max_tokens = 3000  # (10/07/2026): aumentado de 1000 para 3000

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
    """MiniMax Text-01 — fallback ultra-confiável."""

    def __init__(self):
        self.api_key = os.getenv("MINIMAX_API_KEY", "")
        if not self.api_key:
            self.api_key = secrets_manager.get_secret("MINIMAX_API_KEY")
        self.base_url = "https://api.minimax.chat/v1"
        self.model = "MiniMax-Text-01"
        self.enabled = bool(self.api_key)

    def _execute(self, payload, max_retries=3):
        if not self.enabled:
            raise Exception("[MiniMax] MINIMAX_API_KEY nao configurada")
        clean_key = self.api_key.strip().lstrip("\ufeff")
        headers = {
            "Authorization": f"Bearer {clean_key}",
            "Content-Type": "application/json",
        }
        retries = 0
        base_delay = 1

        while retries <= max_retries:
            try:
                resp = requests.post(
                    f"{self.base_url}/text/chatcompletion_v2",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if resp.status_code == 429:
                    retries += 1
                    if retries > max_retries:
                        raise Exception(f"[MiniMax] Max retries atingido (429)")
                    sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                    time.sleep(sleep_time)
                    continue
                if not resp.ok:
                    raise Exception(f"[MiniMax] HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]
                return None
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > max_retries:
                    raise Exception(f"[MiniMax] Erro apos {max_retries} retries: {e}")
                time.sleep(1)

    def chat(self, system_prompt, user_prompt, json_mode=False,
             temperature=None, max_tokens=None):
        if temperature is None:
            temperature = 0.0
        if max_tokens is None:
            max_tokens = 3000

        sp = system_prompt
        if json_mode and "json" not in sp.lower():
            sp = "JSON: " + sp

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": sp},
                {"role": "user", "content": user_prompt},
            ],
        }
        return self._execute(payload)


class LLMClient:
    """Multi-provider cascata: DeepSeek direto -> MiniMax -> NVIDIA NIM.

    Mantem a mesma interface cached_chat() e batch_chat() para compatibilidade com
    evaluator, worker, api.
    """

    def __init__(self):
        self.providers = []
        self.last_provider_used = None  # nome do ultimo provedor bem-sucedido
        active = []

        deepseek = DeepSeekClient()
        self.providers.append(("DeepSeek", deepseek))
        if deepseek.enabled:
            active.append("DeepSeek (api.deepseek.com)")

        minimax = MiniMaxClient()
        self.providers.append(("MiniMax", minimax))
        if minimax.enabled:
            active.append("MiniMax (api.minimax.chat)")

        nvidia = NvidiaNimClient()
        self.providers.append(("NVIDIA", nvidia))
        if nvidia.enabled:
            active.append("NVIDIA NIM")

        print(f"[LLM] Provedores ativos: {', '.join(active) if active else 'NENHUM'}", flush=True)

    def batch_chat(self, tasks: list[dict], json_mode=True) -> list:
        for name, provider in self.providers:
            if hasattr(provider, "batch_chat"):
                try:
                    print(f"[LLM] Chamando {name} (batch_chat)...", flush=True)
                    res = provider.batch_chat(tasks, json_mode=json_mode)
                    if res and len(res) == len(tasks) and res[0] is not None and res[1] is not None:
                        print(f"[LLM] {name} batch OK", flush=True)
                        self.last_provider_used = name
                        return res
                except Exception as e:
                    print(f"[LLM] {name} batch FALHOU: {str(e)[:150]}", flush=True)
        # Fallback: chamadas separadas via cached_chat
        return [
            self.cached_chat(t["system_prompt"], t["user_prompt"], json_mode=json_mode)
            for t in tasks
        ]

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

        raise Exception("Todos provedores LLM falharam (DeepSeek + MiniMax + NVIDIA)")

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
                self.last_provider_used = name
                return result
            print(f"[LLM] {name} retornou None", flush=True)
            return None
        except Exception as e:
            err_msg = str(e)[:150]
            print(f"[LLM] {name} FALHOU: {err_msg}", flush=True)
            return None

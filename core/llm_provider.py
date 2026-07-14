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
            temperature = 0.3  # (10/07/2026): voltou de 0.5 para 0.3 (equilibrio variacao/consistencia) (mais variacao nas notas)
        if max_tokens is None:
            max_tokens = 3000  # (10/07/2026): aumentado de 1000 para 3000 (prompt expandido)

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
                "temperature": 0.3,
                "max_tokens": 3000,
                "messages": [
                    {"role": "system", "content": combined_system},
                    {"role": "user", "content": combined_user},
                ],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
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
            temperature = 0.3  # (10/07/2026): voltou de 0.5 para 0.3 (equilibrio variacao/consistencia)
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



class LLMClient:
    """Multi-provider cascata: DeepSeek direto -> NVIDIA NIM.

    Mantem a mesma interface cached_chat() para compatibilidade com
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

        nvidia = NvidiaNimClient()
        self.providers.append(("NVIDIA", nvidia))
        if nvidia.enabled:
            active.append("NVIDIA NIM")


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

        raise Exception("Todos provedores LLM falharam (DeepSeek + NVIDIA)")

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

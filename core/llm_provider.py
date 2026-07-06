import os
import sys
import time
import requests
import json
import random

# Adiciona o diretorio raiz ao sys.path para importar secrets_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secrets_manager

class LLMClient:
    def __init__(self):
        self.api_key = secrets_manager.get_secret("MINIMAX_API_KEY")
        if not self.api_key:
            print("AVISO: MINIMAX_API_KEY não foi encontrada no Secrets Manager ou ambiente.")
        self.base_url = "https://api.minimax.io/v1/text/chatcompletion_v2"
        self.model = "MiniMax-M3"

    def _execute_request_with_backoff(self, payload, max_retries=5):
        """Executa a requisição com backoff exponencial com ruído (jitter) para evitar HTTP 429."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        retries = 0
        base_delay = 2
        
        while retries <= max_retries:
            try:
                response = requests.post(self.base_url, headers=headers, json=payload, timeout=120)  # 120s: M3 com Thinking ativo pode levar >60s em respostas longas
                if response.status_code == 429: # Rate Limit
                    retries += 1
                    if retries > max_retries:
                        print("Erro: Max retries atingido (HTTP 429).")
                        response.raise_for_status()
                    # Backoff exponencial com jitter
                    sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                    print(f"Rate limit atingido. Aguardando {sleep_time:.2f} segundos...")
                    time.sleep(sleep_time)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                # MiniMax retorna 200 OK mas com erro no base_resp
                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", 0) != 0:
                    status_msg = base_resp.get("status_msg", "Erro desconhecido")
                    print(f"Erro da API MiniMax: {status_msg} (Código {base_resp['status_code']})")
                    raise Exception(f"API Error: {status_msg}")
                    
                return data
                
            except requests.exceptions.RequestException as e:
                retries += 1
                if retries > max_retries:
                    print(f"Erro na requisição: {e}")
                    raise
                sleep_time = (base_delay ** retries) + random.uniform(0, 1)
                print(f"Erro {e}. Tentando novamente em {sleep_time:.2f}s...")
                time.sleep(sleep_time)

    def cached_chat(self, system_prompt, user_prompt, json_mode=False, cache_key=None,
                     temperature=None, max_tokens=None):
        """
        No MiniMax, o prompt caching real v2 para abab6.5 usa tokens especificos,
        mas simulamos o comportamento basico.
        Desativamos o thinking passando json_mode se solicitado.

        Perf (07/07/2026 - Plano A zero perda):
        - temperature default 0.3 (vs ~0.7 default) = respostas mais deterministicas
          e menos "caminhada" do thinking mode.
        - max_tokens default diferenciado por modo:
          * json_mode=True (evaluate) -> 1500: cobre JSON completo (~700 tokens
            tipicos) sem deixar LLM divagar.
          * json_mode=False (diarize) -> 400: cobre transcript reformatado.
        - Caller pode sobrescrever via parametros explicitos (temperature/max_tokens).
        """
        if temperature is None:
            # json_mode usa 0.3 (precisao no schema); diarize usa 0.1 (fidelidade
            # da separacao operador/cliente, sem criatividade)
            temperature = 0.3 if json_mode else 0.1

        if max_tokens is None:
            max_tokens = 1500 if json_mode else 400

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }

        # O MiniMax desativa o thinking se definirmos reply_constraints
        if json_mode:
            payload["reply_constraints"] = {
                "sender_type": "BOT",
                "sender_name": "Assistente"
            }
            # Se a API suportasse json_schema diretamente, adicionariamos aqui.

        data = self._execute_request_with_backoff(payload)

        if data and 'choices' in data:
            return data['choices'][0]['message']['content']
        return None

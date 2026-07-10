import os
import json
import datetime
from .llm_provider import LLMClient
from .masker import mask_pii

class Evaluator:
    def __init__(self):
        self.client = LLMClient()
        
        # Histórico de FinOps (Tokens)
        self.finops_log = "finops_usage.json"

    def _log_usage(self, response, etapa="desconhecida"):
        """Persiste o consumo de tokens em finops_usage.json para rastreamento FinOps."""
        try:
            usage = response.get("usage", {}) if isinstance(response, dict) else {}
            if not usage:
                return

            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            cached_tokens = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # Cálculo de custo estimado (preços MiniMax M3 com 50% de desconto)
            input_noncached = max(0, prompt_tokens - cached_tokens)
            custo_usd = (
                (input_noncached / 1_000_000 * 0.30) +
                (cached_tokens  / 1_000_000 * 0.06) +
                (completion_tokens / 1_000_000 * 1.20)
            )

            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "etapa": etapa,
                "modelo": "MiniMax-M3",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": total_tokens,
                "custo_estimado_usd": round(custo_usd, 8),
            }

            log_path = self.finops_log
            historico = []
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    historico = json.load(f)
            historico.append(entry)
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(historico, f, ensure_ascii=False, indent=2)

            print(f"[FinOps] {etapa}: {total_tokens} tokens | custo estimado: USD {custo_usd:.6f}")
        except Exception as e:
            print(f"[FinOps] Aviso: falha ao registrar uso de tokens: {e}")

    def diarize(self, transcript):
        system_prompt = """Separe a transcricao em dialogo entre 'Operador:' e 'Cliente:'.
Operador = cumprimenta/pede dados/resolve/transfere. Cliente = expoe problema/reclama/duvida.
IMPORTANTE: prefixe CADA turno com o rotulo exato 'Operador:' ou 'Cliente:'.
Separe turnos alternados com quebra de linha dupla.
Nao altere as palavras originais da transcricao.
Retorne APENAS o dialogo formatado, sem comentarios adicionais."""
        user_prompt = f"--- TRANSCRICAO CONTINUA ---\n{mask_pii(transcript)}"
        print("🤖 Diarizando transcricao com MiniMax M3...")
        text = self.client.cached_chat(system_prompt, user_prompt, json_mode=False, max_tokens=2000)
        result = text.strip() if text else transcript

        if not result or result == transcript:
            print("[Evaluator] AVISO: diarizacao retornou original (possivel falha)")
            return transcript

        if not ('Operador:' in result or 'Cliente:' in result):
            print(f"[Evaluator] AVISO: diarizacao sem rotulos Operador:/Cliente:. Primeiros 100 chars: {result[:100]}")
            return transcript

        print(f"[Evaluator] Diarizacao OK: {len(result)} chars, {result.count('Operador:')} turnos operador, {result.count('Cliente:')} turnos cliente")
        return result

    def evaluate(self, transcript, user_settings=None, pop_context="", quality_form=""):
        """
        Avalia a transcrição com base nos POPs e formulário de qualidade.
        """
        if user_settings is None:
            user_settings = {}

        checklist_str = user_settings.get('checklist_items', '[]')
        estrategia_vendas = user_settings.get('estrategia_vendas', 'Não informada.')
        estrategia_retencao = user_settings.get('estrategia_retencao', 'Não informada.')

        # Perf (07/07/2026 - Plano A zero perda): system_prompt trimado de ~1200
        # tokens para ~700 (-40%). Schema de saida (campos JSON exigidos)
        # continua IDENTICO ao anterior. Apenas descricoes de uma linha em vez
        # de paragrafos. Output esperado: mesma nota_geral +/-5.
        system_prompt = f"""Auditor Sênior CX. Avalie o atendimento abaixo.

--- REGRAS DE CONSISTENCIA (OBRIGATORIO - DESCUMPRIR INVALIDA A AVALIACAO) ---
A nota de cada fase DEVE refletir o sentimento do cliente naquela fase.
NAO existe cliente "Irritado" com NPS 10. Isso e' impossivel.

Exemplos CORRETOS (siga exatamente):
- Se sentimento_cliente="Irritado"  → nota_qa entre 20-55, nota_nps entre 1-3
- Se sentimento_cliente="Neutro"    → nota_qa entre 55-80, nota_nps entre 4-7
- Se sentimento_cliente="Positivo"  → nota_qa entre 75-100, nota_nps entre 7-10

Exemplo de fase CORRETA: {{"sentimento_cliente":"Irritado","nota_nps":2,"nota_qa":42}}
NUNCA produza: {{"sentimento_cliente":"Irritado","nota_nps":10}} ← INACEITAVEL

--- CONTEXTO POP ---
{pop_context if pop_context else "1. Cordialidade. 2. Resolucao. 3. Empatia. 4. Clareza."}

--- DIRETRIZES DE QUALIDADE ---
{quality_form if quality_form else "1. Cordialidade. 2. Resolucao do Problema. 3. Empatia. 4. Clareza."}

--- CONFIGURACOES DA EMPRESA ---
1. CHECKLIST OBRIGATORIO: {checklist_str}
2. PLAYBOOK VENDAS (Up-sell/Cross-sell): {estrategia_vendas}
3. PLAYBOOK RETENCAO (Anti-Cancelamento): {estrategia_retencao}

--- AVALIACAO EM 3 FASES ---
Divida em: 1) Apresentacao (empatia + escuta inicial), 2) Metodos de Resolucao (conduta do atendente), 3) Fechamento (explicacao de tramites e proximos passos).
Para cada fase atribua: nota_qa (0-100), nota_nps (0-10), analise (1-3 frases).

--- SAIDA (JSON ESTRITO) ---
{{"nota_geral": int, "nota_qualidade_operador": int, "nota_sentimento_cliente": int,
"nome_atendente": "Nome do atendente" | null,
"motivo_contato": "Descricao do motivo da chamada",
"classificacao_motivo": "Cobrança Indevida|Suporte Técnico|Assistência Técnica|Cancelamento|Informações|Reclamação|Vendas|Outros",
"fases": {{"apresentacao": {{"nota_qa": int, "nota_nps": int, "analise": str,
  "sentimento_cliente": "Positivo|Neutro|Irritado", "sentimento_operador": "Positivo|Neutro|Desinteressado"}},
"resolucao": {{"nota_qa": int, "nota_nps": int, "analise": str,
  "sentimento_cliente": "Positivo|Neutro|Irritado", "sentimento_operador": "Positivo|Neutro|Desinteressado"}},
"fechamento": {{"nota_qa": int, "nota_nps": int, "analise": str,
  "sentimento_cliente": "Positivo|Neutro|Irritado", "sentimento_operador": "Positivo|Neutro|Desinteressado"}}}},
"erro_critico": bool, "pontos_positivos": [str], "pontos_melhoria": [str],
"recomendacao_treinamento": str, "humor_cliente": "Positivo|Neutro|Irritado",
"humor_expert": "Positivo|Neutro|Desinteressado",
"sentimentos_cliente": [str], "sentimentos_operador": [str],
"erros_fatais_identificados": [str],
"checklist_conformidade": [{{"item": str, "cumprido": bool}}],
"oportunidade_venda_retencao": bool, "sucesso_venda_retencao": bool,
"tipo_oportunidade": str, "argumentos_operador": [str]}}"""

        user_prompt = f"--- TRANSCRICAO DIARIZADA ---\n{mask_pii(transcript)}"

        print("🤖 Avaliando atendimento com MiniMax M3...")
        text = self.client.cached_chat(system_prompt, user_prompt, json_mode=True)

        try:
            if not text:
                raise Exception("Resposta vazia da API")

            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            return json.loads(text.strip())
        except Exception as e:
            print(f"❌ Erro ao parsear resposta da IA: {e}")
            return {"error": "Falha no processamento", "raw_response": str(text)}

    def diarize_and_evaluate(self, transcript, user_settings=None,
                              pop_context="", quality_form=""):
        """NEW (08/07/2026 - Plano Ultra-Economico): diarize + evaluate em 1 chamada LLM.

        Combina os 2 prompts (diarizacao + avaliacao) em 1 request combinado via
        LLMClient.batch_chat(). Quando o provider primario (DeepSeek) suporta
        batch_chat(), processa em 1 round-trip. Fallback: chamadas separadas.

        Args:
            transcript: texto bruto transcrito pelo Whisper
            user_settings: dict com checklist_items, estrategia_vendas, etc
            pop_context: contexto POP do usuario
            quality_form: diretrizes de qualidade do formulario

        Returns:
            dict com chaves:
              - diarized_transcript: texto com prefixos Operador:/Cliente:
              - evaluation: dict parseado do JSON de avaliacao
        """
        if user_settings is None:
            user_settings = {}

        checklist_str = user_settings.get('checklist_items', '[]')
        estrategia_vendas = user_settings.get('estrategia_vendas', 'Não informada.')
        estrategia_retencao = user_settings.get('estrategia_retencao', 'Não informada.')

        # Prompt 1: Diarizacao
        diarize_system = """Separe a transcricao em dialogo entre 'Operador:' e 'Cliente:'.
Operador = cumprimenta/pede dados/resolve/transfere. Cliente = expoe problema/reclama/duvida.
IMPORTANTE: prefixe CADA turno com o rotulo exato 'Operador:' ou 'Cliente:'.
Separe turnos alternados com quebra de linha dupla.
Nao altere as palavras originais da transcricao.
Retorne APENAS o dialogo formatado, sem comentarios adicionais."""
        diarize_user = f"--- TRANSCRICAO CONTINUA ---\n{mask_pii(transcript)}"

        # Prompt 2: Avaliacao (reuso do mesmo system_prompt do evaluate())
        eval_system = f"""Auditor Sênior CX. Avalie o atendimento abaixo.

--- CONTEXTO POP ---
{pop_context if pop_context else "1. Cordialidade. 2. Resolucao. 3. Empatia. 4. Clareza."}

--- DIRETRIZES DE QUALIDADE ---
{quality_form if quality_form else "1. Cordialidade. 2. Resolucao do Problema. 3. Empatia. 4. Clareza."}

--- CONFIGURACOES DA EMPRESA ---
1. CHECKLIST OBRIGATORIO: {checklist_str}
2. PLAYBOOK VENDAS (Up-sell/Cross-sell): {estrategia_vendas}
3. PLAYBOOK RETENCAO (Anti-Cancelamento): {estrategia_retencao}

--- AVALIACAO EM 3 FASES ---
Divida em: 1) Apresentacao (empatia + escuta inicial), 2) Metodos de Resolucao (conduta do atendente), 3) Fechamento (explicacao de tramites e proximos passos).
Para cada fase atribua: nota_qa (0-100), nota_nps (0-10), analise (1-3 frases).

--- REGRAS DE CONSISTENCIA SENTIMENTO-NOTA ---
As notas DEVEM ser consistentes com os sentimentos de cada fase:
- Se sentimento_cliente for "Irritado": nota_qa <= 60, nota_nps <= 3
- Se sentimento_cliente for "Neutro": nota_qa entre 60-80, nota_nps entre 4-7
- Se sentimento_cliente for "Positivo": nota_qa >= 80, nota_nps >= 7

--- SAIDA (JSON ESTRITO) ---
{{"nota_geral": int, "nota_qualidade_operador": int, "nota_sentimento_cliente": int,
"nome_atendente": "Nome do atendente" | null,
"motivo_contato": "Descricao do motivo da chamada",
"classificacao_motivo": "Cobrança Indevida|Suporte Técnico|Assistência Técnica|Cancelamento|Informações|Reclamação|Vendas|Outros",
"fases": {{"apresentacao": {{"nota_qa": int, "nota_nps": int, "analise": str,
  "sentimento_cliente": "Positivo|Neutro|Irritado", "sentimento_operador": "Positivo|Neutro|Desinteressado"}},
"resolucao": {{"nota_qa": int, "nota_nps": int, "analise": str,
  "sentimento_cliente": "Positivo|Neutro|Irritado", "sentimento_operador": "Positivo|Neutro|Desinteressado"}},
"fechamento": {{"nota_qa": int, "nota_nps": int, "analise": str,
  "sentimento_cliente": "Positivo|Neutro|Irritado", "sentimento_operador": "Positivo|Neutro|Desinteressado"}}}},
"erro_critico": bool, "pontos_positivos": [str], "pontos_melhoria": [str],
"recomendacao_treinamento": str, "humor_cliente": "Positivo|Neutro|Irritado",
"humor_expert": "Positivo|Neutro|Desinteressado",
"sentimentos_cliente": [str], "sentimentos_operador": [str],
"erros_fatais_identificados": [str],
"checklist_conformidade": [{{"item": str, "cumprido": bool}}],
"oportunidade_venda_retencao": bool, "sucesso_venda_retencao": bool,
"tipo_oportunidade": str, "argumentos_operador": [str]}}"""

        eval_user = f"--- TRANSCRICAO DIARIZADA ---\n{mask_pii(transcript)}"

        tasks = [
            {"system_prompt": diarize_system, "user_prompt": diarize_user},
            {"system_prompt": eval_system, "user_prompt": eval_user},
        ]

        # Tentar batch primeiro
        if hasattr(self.client, 'batch_chat'):
            try:
                print("[Evaluator] Batch LLM (diarize + evaluate em 1 chamada)...", flush=True)
                results = self.client.batch_chat(tasks, json_mode=True)
                diarized = results[0] if results[0] else transcript
                evaluation_raw = results[1] if results[1] else None

                if not diarized or ('Operador:' not in diarized and 'Cliente:' not in diarized):
                    print("[Evaluator] AVISO: diarizacao batch sem rotulos. Fallback diarize().", flush=True)
                    diarized = self.diarize(transcript)

                if evaluation_raw:
                    try:
                        evaluation = json.loads(evaluation_raw) if isinstance(evaluation_raw, str) else evaluation_raw
                    except Exception as e:
                        print(f"[Evaluator] Parse avaliacao batch falhou: {e}", flush=True)
                        evaluation = self.evaluate(diarized, user_settings, pop_context, quality_form)
                else:
                    evaluation = self.evaluate(diarized, user_settings, pop_context, quality_form)

                return {
                    "diarized_transcript": diarized,
                    "evaluation": evaluation,
                }
            except Exception as e:
                print(f"[Evaluator] Batch LLM falhou ({e}), fallback chamadas separadas", flush=True)

        # Fallback: chamadas separadas (codigo original)
        diarized = self.diarize(transcript)
        evaluation = self.evaluate(diarized, user_settings, pop_context, quality_form)
        return {
            "diarized_transcript": diarized,
            "evaluation": evaluation,
        }

if __name__ == "__main__":
    # Teste rápido
    evaluator = Evaluator()
    test_transcript = "Bom dia, meu nome é João, como posso ajudar? Olá João, meu app não abre. Entendi, vamos resetar sua senha. Obrigado. De nada."
    result = evaluator.evaluate(test_transcript)
    print(json.dumps(result, indent=4, ensure_ascii=False))

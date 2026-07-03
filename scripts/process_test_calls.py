import os
import sys
import json
import sqlite3

# Forçar UTF-8 para stdout e stderr
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass # Em versões antigas de python do windows isso pode falhar, mas deve funcionar no python 3.7+

# Adiciona o diretorio raiz ao sys.path para importar core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transcriber import Transcriber
from core.llm_provider import LLMClient
import secrets_manager

class TokenTrackingClient(LLMClient):
    def __init__(self):
        super().__init__()
        self.usage_history = []

    def cached_chat_with_usage(self, system_prompt, user_prompt, json_mode=False):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        if json_mode:
            payload["reply_constraints"] = {
                "sender_type": "BOT",
                "sender_name": "Assistente"
            }
        
        # Chamamos o método herdado que executa e trata backoff
        data = self._execute_request_with_backoff(payload)
        
        if data:
            usage = data.get("usage", {})
            self.usage_history.append({
                "model": self.model,
                "usage": usage,
                "json_mode": json_mode
            })
            content = data['choices'][0]['message']['content'] if 'choices' in data else None
            return content, usage
        return None, {}

def process_audio(filename, audio_path):
    print(f"\n==========================================")
    print(f"Processando: {filename}")
    print(f"==========================================")
    
    # 1. Transcrição via Whisper (Local)
    print("Transcrevendo audio com Whisper...")
    transcriber = Transcriber()
    transcript, segments = transcriber.transcribe(audio_path)
    print(f"Transcricao Concluida ({len(transcript)} caracteres).")
    
    client = TokenTrackingClient()
    
    # 2. Diarização via MiniMax M3
    system_prompt_diarize = """Você é um especialista em transcrição de call centers.
Sua tarefa é separar a transcrição contínua fornecida no formato de diálogo entre 'Operador' e 'Cliente'.
Regras:
1. Identifique quem está falando baseado no contexto (O Operador geralmente cumprimenta, pede dados, resolve o problema. O Cliente expõe o problema e dúvidas).
2. Não altere as palavras, apenas divida em parágrafos com o prefixo 'Operador:' ou 'Cliente:'.
"""
    user_prompt_diarize = f"--- TRANSCRIÇÃO CONTÍNUA ---\n{transcript}"
    print("Diarizando com MiniMax M3...")
    diarized_text, diarize_usage = client.cached_chat_with_usage(system_prompt_diarize, user_prompt_diarize, json_mode=False)
    
    print("\n--- Diarizacao usage ---")
    print(json.dumps(diarize_usage, indent=2))
    
    # 3. Avaliação via MiniMax M3
    system_prompt_evaluate = """Você é um Auditor de Qualidade Sênior em CX.
Sua tarefa é avaliar a seguinte transcrição DIARIZADA (Operador e Cliente) de atendimento baseada nos POPs e nas Diretrizes de Qualidade fornecidas.

--- CONTEXTO POP ---
Seguir roteiro padrão de atendimento cordial e resolutivo.

--- DIRETRIZES DE QUALIDADE (EXPECTATIVAS DO OPERADOR) ---
1. Cordialidade, 2. Resolução do Problema, 3. Empatia, 4. Clareza na comunicação.

--- CONFIGURAÇÕES DINÂMICAS DA EMPRESA ---
1. CHECKLIST OBRIGATÓRIO (Em JSON string):
[]
Audite rigorosamente cada um destes itens e defina se foram 'cumpridos' (true) ou não (false) durante a chamada.

2. PLAYBOOK DE VENDAS (Estratégia de Up-sell / Cross-sell):
Não informada.

3. PLAYBOOK DE RETENÇÃO (Estratégia Anti-Cancelamento):
Não informada.

Baseado no contexto da ligação, decida se o Operador estava lidando com uma oportunidade de Vendas ou de Retenção e avalie seu sucesso considerando os Playbooks acima.

--- INSTRUÇÕES DE AVALIAÇÃO ---
Você deve dividir a chamada em 3 fases principais e avaliá-las individualmente:
1. Apresentação: Onde o atendente escuta o cliente, demonstra empatia e entende o problema inicial exposto.
2. Métodos de Resolução: A conduta do atendente para propor métodos de resolução conforme a necessidade do cliente (o ideal é resolver durante a chamada ou, no mínimo, conseguir entender e encaminhar adequadamente).
3. Fechamento da Chamada: Onde o atendente deve explicar detalhadamente para o cliente como será o trâmite e próximos passos, caso o problema não tenha sido resolvido imediatamente.

Para cada uma das 3 fases, você deve atribuir:
- Uma nota de QA do Atendente (0-100) baseada nas diretrizes de conduta.
- Uma nota de NPS/Satisfação do Cliente (0-10) baseada nas reações e sentimentos dele.
- Uma análise descritiva em texto detalhando a performance e acontecimentos nessa fase.

--- INSTRUÇÕES DE SAÍDA ---
Responda EXATAMENTE em formato JSON estruturado com os seguintes campos:
- nota_geral (inteiro de 0-100) -> Média ponderada ou nota geral de QA do atendente/operador.
- nota_qualidade_operador (inteiro de 0-100) -> Mesma que a nota geral.
- nota_sentimento_cliente (inteiro de 0-10) -> Nota geral de satisfação/sentimento do cliente (0 a 10).
- fases (objeto contendo as 3 fases):
  - apresentacao (objeto com: 'nota_qa' [inteiro], 'nota_nps' [inteiro], 'analise' [string])
  - resolucao (objeto com: 'nota_qa' [inteiro], 'nota_nps' [inteiro], 'analise' [string])
  - fechamento (objeto com: 'nota_qa' [inteiro], 'nota_nps' [inteiro], 'analise' [string])
- erro_critico (booleano) -> Falha grave do Operador.
- pontos_positivos (lista de strings) -> Pontos fortes do Operador.
- pontos_melhoria (lista de strings) -> O que o Operador pode melhorar.
- recomendacao_treinamento (string) -> Recomendação de capacitação técnica.
- humor_cliente (string: Positivo, Neutro, Irritado)
- humor_expert (string: Positivo, Neutro, Desinteressado)
- sentimentos_cliente (lista de strings) -> Sentimentos/emoções do cliente durante o contato.
- sentimentos_operador (lista de strings) -> Posturas/sentimentos demonstrados pelo operador.
- erros_fatais_identificados (lista de strings) -> Erros graves ou descumprimentos de regras críticas.
- checklist_conformidade (lista de objetos) -> Extraia um checklist baseado nas Diretrizes de Qualidade.
- oportunidade_venda_retencao (booleano) -> Oportunidade de venda ou retenção.
- sucesso_venda_retencao (booleano)
- tipo_oportunidade (string)
- argumentos_operador (lista de strings)"""

    user_prompt_evaluate = f"--- TRANSCRIÇÃO DIARIZADA ---\n{diarized_text}"
    print("Avaliando com MiniMax M3...")
    eval_text, eval_usage = client.cached_chat_with_usage(system_prompt_evaluate, user_prompt_evaluate, json_mode=True)
    
    print("\n--- Avaliacao usage ---")
    print(json.dumps(eval_usage, indent=2))
    
    # Exibe o resultado parseado
    try:
        if "```json" in eval_text:
            eval_text = eval_text.split("```json")[1].split("```")[0]
        elif "```" in eval_text:
            eval_text = eval_text.split("```")[1].split("```")[0]
        eval_json = json.loads(eval_text.strip())
        print(f"\nNota Geral CX: {eval_json.get('nota_geral')}")
        print(f"Humor Cliente: {eval_json.get('humor_cliente')}")
    except Exception as e:
        print(f"Erro ao parsear avaliacao JSON: {e}")
        
    return {
        "filename": filename,
        "transcript_len": len(transcript),
        "diarized_len": len(diarized_text) if diarized_text else 0,
        "diarize_usage": diarize_usage,
        "eval_usage": eval_usage,
        "eval_result": eval_text
    }

def main():
    test_dir = r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas_Teste\chamadas_testes"
    files = [
        "WhatsApp Audio 2026-06-29 at 07.11.10.mpeg",
        "WhatsApp Audio 2026-06-29 at 07.11.11.mpeg"
    ]
    
    results = []
    for f in files:
        path = os.path.join(test_dir, f)
        if os.path.exists(path):
            try:
                res = process_audio(f, path)
                results.append(res)
            except Exception as e:
                print(f"Erro ao processar {f}: {e}")
        else:
            print(f"Arquivo nao existe: {path}")
            
    # Escreve resultados num JSON temporário para o relatório
    with open("scripts/processed_tokens_results.json", "w", encoding="utf-8") as out:
        json.dump(results, out, ensure_ascii=False, indent=2)
    print("\nResultados salvos em scripts/processed_tokens_results.json")

if __name__ == "__main__":
    main()

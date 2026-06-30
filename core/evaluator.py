import os
import json
from .llm_provider import LLMClient

class Evaluator:
    def __init__(self):
        self.client = LLMClient()
        
        # Histórico de FinOps (Tokens)
        self.finops_log = "finops_usage.json"

    def _log_usage(self, response):
        """No momento, o log_usage será um stub porque o MiniMax cached_chat não retorna a usage no wrapper."""
        pass

    def diarize(self, transcript):
        system_prompt = """Você é um especialista em transcrição de call centers.
Sua tarefa é separar a transcrição contínua fornecida no formato de diálogo entre 'Operador' e 'Cliente'.
Regras:
1. Identifique quem está falando baseado no contexto (O Operador geralmente cumprimenta, pede dados, resolve o problema. O Cliente expõe o problema e dúvidas).
2. Não altere as palavras, apenas divida em parágrafos com o prefixo 'Operador:' ou 'Cliente:'.
"""
        user_prompt = f"--- TRANSCRIÇÃO CONTÍNUA ---\n{transcript}"
        print("🤖 Diarizando transcrição com MiniMax M3...")
        text = self.client.cached_chat(system_prompt, user_prompt, json_mode=False)
        return text.strip() if text else transcript

    def evaluate(self, transcript, user_settings=None, pop_context="", quality_form=""):
        """
        Avalia a transcrição com base nos POPs e formulário de qualidade.
        """
        if user_settings is None:
            user_settings = {}
            
        checklist_str = user_settings.get('checklist_items', '[]')
        estrategia_vendas = user_settings.get('estrategia_vendas', 'Não informada.')
        estrategia_retencao = user_settings.get('estrategia_retencao', 'Não informada.')

        system_prompt = f"""Você é um Auditor de Qualidade Sênior em CX.
Sua tarefa é avaliar a seguinte transcrição DIARIZADA (Operador e Cliente) de atendimento baseada nos POPs e nas Diretrizes de Qualidade fornecidas.

--- CONTEXTO POP ---
{pop_context if pop_context else "Seguir roteiro padrão de atendimento cordial e resolutivo."}

--- DIRETRIZES DE QUALIDADE (EXPECTATIVAS DO OPERADOR) ---
{quality_form if quality_form else "1. Cordialidade, 2. Resolução do Problema, 3. Empatia, 4. Clareza na comunicação."}

--- CONFIGURAÇÕES DINÂMICAS DA EMPRESA ---
1. CHECKLIST OBRIGATÓRIO (Em JSON string):
{checklist_str}
Audite rigorosamente cada um destes itens e defina se foram 'cumpridos' (true) ou não (false) durante a chamada.

2. PLAYBOOK DE VENDAS (Estratégia de Up-sell / Cross-sell):
{estrategia_vendas}

3. PLAYBOOK DE RETENÇÃO (Estratégia Anti-Cancelamento):
{estrategia_retencao}

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
- sentimentos_cliente (lista de strings) -> Sentimentos/emoções do cliente durante o contato (ex: ["Ansioso", "Frustrado", "Satisfeito"]).
- sentimentos_operador (lista de strings) -> Posturas/sentimentos demonstrados pelo operador (ex: ["Empático", "Paciente", "Claro"]).
- erros_fatais_identificados (lista de strings) -> Erros graves ou descumprimentos de regras críticas identificados (ex: ["Rudeza", "Informação incorreta"]).
- checklist_conformidade (lista de objetos) -> Extraia um checklist baseado nas Diretrizes de Qualidade. Cada objeto deve ter: 'item' (string com o passo avaliado) e 'cumprido' (booleano). Ex: [{"item": "Saudação inicial", "cumprido": true}].
- oportunidade_venda_retencao (booleano) -> Houve oportunidade óbvia para retenção de cliente (evitar cancelamento) ou realizar venda (cross-sell/up-sell)?
- sucesso_venda_retencao (booleano) -> Se houve a oportunidade, o operador conseguiu concretizar a venda/retenção com sucesso?
- tipo_oportunidade (string) -> Descreva o tipo, ex: "Retenção", "Cross-sell", "Up-sell", "Nenhuma".
- argumentos_operador (lista de strings) -> Liste as exatas argumentações que o operador usou (ou tentou usar) para convencer o cliente nessa oportunidade."""

        user_prompt = f"--- TRANSCRIÇÃO DIARIZADA ---\n{transcript}"

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

if __name__ == "__main__":
    # Teste rápido
    evaluator = Evaluator()
    test_transcript = "Bom dia, meu nome é João, como posso ajudar? Olá João, meu app não abre. Entendi, vamos resetar sua senha. Obrigado. De nada."
    result = evaluator.evaluate(test_transcript)
    print(json.dumps(result, indent=4, ensure_ascii=False))

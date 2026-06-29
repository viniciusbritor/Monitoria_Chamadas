import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.llm_provider import LLMClient

def generate_call_script(context_type, index, client):
    system_prompt = """
    Você é um roteirista especializado em simulações extremamente realistas de call center no Brasil.
    Sua tarefa é gerar uma transcrição de uma ligação telefônica (entre 3 e 10 minutos de leitura, cerca de 500 a 800 palavras).
    
    **Regras Essenciais:**
    1. O cliente NÃO PODE soar como um robô, sob nenhuma hipótese. Adicione MUITAS marcas de oralidade na fala do CLIENTE ("hmmm", "ééé...", "ah", "tipo", "olha"), gaguejos leves, frases interrompidas ou re-iniciadas, suspiros, e reações autênticas de impaciência, dúvida ou alívio. O atendente deve manter postura profissional.
    2. Escolha um Gênero (MASCULINO ou FEMININO) para o Atendente e um para o Cliente. O nome dos personagens DEVE corresponder EXATAMENTE ao gênero. NUNCA coloque nome feminino para homem ou vice-versa.
    3. Quando o cliente e atendente discutirem, ficarem na dúvida, ou divergirem, adicione "interrompe_anterior": true nas falas para que a voz do atual atropele o final da fala do anterior. Isso é obrigatório em casos de atrito.
    4. IMPORTANTE (CPF): O cliente DEVE sempre informar um número de CPF inventado com 11 dígitos, MAS deve ser falado de forma NATURAL, em dezenas (ex: "12 34 56 78... 90 1") ou de dígito em dígito (ex: "um, dois, três... quatro, cinco..."). NUNCA escreva o CPF inteiro de uma vez ou na casa dos milhões/bilhões. Exemplos bons: "meu cpf é... 45... 67... 89... 10... 23... 4" ou "é zero cinco um... três quatro dois...".

    Retorne o resultado EXATAMENTE no formato JSON abaixo, sem blocos markdown adicionais:
    {
        "chamada_id": "...",
        "contexto": "...",
        "genero_atendente": "FEMININO",
        "genero_cliente": "MASCULINO",
        "falas": [
            {"speaker": "Atendente", "text": "Central, boa tarde. Meu nome é Mariana, com quem falo?", "interrompe_anterior": false},
            {"speaker": "Cliente", "text": "Boa tarde, Mariana... hmmm, é... eu queria ver um negócio, moça...", "interrompe_anterior": false},
            {"speaker": "Atendente", "text": "Pode falar, o que houve?", "interrompe_anterior": true}
        ]
    }
    """
    
    user_prompt = f"Gere uma chamada telefônica no contexto: {context_type}. Dê vida ao cliente! Deixe-o extremamente humano (ele deve usar linguagem de dia-a-dia, informal, gírias leves). Não crie um cliente certinho."

    print(f"[{index}/5] Gerando roteiro via MiniMax-M3: {context_type[:30]}...")
    
    content = client.cached_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_mode=True,
        cache_key="callcenter_generator_v2"
    )
    
    if not content:
        return None
        
    try:
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        
        parsed_json = json.loads(content)
        return parsed_json
    except Exception as e:
        print(f"Erro ao parsear JSON na chamada {index}: {e}")
        return None

if __name__ == "__main__":
    client = LLMClient()
    if not client.api_key:
        print("Erro Crítico: Chave MINIMAX_API_KEY não foi encontrada pelo secrets_manager.")
        sys.exit(1)

    contextos = [
        ("1_Discussao_Extrema", "Discussão e atrito extremo: Cliente furioso pois cobraram um valor indevido 3 vezes. Atendente tenta acalmar mas cliente grita. Sem resolução."),
        ("2_Problema_Complexo", "Problema complexo: Falha no roteamento do modem do cliente. Atendente guia o cliente (leigo) a fazer reset de fábrica e reconfigurar IPs. Muito técnico."),
        ("3_Conta_Simples_A", "Problema simples: Cliente liga para pedir a 2ª via da fatura que não chegou no email. Ligação rápida e cordial."),
        ("4_Conta_Simples_B", "Problema simples: Cliente não consegue trocar a senha do aplicativo. Atendente envia link por SMS e aguarda."),
        ("5_Cancelamento", "Outros (Cancelamento): Cliente quer cancelar o serviço pois vai se mudar de país. Atendente tenta retenção com descontos, mas o cliente recusa. Fim amigável.")
    ]

    for index, (nome_arquivo, contexto) in enumerate(contextos, start=1):
        roteiro = generate_call_script(contexto, index, client)
        if roteiro:
            filepath = os.path.join("chamadas_simuladas", "roteiros", f"{nome_arquivo}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(roteiro, f, ensure_ascii=False, indent=4)
            print(f"Salvo: {filepath}")
    
    print("Processo de geração de roteiros finalizado.")



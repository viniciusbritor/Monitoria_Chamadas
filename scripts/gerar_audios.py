import os
import json
import asyncio
import random
import subprocess
import requests
from pydub import AudioSegment
from pydub.generators import WhiteNoise

# Adicionando o diretorio raiz para pegar a chave
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secrets_manager

# Vozes MiniMax (multilingues de alta qualidade)
VOZES_MASC = ["male-qn-jingying"]
VOZES_FEM = ["female-shaonv"]

def get_voz_por_genero(genero, fallback_se_igual=None):
    genero = str(genero).upper()
    if genero == "MASCULINO":
        escolhida = random.choice(VOZES_MASC)
        if fallback_se_igual and escolhida == fallback_se_igual:
            escolhida = [v for v in VOZES_MASC if v != fallback_se_igual][0]
    else:
        escolhida = random.choice(VOZES_FEM)
        if fallback_se_igual and escolhida == fallback_se_igual:
            escolhida = [v for v in VOZES_FEM if v != fallback_se_igual][0]
            
    return escolhida

def apply_telephone_filter(audio_segment):
    """Aplica um filtro passa-banda para simular telefone (300Hz - 3400Hz)."""
    # High pass em 300Hz
    filtered = audio_segment.high_pass_filter(300)
    # Low pass em 3400Hz
    filtered = filtered.low_pass_filter(3400)
    return filtered

async def gerar_fala_minimax(texto, voz, output_path, pitch=0):
    """Usa a API MiniMax T2A para gerar o arquivo MP3."""
    api_key = secrets_manager.get_secret("MINIMAX_API_KEY")
    if not api_key:
        print("Erro: Chave MINIMAX_API_KEY não encontrada.")
        return
        
    url = "https://api.minimax.io/v1/t2a_v2"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "speech-01-turbo",
        "text": texto,
        "voice_setting": {
            "voice_id": voz,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": pitch
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    }
    
    # Adiciona pequena aleatoriedade no rate e pitch para o cliente soar mais humano
    if "presenter" not in voz:
        payload["voice_setting"]["speed"] = round(random.uniform(1.0, 1.1), 2)
        
    # Executa a requisição (sincrona, num wrapper asyncio para não travar event loop)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, lambda: requests.post(url, headers=headers, json=payload, timeout=30))
    
    if response.status_code == 200:
        data = response.json()
        if data.get("base_resp", {}).get("status_code", 0) != 0:
            print(f"Erro MiniMax T2A: {data.get('base_resp')}")
            return
            
        with open(output_path, "wb") as f:
            f.write(bytes.fromhex(data["data"]["audio"]))
    else:
        print(f"Erro HTTP {response.status_code}: {response.text}")

async def processar_roteiro(json_path, output_mp3_path):
    with open(json_path, "r", encoding="utf-8") as f:
        dados = json.load(f)
    
    falas = dados.get("falas", [])
    if not falas:
        return
    
    genero_atendente = dados.get("genero_atendente", "FEMININO")
    genero_cliente = dados.get("genero_cliente", "MASCULINO")
    
    voz_atendente = get_voz_por_genero(genero_atendente)
    voz_cliente = get_voz_por_genero(genero_cliente, fallback_se_igual=voz_atendente)
    
    vozes_map = {
        "Atendente": voz_atendente,
        "Cliente": voz_cliente
    }
    
    print(f"Processando {os.path.basename(json_path)}...")
    print(f"  Voz Atendente: {voz_atendente} ({genero_atendente})")
    print(f"  Voz Cliente: {voz_cliente} ({genero_cliente})")

    temp_file = "temp_fala.mp3"
    pieces = []
    current_time = 0
    
    for fala in falas:
        speaker = fala.get("speaker", "Cliente")
        texto = fala.get("text", "")
        if not texto: continue
        
        # Gera o mp3 temporario
        voz_atual = vozes_map.get(speaker, vozes_map["Cliente"])
        pitch_val = -2 if speaker == "Atendente" else 0
        await gerar_fala_minimax(texto, voz_atual, temp_file, pitch=pitch_val)
        
        if os.path.exists(temp_file):
            # Carrega e aplica filtro de telefone
            segment = AudioSegment.from_mp3(temp_file)
            segment = apply_telephone_filter(segment)
            
            # Ajuste de volume e humanização
            if speaker == "Cliente":
                segment = segment - 2 # reduz 2 dB
                
            # Lógica de interrupção (sobreposição)
            interrompe = fala.get("interrompe_anterior", False)
            if interrompe and current_time > 800:
                # Volta o tempo no máximo 800ms para criar a sobreposição ("atropelo" de voz)
                current_time -= random.randint(400, 800)
                
            pieces.append((segment, current_time))
            
            # Avança o tempo com a duração da fala + pausa
            pausa = random.randint(300, 900)
            if interrompe:
                pausa = 100 # Sem quase pausa se foi interrupção
            current_time += len(segment) + pausa
            
            os.remove(temp_file)
            
    # Cria um canvas de silêncio do tamanho total exato
    total_duration = current_time
    audio_final = AudioSegment.silent(duration=total_duration)
    
    # Cola todas as peças na timeline (suporta sobreposição perfeitamente)
    for seg, pos in pieces:
        audio_final = audio_final.overlay(seg, position=pos)
            
    # Adicionando ruído de fundo (Estática + Pink Noise para simular ambiente)
    print("  Aplicando ruído de fundo...")
    duracao_total = len(audio_final)
    
    # Gera ruído branco para o fundo (chiado do call center) e filtra
    ruido_fundo = WhiteNoise().to_audio_segment(duration=duracao_total)
    ruido_fundo = ruido_fundo.low_pass_filter(2000) # Deixa mais grave, parecendo pink noise/ambiente
    ruido_fundo = apply_telephone_filter(ruido_fundo)
    ruido_fundo = ruido_fundo - 35 # muito baixo, apenas pano de fundo
    
    # Gera uma estatíca (white noise) mais aguda baixinha para simular linha
    estatica = WhiteNoise().to_audio_segment(duration=duracao_total)
    estatica = estatica - 45
    
    # Sobrepõe
    audio_final = audio_final.overlay(ruido_fundo)
    audio_final = audio_final.overlay(estatica)
    
    audio_final.export(output_mp3_path, format="mp3")
    print(f"Audio salvo em: {output_mp3_path}")

async def main():
    pasta_roteiros = os.path.join("chamadas_simuladas", "roteiros")
    pasta_audios = os.path.join("chamadas_simuladas", "audios")
    
    if not os.path.exists(pasta_roteiros):
        print("Pasta de roteiros não encontrada.")
        return
        
    for arquivo in os.listdir(pasta_roteiros):
        if arquivo.endswith(".json"):
            json_path = os.path.join(pasta_roteiros, arquivo)
            mp3_nome = arquivo.replace(".json", ".mp3")
            output_path = os.path.join(pasta_audios, mp3_nome)
            
            if os.path.exists(output_path):
                print(f"Pulando {arquivo}, áudio já existe.")
                continue
                
            await processar_roteiro(json_path, output_path)

if __name__ == "__main__":
    asyncio.run(main())

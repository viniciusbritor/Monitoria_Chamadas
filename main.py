import os
import json
import sys
from core.transcriber import Transcriber
from core.evaluator import Evaluator
from secrets_manager import get_secret

def run_pilot(audio_dir, output_dir="results"):
    """
    Executa o piloto de processamento de chamadas.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Inicializa componentes
    transcriber = Transcriber()
    evaluator = Evaluator()

    # Busca arquivos de áudio
    files = [f for f in os.listdir(audio_dir) if f.endswith(('.mp3', '.wav', '.m4a'))]
    
    # Limite do piloto (se definido)
    limit = int(get_secret("PILOT_CALL_COUNT", "50"))
    files = files[:limit]

    print(f"🚀 Iniciando Piloto: {len(files)} chamadas para processar.")

    for i, filename in enumerate(files):
        print(f"\n--- [{i+1}/{len(files)}] Processando: {filename} ---")
        audio_path = os.path.join(audio_dir, filename)
        
        try:
            # 1. Transcrição (Custo Zero)
            transcript, segments = transcriber.transcribe(audio_path)
            
            # 2. Avaliação (Custo Gemini)
            evaluation = evaluator.evaluate(transcript)
            
            # 3. Consolidação de Resultados
            result = {
                "id": filename,
                "transcript": transcript,
                "segments": segments,
                "evaluation": evaluation
            }
            
            # Salva individualmente
            result_path = os.path.join(output_dir, f"{filename}.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            
            print(f"✅ Resultado salvo: {result_path}")
            print(f"📊 Nota: {evaluation.get('nota_geral', 'N/A')}")

        except Exception as e:
            print(f"❌ Falha ao processar {filename}: {e}")

    print("\n🏁 Piloto concluído!")
    print(f"Verifique a pasta '{output_dir}' para os resultados detalhados.")
    print("Consulte 'finops_usage.json' para o tracking de custos.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        audio_folder = sys.argv[1]
        run_pilot(audio_folder)
    else:
        print("Uso: python main.py <pasta_com_audios>")
        print("Dica: Crie uma pasta 'test_audios' e coloque alguns arquivos lá.")

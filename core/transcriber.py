import os
import time
from faster_whisper import WhisperModel
from secrets_manager import get_secret

class Transcriber:
    def __init__(self, model_size=None, device="cpu", compute_type="default"):
        """
        Inicializa o modelo Whisper.
        model_size: base, small, medium, large-v3
        device: cpu ou cuda
        """
        if model_size is None:
            model_size = get_secret("WHISPER_MODEL", "base")
        
        print(f"📦 Carregando modelo Whisper ({model_size}) no {device}...", flush=True)
        start_time = time.time()
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type, cpu_threads=2)
        print(f"✅ Modelo carregado em {time.time() - start_time:.2f}s")

    def transcribe(self, audio_path):
        """
        Transcreve um arquivo de áudio.
        Retorna o texto completo e os segmentos com timestamps.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

        print(f"🎙️ Transcrevendo: {os.path.basename(audio_path)}...")
        start_time = time.time()
        
        segments, info = self.model.transcribe(audio_path, beam_size=5, language="pt")
        
        full_text = []
        detailed_segments = []
        
        for segment in segments:
            text = segment.text.strip()
            full_text.append(text)
            detailed_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": text
            })
            print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {text}", flush=True)

        duration = time.time() - start_time
        print(f"✅ Transcrição concluída em {duration:.2f}s (Áudio de {info.duration:.2f}s)")
        
        return " ".join(full_text), detailed_segments

if __name__ == "__main__":
    # Teste simples
    import sys
    if len(sys.argv) > 1:
        t = Transcriber()
        text, _ = t.transcribe(sys.argv[1])
        print("\n--- Texto Extraído ---")
        print(text)
    else:
        print("Uso: python transcriber.py <caminho_do_audio>")

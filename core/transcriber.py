import os
import subprocess
import tempfile
import time
from faster_whisper import WhisperModel
from secrets_manager import get_secret


class Transcriber:
    def __init__(self, model_size=None, device="cpu", compute_type="default"):
        """
        Inicializa o modelo Whisper.
        model_size: base, small, medium, large-v3
        device: cpu ou cuda
        compute_type: default (float32) ou float16 (GPU), int8 (perde qualidade)
        """
        if model_size is None:
            model_size = get_secret("WHISPER_MODEL", "base")

        # Otimização: paralelismo CPU via OMP_NUM_THREADS e cpu_threads
        # faster-whisper usa CTranslate2 que paraleliza em CPU
        cpu_threads = int(os.getenv("OMP_NUM_THREADS", "2"))

        print(f"[Transcriber] Carregando modelo Whisper ({model_size}) no {device} (threads={cpu_threads})...", flush=True)
        start_time = time.time()
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=2,  # Otimização A: paralelismo de decode em CPU
            download_root=os.getenv("WHISPER_DOWNLOAD_ROOT", None),  # Cache local (pre-build)
        )
        print(f"[Transcriber] Modelo carregado em {time.time() - start_time:.2f}s", flush=True)

    def _preprocess_audio(self, audio_path: str) -> str:
        """
        Otimização B: Pré-processa áudio para mono 16kHz PCM (formato ideal para Whisper).
        Reduz trabalho do decoder. Usa ffmpeg que já está instalado no Dockerfile.
        Retorna o caminho do arquivo pré-processado (em /tmp).

        Timeout aumentado para 180s (era 60s) após incidente 03/07/2026 com audio
        WhatsApp .mpeg de 1MB que estourou mesmo sendo pequeno - causa raiz foi
        contencao de CPU com Whisper ja carregado em paralelo. Ver DIARIO_BORDO.
        """
        # Pula pre-processamento para arquivos >100MB (codec exotico arrisca timeout
        # OU problemas de memoria). Trade-off: audio bruto fica mais lento pro Whisper.
        try:
            size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            if size_mb > 100:
                print(f"[Transcriber] Audio grande ({size_mb:.1f}MB) - pulando pre-processamento", flush=True)
                return audio_path
        except OSError:
            pass

        if not audio_path.endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
            # Arquivos como .mpeg, .mp4, .aac precisam de conversão
            try:
                tmp_dir = tempfile.mkdtemp(prefix="audio_pre_")
                output_path = os.path.join(tmp_dir, "preprocessed.wav")
                cmd = [
                    "ffmpeg", "-y", "-i", audio_path,
                    "-ac", "1",       # mono
                    "-ar", "16000",   # 16kHz
                    "-sample_fmt", "s16",  # PCM 16-bit
                    "-f", "wav",
                    output_path
                ]
                try:
                    size_mb_str = f" ({os.path.getsize(audio_path) / (1024*1024):.2f}MB)"
                except OSError:
                    size_mb_str = ""
                print(f"[Transcriber] Pre-processando audio para mono 16kHz PCM{size_mb_str}...", flush=True)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode == 0 and os.path.exists(output_path):
                    print(f"[Transcriber] Pre-processamento concluido: {output_path}", flush=True)
                    return output_path
                else:
                    err_snip = (result.stderr or "")[:200]
                    print(f"[Transcriber] ffmpeg falhou (rc={result.returncode}), usando original: {err_snip}", flush=True)
                    return audio_path
            except subprocess.TimeoutExpired as e:
                print(f"[Transcriber] Pre-processamento TIMEOUT 180s (audio: {audio_path}), usando original", flush=True)
                return audio_path
            except FileNotFoundError as e:
                print(f"[Transcriber] ffmpeg nao encontrado ({e}), usando original", flush=True)
                return audio_path
        return audio_path

    def transcribe(self, audio_path):
        """
        Transcreve um arquivo de áudio.
        Retorna o texto completo e os segmentos com timestamps.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

        # Otimização B: pré-processar áudio
        processed_path = self._preprocess_audio(audio_path)

        print(f"[Transcriber] Transcrevendo: {os.path.basename(processed_path)}...", flush=True)
        start_time = time.time()

        segments, info = self.model.transcribe(
            processed_path,
            beam_size=5,
            language="pt",
            vad_filter=True,  # Filtro de silêncio (otimização bonus)
            vad_parameters=dict(min_silence_duration_ms=500),
        )

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
        print(f"[Transcriber] Transcricao concluida em {duration:.2f}s (Audio de {info.duration:.2f}s, ratio={duration/info.duration:.2f}x)", flush=True)

        # Cleanup arquivo temporário
        if processed_path != audio_path:
            try:
                os.remove(processed_path)
                os.rmdir(os.path.dirname(processed_path))
            except OSError:
                pass

        return " ".join(full_text), detailed_segments


def preload_model():
    """
    Otimização C: Pré-carregar modelo no startup do container.
    Salva 33s no primeiro upload.
    """
    print("[Transcriber] Pre-carregando modelo Whisper no startup...", flush=True)
    t = Transcriber()
    print("[Transcriber] Modelo pronto para uso", flush=True)
    return t


if __name__ == "__main__":
    # Teste simples
    import sys
    if len(sys.argv) > 1:
        t = Transcriber()
        text, _ = t.transcribe(sys.argv[1])
        print("\n--- Texto Extraido ---")
        print(text)
    else:
        print("Uso: python transcriber.py <caminho_do_audio>")
import os
import subprocess
import tempfile
import time
from faster_whisper import WhisperModel
from secrets_manager import get_secret


class Transcriber:
    def __init__(self, model_size=None, device="cpu", compute_type="int8"):
        """
        Inicializa o modelo Whisper.
        model_size: base, small, medium, large-v3
        device: cpu ou cuda
        compute_type: int8 (padrao, 2x speedup CPU), default (float32), float16 (GPU)

        HISTORICO:
        - 28/06/2026: int8 causava hang silencioso em Cloud Run CPU-only.
          Fix: OMP_NUM_THREADS=2 + compute_type=default.
        - 06/07/2026: Owner aprovou compute_type=int8 (2x speedup aceito).
          Mantido OMP_NUM_THREADS=2 para evitar o hang original.
          Loss de qualidade <1% WER segundo docs faster-whisper.
        """
        if model_size is None:
            # NEW (09/07/2026 - Batch/Standalone): default alterado de 'base' para 'large-v3'.
            # large-v3 e' ~2x mais rapido em CPU que 'base' e melhor qualidade.
            model_size = get_secret("WHISPER_MODEL", "large-v3")

        # Otimização: paralelismo CPU via OMP_NUM_THREADS e cpu_threads
        # faster-whisper usa CTranslate2 que paraleliza em CPU.
        # CRITICO: manter OMP_NUM_THREADS=2 mesmo com int8 (evita hang historico).
        cpu_threads = int(os.getenv("OMP_NUM_THREADS", "2"))

        print(f"[Transcriber] Carregando modelo Whisper ({model_size}) no {device} (compute_type={compute_type}, threads={cpu_threads})...", flush=True)
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
        Otimizacao B (05/07/2026): Pre-processa audio para mono 16kHz PCM
        (formato ideal para Whisper) via ffmpeg. Pula se ja esta' no formato
        alvo. Reduz trabalho do decoder e tempo total de transcricao.

        Mudancas 05/07/2026:
        - Detecta WAV PCM 16-bit @ 16kHz mono via ffprobe e pula ffmpeg
          (economiza ~5-30s por arquivo no caso comum).
        - Timeout mantido em 180s (DIARIO_BORDO 03/07 - contencao CPU).
        - Skip para arquivos >100MB (memoria).
        """
        # Skip pre-processamento para arquivos >100MB (codec exotico arrisca timeout
        # OU problemas de memoria). Trade-off: audio bruto fica mais lento pro Whisper.
        try:
            size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            if size_mb > 100:
                print(f"[Transcriber] Audio grande ({size_mb:.1f}MB) - pulando pre-processamento", flush=True)
                return audio_path
        except OSError:
            pass

        # NOVO (05/07/2026): detecta se ja' esta' no formato alvo via ffprobe.
        # WAV PCM s16 16kHz mono == formato nativo do Whisper, ffmpeg seria puro overhead.
        if audio_path.lower().endswith(".wav"):
            if self._is_native_whisper_format(audio_path):
                print(f"[Transcriber] WAV ja' em PCM s16 16kHz mono - pulando ffmpeg", flush=True)
                return audio_path

        # Para MP3/M4A/AAC/MPEG/Opus, mantem ffmpeg (codecs comprimidos precisam decode)
        if not audio_path.endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
            # Arquivos como .mpeg, .mp4, .aac precisam de conversao
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

    @staticmethod
    def _is_native_whisper_format(audio_path: str) -> bool:
        """Detecta se WAV ja' esta' em PCM s16 16kHz mono (formato nativo Whisper).

        Usa ffprobe. Retorna True se for nativo, False caso contrario
        (ou se ffprobe nao disponivel - fallback seguro = False, faz ffmpeg).
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,channels,sample_fmt,codec_name",
                "-of", "default=noprint_wrappers=1",
                audio_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return False
            out = result.stdout
            # Parse simples (key=value por linha)
            kv = {}
            for line in out.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    kv[k.strip()] = v.strip()
            return (
                kv.get("codec_name") == "pcm_s16le"
                and kv.get("sample_rate") == "16000"
                and kv.get("channels") == "1"
                and kv.get("sample_fmt") == "s16"
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    def transcribe(self, audio_path, on_progress=None, audio_duration_sec=None):
        """
        Transcreve um arquivo de audio.

        Args:
            audio_path: caminho do arquivo de audio.
            on_progress: callback opcional chamado por segmento com
                signature on_progress(segment_end: float, audio_duration_sec: float).
                Caller faz throttling para nao spammar DB.
            audio_duration_sec: duracao do audio em segundos (usada para
                calcular progress_pct). Se None, usa info.duration do Whisper.

        Retorna o texto completo e os segmentos com timestamps.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo nao encontrado: {audio_path}")

        # Otimizacao B: pre-processar audio
        processed_path = self._preprocess_audio(audio_path)

        print(f"[Transcriber] Transcrevendo: {os.path.basename(processed_path)}...", flush=True)
        start_time = time.time()

        segments, info = self.model.transcribe(
            processed_path,
            beam_size=5,
            language="pt",
            vad_filter=True,  # Filtro de silencio (otimizacao bonus)
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        full_text = []
        detailed_segments = []
        # Usa duracao passada se disponivel, senao usa info.duration do Whisper
        total_duration = audio_duration_sec if audio_duration_sec and audio_duration_sec > 0 else info.duration

        for segment in segments:
            text = segment.text.strip()
            full_text.append(text)
            detailed_segments.append({
                "start": segment.start,
                "end": segment.end,
                "text": text
            })
            print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {text}", flush=True)
            # Callback de progresso por segmento (caller faz throttle)
            if on_progress is not None:
                try:
                    on_progress(segment.end, total_duration)
                except Exception as e:
                    print(f"[Transcriber] on_progress callback falhou: {e}", flush=True)

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
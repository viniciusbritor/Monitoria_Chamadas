import os
import subprocess
import tempfile
import time
import requests
import json
import threading
from secrets_manager import get_secret


class Transcriber:
    def __init__(self, model_size=None, device="cpu", compute_type="int8"):
        """
        Inicializa o Transcriber híbrido:
        - Primário: Groq Cloud LPU (whisper-large-v3-turbo) - 100% Free Tier, ~2s de latência, WER < 5%.
        - Fallback: faster-whisper local (CTranslate2) em CPU (carregado sob demanda se Groq indisponível ou arquivo > 25MB).
        """
        self.model_size = model_size or get_secret("WHISPER_MODEL", "base")
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = int(os.getenv("OMP_NUM_THREADS", "4"))
        self._local_model = None
        self._lock = threading.Lock()
        
        # Chave da API Groq Cloud (Free Tier LPU)
        self.groq_api_key = os.getenv("GROQ_API_KEY") or get_secret("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
        self.groq_base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    def _get_local_model(self):
        """Inicialização sob demanda (lazy) do faster-whisper para economizar RAM e CPU."""
        with self._lock:
            if self._local_model is None:
                from faster_whisper import WhisperModel
                print(f"[Transcriber] Carregando faster-whisper local ({self.model_size}) no {self.device} (compute_type={self.compute_type}, threads={self.cpu_threads})...", flush=True)
                start_t = time.time()
                self._local_model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    cpu_threads=self.cpu_threads,
                    num_workers=1,
                    download_root=os.getenv("WHISPER_DOWNLOAD_ROOT", None),
                )
                print(f"[Transcriber] faster-whisper local pronto em {time.time() - start_t:.2f}s", flush=True)
            return self._local_model

    def _preprocess_audio(self, audio_path: str) -> str:
        """
        Pré-processa áudio para mono 16kHz PCM (formato ideal para Whisper) via ffmpeg.
        Pula se já está no formato nativo.
        """
        try:
            size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            if size_mb > 100:
                print(f"[Transcriber] Audio grande ({size_mb:.1f}MB) - pulando pre-processamento", flush=True)
                return audio_path
        except OSError:
            pass

        if audio_path.lower().endswith(".wav"):
            if self._is_native_whisper_format(audio_path):
                print(f"[Transcriber] WAV ja em PCM s16 16kHz mono - pulando ffmpeg", flush=True)
                return audio_path

        if not audio_path.endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
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
                print(f"[Transcriber] Pre-processando audio para mono 16kHz PCM...", flush=True)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode == 0 and os.path.exists(output_path):
                    print(f"[Transcriber] Pre-processamento concluido: {output_path}", flush=True)
                    return output_path
                else:
                    err_snip = (result.stderr or "")[:200]
                    print(f"[Transcriber] ffmpeg falhou (rc={result.returncode}), usando original: {err_snip}", flush=True)
                    return audio_path
            except subprocess.TimeoutExpired:
                print(f"[Transcriber] Pre-processamento TIMEOUT 180s, usando original", flush=True)
                return audio_path
            except FileNotFoundError:
                print(f"[Transcriber] ffmpeg nao encontrado, usando original", flush=True)
                return audio_path
        return audio_path

    @staticmethod
    def _is_native_whisper_format(audio_path: str) -> bool:
        """Detecta se WAV já está em PCM s16 16kHz mono."""
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
        except Exception:
            return False

    def _transcribe_groq(self, audio_path: str, on_progress=None, audio_duration_sec=None):
        """
        Transcreve áudio via Groq Cloud STT (whisper-large-v3-turbo em LPU).
        Retorna (full_text, detailed_segments) ou levanta Exception para acionar fallback.
        """
        api_key = self.groq_api_key or os.getenv("GROQ_API_KEY") or get_secret("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY nao configurada")

        size_bytes = os.path.getsize(audio_path)
        if size_bytes > 25 * 1024 * 1024:
            raise ValueError(f"Audio ({size_bytes / (1024*1024):.1f}MB) excede limite de 25MB da Groq API")

        url = f"{self.groq_base_url.rstrip('/')}/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {api_key.strip().lstrip('\ufeff')}",
        }

        ext = os.path.splitext(audio_path)[1].lower() or ".wav"
        mime_map = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
        mimetype = mime_map.get(ext, "audio/wav")

        print(f"[Transcriber] Chamando Groq Cloud STT ({self.groq_model})...", flush=True)
        start_t = time.time()

        with open(audio_path, "rb") as f:
            files = {
                "file": (f"audio{ext}", f, mimetype),
            }
            data = {
                "model": self.groq_model,
                "response_format": "verbose_json",
                "language": "pt",
                "temperature": "0.0",
            }
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)

        if resp.status_code != 200:
            err_msg = resp.text[:300]
            raise RuntimeError(f"Groq STT HTTP {resp.status_code}: {err_msg}")

        payload = resp.json()
        full_text = payload.get("text", "").strip()
        segments_raw = payload.get("segments") or []

        detailed_segments = []
        for s in segments_raw:
            text = str(s.get("text", "")).strip()
            if text:
                detailed_segments.append({
                    "start": float(s.get("start", 0.0)),
                    "end": float(s.get("end", 0.0)),
                    "text": text,
                })

        duration = time.time() - start_t
        audio_dur = payload.get("duration") or audio_duration_sec or 0.0
        print(f"[Transcriber] Groq STT OK em {duration:.2f}s ({len(detailed_segments)} segmentos, duracao: {audio_dur:.1f}s)", flush=True)

        if on_progress and audio_dur > 0:
            try:
                on_progress(audio_dur, audio_dur)
            except Exception as e:
                print(f"[Transcriber] on_progress Groq falhou: {e}", flush=True)

        return full_text, detailed_segments

    def _transcribe_local(self, processed_path: str, on_progress=None, audio_duration_sec=None):
        """Fallback de transcrição com faster-whisper local em CPU."""
        model = self._get_local_model()
        print(f"[Transcriber] Executando transcricao local (faster-whisper)...", flush=True)
        start_time = time.time()

        with self._lock:
            segments, info = model.transcribe(
                processed_path,
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                language="pt",
                vad_filter=False,
            )

            full_text = []
            detailed_segments = []
            total_duration = audio_duration_sec if audio_duration_sec and audio_duration_sec > 0 else info.duration

            for segment in segments:
                text = segment.text.strip()
                full_text.append(text)
                detailed_segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": text
                })
                if on_progress is not None:
                    try:
                        on_progress(segment.end, total_duration)
                    except Exception as e:
                        print(f"[Transcriber] on_progress local falhou: {e}", flush=True)

        duration = time.time() - start_time
        print(f"[Transcriber] faster-whisper local concluido em {duration:.2f}s (Audio de {info.duration:.2f}s)", flush=True)
        return " ".join(full_text), detailed_segments

    def transcribe(self, audio_path, on_progress=None, audio_duration_sec=None):
        """
        Transcreve um arquivo de áudio usando cascata:
        1. Groq Cloud (Whisper Large v3 Turbo - Gratuito, ~2s, alta precisão)
        2. Fallback: faster-whisper local em CPU (para arquivos >25MB ou falha de API)
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Arquivo nao encontrado: {audio_path}")

        processed_path = self._preprocess_audio(audio_path)

        # 1. Tentativa Primária: Groq Cloud LPU
        try:
            full_text, detailed_segments = self._transcribe_groq(
                processed_path,
                on_progress=on_progress,
                audio_duration_sec=audio_duration_sec,
            )
            # Cleanup temporário
            if processed_path != audio_path:
                try:
                    os.remove(processed_path)
                    os.rmdir(os.path.dirname(processed_path))
                except OSError:
                    pass
            return full_text, detailed_segments
        except Exception as e:
            print(f"[Transcriber] Groq Cloud STT indisponivel/falhou ({e}). Acionando fallback faster-whisper local...", flush=True)

        # 2. Fallback Local: faster-whisper
        full_text, detailed_segments = self._transcribe_local(
            processed_path,
            on_progress=on_progress,
            audio_duration_sec=audio_duration_sec,
        )

        if processed_path != audio_path:
            try:
                os.remove(processed_path)
                os.rmdir(os.path.dirname(processed_path))
            except OSError:
                pass

        return full_text, detailed_segments


def preload_model():
    """Pré-carrega o Transcriber no startup do container."""
    print("[Transcriber] Inicializando Transcriber no startup...", flush=True)
    t = Transcriber()
    return t


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        t = Transcriber()
        text, segs = t.transcribe(sys.argv[1])
        print("\n--- Texto Extraido ---")
        print(text)
        print(f"\n--- Segmentos ({len(segs)}) ---")
        for s in segs[:5]:
            print(f"[{s['start']:.2f}s -> {s['end']:.2f}s] {s['text']}")
    else:
        print("Uso: python transcriber.py <caminho_do_audio>")
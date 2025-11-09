"""
Edge-TTS Handler with Professional Audio Processing
แก้ปัญหา RVC noise/ช็อต/ซ่า อย่างสมบูรณ์
"""
import asyncio
import logging
from typing import Optional, Tuple
import numpy as np
import tempfile
from pathlib import Path
import soundfile as sf
import os

logger = logging.getLogger(__name__)

class EdgeTTSHandler:
    """
    Edge-TTS Handler with Audio Processing
    """
    
    def __init__(
        self,
        voice: str = "th-TH-PremwadeeNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz"
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        
        logger.info(f"✅ Edge-TTS initialized: {voice}")
    
    def _process_audio_pre_rvc(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Process audio ก่อนส่งเข้า RVC
        """
        try:
            logger.debug("   🔧 Pre-RVC processing...")
            
            # 1. Remove DC offset
            audio = audio - np.mean(audio)
            
            # 2. High-pass filter @ 80 Hz
            try:
                from scipy import signal
                nyquist = sr / 2
                cutoff = 80 / nyquist
                if 0 < cutoff < 1:
                    b, a = signal.butter(4, cutoff, btype='high')
                    audio = signal.filtfilt(b, a, audio)
                    logger.debug("   ✅ Pre-RVC high-pass applied")
            except Exception as e:
                logger.debug(f"   ⚠️ Pre-RVC filter skipped: {e}")
            
            # 3. Normalize to -3dB
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.707  # -3dB
            
            # 4. Soft clip
            audio = np.tanh(audio * 1.5) * 0.95
            
            return audio.astype(np.float32)
            
        except Exception as e:
            logger.warning(f"Pre-RVC processing error: {e}")
            return audio
    
    def _process_audio_post_rvc(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Process audio หลัง RVC (แก้ noise/ช็อต/ซ่า)
        """
        try:
            logger.debug("   🔧 Post-RVC processing...")
            
            # 1. Remove DC offset (สำคัญมาก!)
            audio = audio - np.mean(audio)
            
            # 2. High-pass filter @ 60 Hz (ตัด rumble)
            try:
                from scipy import signal
                nyquist = sr / 2
                cutoff = 100 / nyquist
                if 0 < cutoff < 1:
                    b, a = signal.butter(3, cutoff, btype='high')
                    audio = signal.filtfilt(b, a, audio)
                    logger.debug("   ✅ Post-RVC high-pass applied")
            except Exception as e:
                logger.debug(f"   ⚠️ Post-RVC filter skipped: {e}")
            
            # 3. De-emphasis (ลดเสียงแหลม/ช็อต)
            try:
                alpha = 0.97
                deemph = np.zeros_like(audio)
                deemph[0] = audio[0]
                for i in range(1, len(audio)):
                    deemph[i] = audio[i] + alpha * deemph[i-1]
                
                # Normalize
                max_val = np.abs(deemph).max()
                if max_val > 0:
                    audio = deemph / max_val * 0.85
                else:
                    audio = deemph
                
                logger.debug("   ✅ De-emphasis applied")
            except Exception as e:
                logger.debug(f"   ⚠️ De-emphasis skipped: {e}")
            
            # 4. Fade in/out (ป้องกัน pop/click)
            fade_ms = 10
            fade_samples = int(sr * fade_ms / 1000)
            
            if len(audio) > fade_samples * 2:
                fade_in = np.linspace(0, 1, fade_samples)
                audio[:fade_samples] *= fade_in
                
                fade_out = np.linspace(1, 0, fade_samples)
                audio[-fade_samples:] *= fade_out
                
                logger.debug("   ✅ Fade in/out applied")
            
            # 5. Final normalize
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.85  # -1.5dB headroom
            
            # 6. Soft limiter (final)
            audio = np.tanh(audio * 1.2) * 0.85
            
            return audio.astype(np.float32)
            
        except Exception as e:
            logger.warning(f"Post-RVC processing error: {e}")
            return audio
    
    async def generate_speech(
        self,
        text: str,
        output_path: Optional[Path] = None
    ) -> Tuple[Optional[np.ndarray], int]:
        """
        Generate speech from text
        """
        try:
            import edge_tts
            
            logger.info(f"🎤 Generating speech: '{text[:50]}...'")
            
            # Create temp file
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
                output_path = Path(temp_file.name)
                temp_file.close()
            
            # Generate speech
            communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch)
            await communicate.save(str(output_path))
            
            logger.info(f"✅ Speech generated: {output_path}")
            
            # Load audio
            audio, sr = sf.read(str(output_path))
            
            # Convert to mono
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            
            audio = audio.astype(np.float32)
            
            # Basic processing (แค่ normalize + DC offset)
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.95
            audio = audio - audio.mean()
            
            logger.info(f"   Duration: {len(audio)/sr:.2f}s, RMS: {np.sqrt(np.mean(audio**2)):.4f}")
            
            if np.abs(audio).max() < 0.001:
                logger.error("❌ Generated audio is SILENT!")
                return None, None
            
            return audio, sr
            
        except ImportError:
            logger.error("Edge-TTS not installed! Run: pip install edge-tts")
            return None, None
        except Exception as e:
            logger.error(f"Speech generation error: {e}", exc_info=True)
            return None, None
    
    async def generate_speech_with_rvc(
        self,
        text: str,
        rvc_model_path: Optional[Path] = None
    ) -> Tuple[Optional[np.ndarray], int]:
        """
        Generate speech with RVC + Audio Processing
        """
        try:
            # 1. Generate base audio
            audio, sr = await self.generate_speech(text)
            
            if audio is None:
                return None, None
            
            # 2. Check if RVC is enabled
            try:
                from core.config import config as core_config
            except Exception:
                core_config = None
            
            use_rvc = False
            server_url = None
            index_path = None
            pitch = 0
            device = 'cpu'
            
            if core_config is not None:
                use_rvc = getattr(core_config, 'ENABLE_RVC', False)
                rvc_model_path = Path(getattr(core_config, 'RVC_MODEL_PATH', str(rvc_model_path or 'rvc_models/jeed_anime.pth')))
                index_path = getattr(core_config, 'rvc').index_path if hasattr(core_config, 'rvc') else None
                server_url = getattr(core_config, 'rvc').__dict__.get('server_url', None) if hasattr(core_config, 'rvc') else None
                pitch = int(os.getenv('RVC_PITCH', '0'))
                device = getattr(core_config, 'RVC_DEVICE', 'cpu')
            
            # 3. Apply RVC if enabled
            if use_rvc and rvc_model_path and rvc_model_path.exists():
                try:
                    logger.info("🎵 Applying RVC with audio processing...")
                    
                    # === PRE-RVC PROCESSING ===
                    audio_pre = self._process_audio_pre_rvc(audio, sr)
                    
                    # === RVC CONVERSION ===
                    from audio.rvc_adapter import RVCAdapter
                    adapter = RVCAdapter(
                        server_url=server_url,
                        model_path=str(rvc_model_path),
                        index_path=index_path,
                        device=device,
                        pitch=pitch
                    )
                    
                    converted, out_sr = await adapter.convert(audio_pre, sr)
                    
                    if converted is not None:
                        # === POST-RVC PROCESSING ===
                        converted_clean = self._process_audio_post_rvc(converted, out_sr)
                        
                        logger.info("✅ RVC conversion with audio processing complete")
                        logger.info(f"   Final RMS: {np.sqrt(np.mean(converted_clean**2)):.4f}")
                        
                        return converted_clean, out_sr
                    else:
                        logger.warning("RVC conversion failed, returning base TTS audio")
                        
                except Exception as e:
                    logger.warning(f"RVC conversion error: {e}")
            
            return audio, sr
            
        except Exception as e:
            logger.error(f"RVC conversion error: {e}")
            return audio, sr
    
    @staticmethod
    async def list_voices(language: str = "th") -> list:
        """List available voices"""
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            filtered = [v for v in voices if v['Locale'].startswith(language)]
            return filtered
        except Exception as e:
            logger.error(f"Error listing voices: {e}")
            return []


async def text_to_speech(
    text: str,
    voice: str = "th-TH-PremwadeeNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> Tuple[Optional[np.ndarray], int]:
    """Convenience function for TTS"""
    tts = EdgeTTSHandler(voice=voice, rate=rate, pitch=pitch)
    return await tts.generate_speech(text)
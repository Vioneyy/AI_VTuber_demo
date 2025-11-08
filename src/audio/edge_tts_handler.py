"""
Edge-TTS Handler
- ฟรี 100%
- เสียงธรรมชาติมาก
- เร็วมาก (< 1 วินาที)
- ไม่มีปัญหาเสียงช็อต/ตื้ด/เงียบ
- รองรับภาษาไทย
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
    Edge-TTS Handler
    แก้ปัญหา:
    1. เสียงช็อตๆ/ตื้ด → Edge-TTS output สะอาด
    2. ไฟล์เงียบ → ไม่เกิดกับ Edge-TTS
    3. ช้า → Edge-TTS เร็วมาก
    """
    
    def __init__(
        self,
        voice: str = "th-TH-PremwadeeNeural",  # เสียงผู้หญิงไทย
        rate: str = "+0%",  # ความเร็วพูด
        pitch: str = "+0Hz"  # ระดับเสียง
    ):
        """
        Args:
            voice: Voice name
                Thai voices:
                - th-TH-PremwadeeNeural (Female)
                - th-TH-NiwatNeural (Male)
                - th-TH-AcharaNeural (Female)
            rate: Speech rate (-50% to +100%)
            pitch: Pitch adjustment (-50Hz to +50Hz)
        """
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        
        logger.info(f"✅ Edge-TTS initialized: {voice}")
    
    async def generate_speech(
        self,
        text: str,
        output_path: Optional[Path] = None
    ) -> Tuple[Optional[np.ndarray], int]:
        """
        Generate speech from text
        
        Args:
            text: Text to convert
            output_path: Optional output file path
        
        Returns:
            (audio_array, sample_rate) or (None, None)
        """
        try:
            import edge_tts
            
            logger.info(f"🎤 Generating speech: '{text[:50]}...'")
            
            # Create temp file if no output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(
                    suffix='.mp3',
                    delete=False
                )
                output_path = Path(temp_file.name)
                temp_file.close()
            
            # Generate speech
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                pitch=self.pitch
            )
            
            await communicate.save(str(output_path))
            
            logger.info(f"✅ Speech generated: {output_path}")
            
            # Load audio
            audio, sr = sf.read(str(output_path))
            
            # Convert to mono if stereo
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            
            # Ensure float32
            audio = audio.astype(np.float32)
            
            # Normalize
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.95
            
            # Remove DC offset
            audio = audio - audio.mean()
            
            logger.info(f"   Duration: {len(audio)/sr:.2f}s")
            logger.info(f"   Sample rate: {sr} Hz")
            logger.info(f"   RMS: {np.sqrt(np.mean(audio**2)):.4f}")
            
            # Check if audio is silent
            if np.abs(audio).max() < 0.001:
                logger.error("❌ Generated audio is SILENT!")
                return None, None
            
            return audio, sr
            
        except ImportError:
            logger.error("Edge-TTS not installed!")
            logger.error("Install: pip install edge-tts")
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
        Generate speech with RVC voice conversion
        
        Args:
            text: Text to convert
            rvc_model_path: Path to RVC model (optional)
        
        Returns:
            (audio_array, sample_rate) or (None, None)
        """
        try:
            # Generate base audio
            audio, sr = await self.generate_speech(text)
            
            if audio is None:
                return None, None
            
            # Apply RVC if enabled in config
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
            
            if use_rvc and rvc_model_path and rvc_model_path.exists():
                try:
                    logger.info("🎵 Applying RVC conversion...")
                    from audio.rvc_adapter import RVCAdapter
                    adapter = RVCAdapter(
                        server_url=server_url,
                        model_path=str(rvc_model_path),
                        index_path=index_path,
                        device=device,
                        pitch=pitch
                    )
                    converted, out_sr = await adapter.convert(audio, sr)
                    if converted is not None:
                        return converted, out_sr
                    else:
                        logger.warning("RVC conversion failed, returning base TTS audio")
                except Exception as e:
                    logger.warning(f"RVC conversion error: {e}")
            
            return audio, sr
            
        except Exception as e:
            logger.error(f"RVC conversion error: {e}")
            return audio, sr  # Return without RVC on error
    
    @staticmethod
    async def list_voices(language: str = "th") -> list:
        """
        List available voices
        
        Args:
            language: Language code (th, en, etc.)
        
        Returns:
            List of voice names
        """
        try:
            import edge_tts
            
            voices = await edge_tts.list_voices()
            
            # Filter by language
            filtered = [
                v for v in voices
                if v['Locale'].startswith(language)
            ]
            
            return filtered
            
        except Exception as e:
            logger.error(f"Error listing voices: {e}")
            return []


# Helper function
async def text_to_speech(
    text: str,
    voice: str = "th-TH-PremwadeeNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> Tuple[Optional[np.ndarray], int]:
    """
    Convenience function for TTS
    
    Args:
        text: Text to convert
        voice: Voice name
        rate: Speech rate
        pitch: Pitch adjustment
    
    Returns:
        (audio_array, sample_rate) or (None, None)
    """
    tts = EdgeTTSHandler(voice=voice, rate=rate, pitch=pitch)
    return await tts.generate_speech(text)


# Example usage and voice list
"""
Edge-TTS Usage:

1. Install:
   pip install edge-tts

2. Basic usage:
   from audio.edge_tts_handler import EdgeTTSHandler
   
   tts = EdgeTTSHandler(voice="th-TH-PremwadeeNeural")
   audio, sr = await tts.generate_speech("สวัสดีครับ")

3. List available Thai voices:
   voices = await EdgeTTSHandler.list_voices("th")
   for v in voices:
       print(f"{v['ShortName']}: {v['FriendlyName']}")

Thai Voices:
- th-TH-PremwadeeNeural (Female, Natural)
- th-TH-NiwatNeural (Male, Natural)
- th-TH-AcharaNeural (Female, Expressive)

Benefits:
✅ Free and unlimited
✅ High quality, natural voices
✅ Very fast (< 1 second)
✅ No silent output issues
✅ No distortion/artifacts
✅ Supports 100+ languages
✅ No API keys required
✅ Works offline after first download

Rate examples:
- "-50%" = Very slow
- "+0%" = Normal (default)
- "+50%" = Fast
- "+100%" = Very fast

Pitch examples:
- "-50Hz" = Lower voice
- "+0Hz" = Normal (default)
- "+50Hz" = Higher voice
"""
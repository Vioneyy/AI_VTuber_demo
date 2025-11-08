"""
Fixed TTS + RVC Handler
แก้ปัญหา:
1. Output เป็นไฟล์เงียบ
2. เสียงช็อต/ตื้ด
3. RVC ทำลายเสียง
"""
import numpy as np
import torch
import logging
from typing import Optional, Tuple
from pathlib import Path
import soundfile as sf
import asyncio

logger = logging.getLogger(__name__)

class FixedTTSRVCHandler:
    """
    TTS + RVC Handler ที่แก้ไขแล้ว
    """
    
    def __init__(
        self,
        tts_device: str = "cuda",
        rvc_device: str = "cuda",
        ref_audio_path: str = "reference_audio/jeed_voice.wav",
        rvc_model_path: Optional[str] = None
    ):
        """
        Args:
            tts_device: Device for TTS
            rvc_device: Device for RVC
            ref_audio_path: Reference audio for TTS
            rvc_model_path: RVC model path (optional)
        """
        # Check CUDA
        if tts_device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available for TTS, using CPU")
            tts_device = "cpu"
        
        if rvc_device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA not available for RVC, using CPU")
            rvc_device = "cpu"
        
        self.tts_device = tts_device
        self.rvc_device = rvc_device
        self.ref_audio_path = Path(ref_audio_path)
        
        # Load TTS
        self.tts_model = self._load_tts()
        
        # Load RVC (optional)
        self.rvc_model = None
        if rvc_model_path:
            self.rvc_model_path = Path(rvc_model_path)
            if self.rvc_model_path.exists():
                self.rvc_model = self._load_rvc()
            else:
                logger.warning(f"RVC model not found: {rvc_model_path}")
        
        logger.info(f"✅ TTS+RVC ready (TTS: {tts_device}, RVC: {rvc_device})")
    
    def _load_tts(self):
        """Load TTS model"""
        try:
            # Try F5-TTS-Thai first
            try:
                from f5_tts_th.tts import TTS
                
                logger.info("Loading F5-TTS-Thai...")
                
                model = TTS(
                    device=self.tts_device,
                    speed=1.0
                )
                
                logger.info("✅ F5-TTS-Thai loaded")
                return {'type': 'f5', 'model': model}
                
            except Exception as e:
                logger.warning(f"F5-TTS-Thai failed: {e}")
                logger.info("Falling back to Edge-TTS...")
                
                # Fallback to Edge-TTS
                return {'type': 'edge', 'model': None}
                
        except Exception as e:
            logger.error(f"Failed to load TTS: {e}")
            raise
    
    def _load_rvc(self):
        """Load RVC model"""
        try:
            # TODO: Implement actual RVC loading
            logger.info(f"Loading RVC model: {self.rvc_model_path}")
            
            # Placeholder: RVC loading code here
            logger.warning("RVC loading not implemented yet")
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to load RVC: {e}")
            return None
    
    async def generate_speech(
        self,
        text: str,
        apply_rvc: bool = True
    ) -> Tuple[Optional[np.ndarray], int]:
        """
        Generate speech with TTS + RVC
        
        Args:
            text: Text to convert
            apply_rvc: Whether to apply RVC
        
        Returns:
            (audio_array, sample_rate) or (None, None)
        """
        try:
            logger.info(f"🎤 Generating speech: '{text[:50]}...'")
            
            # 1. Generate with TTS
            if self.tts_model['type'] == 'f5':
                audio, sr = await self._generate_f5_tts(text)
            else:
                audio, sr = await self._generate_edge_tts(text)
            
            if audio is None:
                logger.error("TTS generation failed")
                return None, None
            
            # 2. Validate audio (แก้ปัญหาไฟล์เงียบ)
            if not self._validate_audio(audio):
                logger.error("Generated audio is invalid/silent!")
                return None, None
            
            logger.info(f"✅ TTS generated: {len(audio)/sr:.2f}s")
            
            # 3. Apply RVC if enabled and available
            if apply_rvc and self.rvc_model is not None:
                logger.info("🎵 Applying RVC...")
                audio = await self._apply_rvc(audio, sr)
                
                # Validate again after RVC
                if not self._validate_audio(audio):
                    logger.error("RVC destroyed audio! Using TTS output only")
                    # Re-generate without RVC
                    if self.tts_model['type'] == 'f5':
                        audio, sr = await self._generate_f5_tts(text)
                    else:
                        audio, sr = await self._generate_edge_tts(text)
            
            # 4. Post-process (แก้ปัญหาเสียงช็อต/ตื้ด)
            audio = self._post_process_audio(audio)
            
            # 5. Final validation
            if not self._validate_audio(audio):
                logger.error("Final audio is invalid!")
                return None, None
            
            logger.info(f"✅ Final audio ready: {len(audio)/sr:.2f}s, RMS={np.sqrt(np.mean(audio**2)):.4f}")
            
            return audio, sr
            
        except Exception as e:
            logger.error(f"Speech generation error: {e}", exc_info=True)
            return None, None
    
    async def _generate_f5_tts(self, text: str) -> Tuple[Optional[np.ndarray], int]:
        """Generate with F5-TTS"""
        try:
            model = self.tts_model['model']
            
            # Load reference audio
            if not self.ref_audio_path.exists():
                logger.error(f"Reference audio not found: {self.ref_audio_path}")
                return None, None
            
            ref_audio, ref_sr = sf.read(self.ref_audio_path)
            
            # Generate
            loop = asyncio.get_event_loop()
            audio = await loop.run_in_executor(
                None,
                model.generate,
                text,
                ref_audio,
                ref_sr
            )
            
            # F5-TTS output is usually at 22050 Hz
            return audio, 22050
            
        except Exception as e:
            logger.error(f"F5-TTS generation error: {e}")
            return None, None
    
    async def _generate_edge_tts(self, text: str) -> Tuple[Optional[np.ndarray], int]:
        """Generate with Edge-TTS (fallback)"""
        try:
            import edge_tts
            import tempfile
            
            # Generate to temp file
            temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            temp_path = Path(temp_file.name)
            temp_file.close()
            
            # Generate
            communicate = edge_tts.Communicate(
                text,
                "th-TH-PremwadeeNeural"  # Thai female voice
            )
            
            await communicate.save(str(temp_path))
            
            # Load audio
            audio, sr = sf.read(str(temp_path))
            
            # Cleanup
            temp_path.unlink(missing_ok=True)
            
            # Convert to mono
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            
            return audio.astype(np.float32), sr
            
        except Exception as e:
            logger.error(f"Edge-TTS generation error: {e}")
            return None, None
    
    async def _apply_rvc(
        self,
        audio: np.ndarray,
        sample_rate: int
    ) -> np.ndarray:
        """Apply RVC voice conversion"""
        try:
            # TODO: Implement actual RVC conversion
            logger.warning("RVC conversion not implemented yet")
            return audio
            
        except Exception as e:
            logger.error(f"RVC error: {e}")
            return audio
    
    def _validate_audio(self, audio: Optional[np.ndarray]) -> bool:
        """
        Validate audio (แก้ปัญหาไฟล์เงียบ)
        
        Args:
            audio: Audio array
        
        Returns:
            True if valid
        """
        if audio is None:
            return False
        
        if len(audio) == 0:
            logger.error("Audio is empty")
            return False
        
        # Check for silence
        rms = np.sqrt(np.mean(audio**2))
        max_val = np.abs(audio).max()
        
        if max_val < 0.001:
            logger.error(f"Audio is silent! max={max_val:.6f}")
            return False
        
        if rms < 0.001:
            logger.error(f"Audio RMS too low! rms={rms:.6f}")
            return False
        
        # Check for NaN/Inf
        if np.isnan(audio).any():
            logger.error("Audio contains NaN")
            return False
        
        if np.isinf(audio).any():
            logger.error("Audio contains Inf")
            return False
        
        return True
    
    def _post_process_audio(self, audio: np.ndarray) -> np.ndarray:
        """
        Post-process audio (แก้ปัญหาเสียงช็อต/ตื้ด)
        
        Args:
            audio: Raw audio
        
        Returns:
            Processed audio
        """
        try:
            # 1. Remove DC offset
            audio = audio - audio.mean()
            
            # 2. Normalize (ป้องกันเสียงเบาหรือดังเกินไป)
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.95
            
            # 3. Apply soft clipping (ป้องกันเสียงช็อต/distortion)
            audio = np.tanh(audio * 1.5) / 1.5
            
            # 4. Smooth edges (ป้องกันเสียงตื้ด)
            fade_samples = int(0.01 * 22050)  # 10ms fade
            
            if len(audio) > fade_samples * 2:
                # Fade in
                fade_in = np.linspace(0, 1, fade_samples)
                audio[:fade_samples] *= fade_in
                
                # Fade out
                fade_out = np.linspace(1, 0, fade_samples)
                audio[-fade_samples:] *= fade_out
            
            # 5. Final normalization
            max_val = np.abs(audio).max()
            if max_val > 0:
                audio = audio / max_val * 0.95
            
            return audio
            
        except Exception as e:
            logger.error(f"Post-processing error: {e}")
            return audio
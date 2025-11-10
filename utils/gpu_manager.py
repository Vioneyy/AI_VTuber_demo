"""
GPU Memory Manager
แก้ไขปัญหา:
1. TTS/STT แย่ง VRAM
2. OOM errors
3. GPU queue conflicts
"""
import torch
import logging
from typing import Optional, Dict
from contextlib import contextmanager
import gc

logger = logging.getLogger(__name__)

class GPUMemoryManager:
    """จัดการ GPU memory สำหรับโมดูลต่างๆ"""
    
    def __init__(self):
        """Initialize GPU manager"""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.devices_count = torch.cuda.device_count() if self.device == "cuda" else 0
        
        if self.device == "cuda":
            logger.info(f"✅ CUDA available: {self.devices_count} device(s)")
            for i in range(self.devices_count):
                props = torch.cuda.get_device_properties(i)
                total_memory = props.total_memory / 1024**3  # GB
                logger.info(f"   GPU {i}: {props.name}, {total_memory:.1f}GB VRAM")
        else:
            logger.warning("⚠️  CUDA not available, using CPU")
        
        # Track memory usage
        self.memory_allocated = {}
        self.last_cleanup = 0
    
    def get_optimal_device_assignment(self) -> Dict[str, str]:
        """
        กำหนด device ที่เหมาะสมสำหรับแต่ละโมดูล
        
        Returns:
            Dict ของ module -> device
        """
        if self.device == "cpu":
            return {
                'stt': 'cpu',
                'tts': 'cpu',
                'llm': 'cpu'
            }
        
        # ถ้ามี GPU เดียว - ใช้ร่วมกัน
        if self.devices_count == 1:
            return {
                'stt': 'cuda:0',
                'tts': 'cuda:0',
                'llm': 'cpu'  # LLM ใช้ API ไม่ต้อง GPU
            }
        
        # ถ้ามี GPU หลายตัว - แยกโมดูล
        if self.devices_count >= 2:
            return {
                'stt': 'cuda:0',
                'tts': 'cuda:1',
                'llm': 'cpu'
            }
        
        return {
            'stt': self.device,
            'tts': self.device,
            'llm': 'cpu'
        }
    
    def get_memory_stats(self, device: int = 0) -> Dict[str, float]:
        """
        ดูสถานะ memory
        
        Args:
            device: GPU device index
        
        Returns:
            Dict ของ memory stats (GB)
        """
        if self.device == "cpu":
            return {
                'allocated': 0,
                'reserved': 0,
                'free': 0,
                'total': 0
            }
        
        try:
            allocated = torch.cuda.memory_allocated(device) / 1024**3
            reserved = torch.cuda.memory_reserved(device) / 1024**3
            total = torch.cuda.get_device_properties(device).total_memory / 1024**3
            free = total - allocated
            
            return {
                'allocated': allocated,
                'reserved': reserved,
                'free': free,
                'total': total
            }
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {}
    
    def print_memory_stats(self, device: int = 0):
        """แสดงสถานะ memory"""
        stats = self.get_memory_stats(device)
        if stats:
            logger.info(
                f"GPU {device} Memory: "
                f"Allocated={stats['allocated']:.2f}GB, "
                f"Reserved={stats['reserved']:.2f}GB, "
                f"Free={stats['free']:.2f}GB, "
                f"Total={stats['total']:.2f}GB"
            )
    
    def cleanup(self, device: Optional[int] = None):
        """
        ทำความสะอาด GPU memory
        
        Args:
            device: GPU device index (None = all devices)
        """
        if self.device == "cpu":
            return
        
        try:
            # Python garbage collection
            gc.collect()
            
            # PyTorch cache cleanup
            if device is None:
                torch.cuda.empty_cache()
                for i in range(self.devices_count):
                    torch.cuda.synchronize(i)
            else:
                torch.cuda.empty_cache()
                torch.cuda.synchronize(device)
            
            logger.debug("GPU memory cleanup completed")
            
        except Exception as e:
            logger.error(f"GPU cleanup failed: {e}")
    
    def auto_cleanup_if_needed(self, threshold_gb: float = 1.0):
        """
        ทำความสะอาดอัตโนมัติถ้า memory เหลือน้อย
        
        Args:
            threshold_gb: Cleanup ถ้า free memory < threshold
        """
        if self.device == "cpu":
            return
        
        try:
            stats = self.get_memory_stats(0)
            if stats['free'] < threshold_gb:
                logger.warning(
                    f"Low GPU memory: {stats['free']:.2f}GB free, "
                    f"running cleanup..."
                )
                self.cleanup()
                
                # Check again
                stats_after = self.get_memory_stats(0)
                logger.info(
                    f"After cleanup: {stats_after['free']:.2f}GB free "
                    f"(freed {stats_after['free'] - stats['free']:.2f}GB)"
                )
        except Exception as e:
            logger.error(f"Auto cleanup failed: {e}")
    
    @contextmanager
    def managed_memory(self, module_name: str = "unknown", device: int = 0):
        """
        Context manager สำหรับจัดการ memory
        
        Usage:
            with gpu_manager.managed_memory('stt'):
                # Your GPU operations
                result = model(input)
        """
        if self.device == "cpu":
            yield
            return
        
        try:
            # Log before
            logger.debug(f"[{module_name}] Starting GPU operation")
            stats_before = self.get_memory_stats(device)
            
            yield
            
            # Log after
            stats_after = self.get_memory_stats(device)
            used = stats_after['allocated'] - stats_before['allocated']
            logger.debug(
                f"[{module_name}] Completed. "
                f"Used {used:.3f}GB, "
                f"Free {stats_after['free']:.2f}GB"
            )
            
        finally:
            # Cleanup if needed
            self.auto_cleanup_if_needed(threshold_gb=1.0)
    
    def set_memory_fraction(self, fraction: float = 0.8, device: int = 0):
        """
        จำกัด memory ที่ PyTorch ใช้ได้
        
        Args:
            fraction: สัดส่วนของ total memory (0.0-1.0)
            device: GPU device index
        """
        if self.device == "cpu":
            return
        
        try:
            torch.cuda.set_per_process_memory_fraction(fraction, device)
            logger.info(
                f"Set GPU {device} memory fraction to {fraction*100:.0f}%"
            )
        except Exception as e:
            logger.error(f"Failed to set memory fraction: {e}")
    
    def enable_memory_optimization(self):
        """เปิดการ optimize memory"""
        if self.device == "cpu":
            return
        
        try:
            # Enable cuDNN auto-tuner
            torch.backends.cudnn.benchmark = True
            
            # Enable TF32 on Ampere GPUs
            if torch.cuda.get_device_capability()[0] >= 8:
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                logger.info("✅ TF32 enabled")
            
            logger.info("✅ Memory optimization enabled")
            
        except Exception as e:
            logger.error(f"Failed to enable memory optimization: {e}")
    
    def check_oom_risk(self, required_gb: float, device: int = 0) -> bool:
        """
        ตรวจสอบความเสี่ยง Out of Memory
        
        Args:
            required_gb: Memory ที่ต้องการ (GB)
            device: GPU device index
        
        Returns:
            True ถ้ามีความเสี่ยง OOM
        """
        if self.device == "cpu":
            return False
        
        stats = self.get_memory_stats(device)
        free_memory = stats['free']
        
        # เผื่อไว้ 20%
        safety_margin = required_gb * 1.2
        
        if free_memory < safety_margin:
            logger.warning(
                f"OOM Risk: Need {required_gb:.2f}GB, "
                f"Free {free_memory:.2f}GB"
            )
            return True
        
        return False


# Global instance
_gpu_manager = None

def get_gpu_manager() -> GPUMemoryManager:
    """Get global GPU manager instance"""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUMemoryManager()
    return _gpu_manager


# Helper functions
def cleanup_gpu():
    """Cleanup GPU memory"""
    manager = get_gpu_manager()
    manager.cleanup()

def print_gpu_stats():
    """Print GPU statistics"""
    manager = get_gpu_manager()
    manager.print_memory_stats()

def get_device_for(module: str) -> str:
    """
    Get optimal device for module
    
    Args:
        module: Module name ('stt', 'tts', 'llm')
    
    Returns:
        Device string (e.g., 'cuda:0' or 'cpu')
    """
    manager = get_gpu_manager()
    assignments = manager.get_optimal_device_assignment()
    return assignments.get(module, 'cpu')
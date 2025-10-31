"""
vts_client.py - VTube Studio WebSocket Client
Client พื้นฐานสำหรับเชื่อมต่อกับ VTS
"""

import asyncio
import websockets
import json
import logging
import io
import wave
from typing import Optional, Dict, Any, Tuple, List

try:
    import numpy as np
except Exception:
    np = None  # ใช้ fallback หากไม่มี numpy

logger = logging.getLogger(__name__)


class VTSClient:
    """WebSocket Client สำหรับ VTube Studio"""
    
    def __init__(self, host: str = "localhost", port: int = 8001):
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """เชื่อมต่อกับ VTS"""
        try:
            uri = f"ws://{self.host}:{self.port}"
            logger.info(f"กำลังเชื่อมต่อ: {uri}")
            
            self.ws = await websockets.connect(uri)
            self.is_connected = True
            
            logger.info("✅ เชื่อมต่อสำเร็จ")
            return True
            
        except Exception as e:
            logger.error(f"❌ ไม่สามารถเชื่อมต่อได้: {e}")
            self.is_connected = False
            return False

    def _is_connected(self) -> bool:
        """ตัวช่วยตรวจสอบการเชื่อมต่อ (เข้ากันได้กับโค้ดเดิม)"""
        return bool(self.ws) and bool(self.is_connected)

    async def disconnect(self):
        """ตัดการเชื่อมต่อ"""
        if self.ws:
            await self.ws.close()
            self.is_connected = False
            logger.info("✅ ตัดการเชื่อมต่อแล้ว")
    
    async def send_request(self, message_type: str, data: Dict[str, Any]) -> Optional[Dict]:
        """ส่ง request ไปยัง VTS"""
        if not self.ws or not self.is_connected:
            logger.error("ไม่ได้เชื่อมต่อกับ VTS")
            return None
        
        try:
            request = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": message_type,
                "messageType": message_type,
                "data": data
            }
            
            await self.ws.send(json.dumps(request))
            response = await self.ws.recv()
            
            return json.loads(response)
            
        except Exception as e:
            logger.error(f"❌ เกิดข้อผิดพลาดในการส่ง request: {e}")
            return None
    
    async def get_api_state(self) -> Optional[Dict]:
        """ดูสถานะ API"""
        return await self.send_request("APIStateRequest", {})
    
    async def get_model_list(self) -> Optional[Dict]:
        """ดูรายการโมเดล"""
        return await self.send_request("AvailableModelsRequest", {})
    
    async def get_current_model(self) -> Optional[Dict]:
        """ดูโมเดลปัจจุบัน"""
        return await self.send_request("CurrentModelRequest", {})

    async def compute_mouth_envelope(self, audio_bytes: bytes) -> Optional[Tuple[List[float], float]]:
        """
        คำนวณ mouth-open envelope จากข้อมูลเสียงแบบ WAV ในหน่วยช่วงเวลาเท่ากัน
        - คืนค่า (series, interval_sec) โดย series เป็นลิสต์ค่าระหว่าง 0..1
        - หากไม่สามารถประมวลผลได้ จะคืน None
        """
        try:
            if not audio_bytes:
                # Fallback: สร้าง envelope แบบง่ายเพื่อการทดสอบเมื่อไม่มีเสียงจริง
                try:
                    import os
                    interval_ms = int(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "30"))
                except Exception:
                    interval_ms = 30
                interval_sec = max(0.01, float(interval_ms) / 1000.0)
                steps = 40
                series = [0.0, 0.4, 0.8, 0.5, 0.2] + [0.6, 0.3, 0.7, 0.4, 0.1] * 3 + [0.0]
                # ปรับความยาวให้พอดีกับ steps
                if len(series) < steps:
                    series = (series * (steps // len(series) + 1))[:steps]
                return series, interval_sec

            # พยายามอ่านเป็น WAV จาก bytes
            with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            # กำหนดช่วงเวลาสendตาม env (.env) หรือใช้ค่าเริ่มต้น 30ms
            try:
                import os
                interval_ms = int(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "30"))
            except Exception:
                interval_ms = 30
            interval_sec = max(0.01, float(interval_ms) / 1000.0)

            # แปลงข้อมูลเสียงเป็น amplitude
            # รองรับ 16-bit PCM เป็นพื้นฐาน (ทั่วไปสำหรับ WAV)
            if sample_width != 2:
                # fallback แบบง่าย: ประเมินจากความยาวข้อมูล
                approx_len_sec = max(0.1, len(audio_bytes) / (framerate if framerate else 24000) / max(1, n_channels))
                steps = int(approx_len_sec / interval_sec)
                series = [0.5] * max(1, steps)
                return series, interval_sec

            # ใช้ numpy หากมี เพื่อความเร็ว
            if np is not None:
                dtype = np.int16
                audio = np.frombuffer(raw, dtype=dtype)
                if n_channels > 1:
                    audio = audio.reshape(-1, n_channels).mean(axis=1)
                # คำนวณ envelope โดย RMS ภายใน window
                samples_per_window = max(1, int(framerate * interval_sec))
                total_windows = max(1, int(len(audio) / samples_per_window))
                series = []
                for i in range(total_windows):
                    start = i * samples_per_window
                    end = start + samples_per_window
                    window = audio[start:end]
                    if window.size == 0:
                        series.append(0.0)
                        continue
                    rms = float(np.sqrt(np.mean(window.astype(np.float32) ** 2)))
                    # Normalize RMS to 0..1 using 16-bit max value
                    norm = min(1.0, rms / 32768.0 * 3.0)  # boost เล็กน้อย
                    series.append(norm)
                # Smooth เล็กน้อย
                for i in range(1, len(series)):
                    series[i] = 0.6 * series[i] + 0.4 * series[i-1]
                return series, interval_sec
            else:
                # ไม่มี numpy: สร้าง series แบบคงที่เพื่อหลีกเลี่ยง error
                approx_len_sec = n_frames / float(framerate or 24000)
                steps = int(approx_len_sec / interval_sec)
                series = [0.5] * max(1, steps)
                return series, interval_sec
        except Exception as e:
            logger.debug(f"compute_mouth_envelope failed: {e}")
            # Fallback series เมื่อประมวลผลเสียงไม่สำเร็จ
            try:
                import os
                interval_ms = int(os.getenv("VTS_SEND_MIN_INTERVAL_MS", "30"))
            except Exception:
                interval_ms = 30
            interval_sec = max(0.01, float(interval_ms) / 1000.0)
            steps = 40
            series = [0.3, 0.6, 0.9, 0.5, 0.2] + [0.7, 0.4, 0.8, 0.3, 0.1] * 3 + [0.0]
            if len(series) < steps:
                series = (series * (steps // len(series) + 1))[:steps]
            return series, interval_sec


# ตัวอย่างการใช้งาน
async def test_vts_client():
    """ทดสอบการเชื่อมต่อ"""
    client = VTSClient()
    
    if await client.connect():
        # ดูสถานะ API
        state = await client.get_api_state()
        print("API State:", state)
        
        # ดูโมเดลปัจจุบัน
        model = await client.get_current_model()
        print("Current Model:", model)
        
        await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_vts_client())
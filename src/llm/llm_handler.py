"""
จัดการ LLM (ChatGPT) พร้อมบุคลิกภาพ
ตำแหน่ง: src/llm/llm_handler.py (แทนที่ chatgpt_client.py)
ลบไฟล์: prompts/system_prompt.txt (ย้ายไปอยู่ใน jeed_persona.py แล้ว)
"""

import asyncio
import time
from typing import Optional, List, Dict
import openai
from openai import AsyncOpenAI

import sys
sys.path.append('..')
from core.config import config
from personality.jeed_persona import JeedPersona, Emotion

class LLMHandler:
    """จัดการ LLM และสร้างคำตอบ"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.llm.api_key)
        self.conversation_history: List[Dict] = []
        self.max_history = 10  # เก็บประวัติ 10 ข้อความล่าสุด
        
        # Statistics
        self.total_requests = 0
        self.total_tokens = 0
        self.avg_response_time = 0
        
    async def generate_response(self, user_message: str, retry: int = 2) -> Optional[str]:
        """
        สร้างคำตอบจาก LLM
        Args:
            user_message: ข้อความจากผู้ใช้
            retry: จำนวนครั้งที่พยายามใหม่
        Returns:
            คำตอบ หรือ None ถ้าล้มเหลว
        """
        start_time = time.time()
        
        try:
            # เพิ่มข้อความเข้าประวัติ
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })
            
            # ตัดประวัติเก่า
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]
            
            # สร้าง messages
            messages = [
                {"role": "system", "content": JeedPersona.SYSTEM_PROMPT}
            ] + self.conversation_history
            
            # เรียก API
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=config.llm.model,
                    messages=messages,
                    max_tokens=config.llm.max_tokens,
                    temperature=config.llm.temperature,
                    presence_penalty=config.llm.presence_penalty,
                    frequency_penalty=config.llm.frequency_penalty
                ),
                timeout=config.llm.timeout
            )
            
            # ดึงคำตอบ
            assistant_message = response.choices[0].message.content.strip()
            
            # ทำความสะอาด
            assistant_message = JeedPersona.clean_response(assistant_message)
            
            # ตรวจสอบความถูกต้อง
            is_valid, error = JeedPersona.validate_response(assistant_message)
            
            if not is_valid:
                print(f"⚠️ คำตอบไม่ถูกต้อง: {error}")
                if retry > 0:
                    print(f"🔄 ลองใหม่... (เหลือ {retry} ครั้ง)")
                    return await self.generate_response(user_message, retry - 1)
                else:
                    assistant_message = "เอ๊ะ หนูงงนิดนึง ลองถามใหม่ได้ไหม~"
            
            # เพิ่มคำตอบเข้าประวัติ
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            # อัพเดทสถิติ
            elapsed = time.time() - start_time
            self.total_requests += 1
            self.total_tokens += response.usage.total_tokens
            self.avg_response_time = (
                (self.avg_response_time * (self.total_requests - 1) + elapsed) 
                / self.total_requests
            )
            
            print(f"🤖 LLM Response ({elapsed:.2f}s, {response.usage.total_tokens} tokens)")
            print(f"   '{assistant_message[:100]}...'")
            
            return assistant_message
            
        except asyncio.TimeoutError:
            print(f"⏰ LLM Timeout ({config.llm.timeout}s)")
            if retry > 0:
                return await self.generate_response(user_message, retry - 1)
            return "เอ๊ะ หนูตอบช้าไปหน่อย ขอโทษนะ ลองถามใหม่ได้ไหม~"
            
        except openai.APIError as e:
            print(f"❌ OpenAI API Error: {e}")
            if retry > 0:
                await asyncio.sleep(1)
                return await self.generate_response(user_message, retry - 1)
            return "อุ๊ปส์ มีปัญหานิดหน่อย ลองใหม่อีกทีนะ~"
            
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            return "เอ๊ะ มีอะไรผิดพลาด ขอโทษนะ~"
    
    def clear_history(self):
        """ล้างประวัติการสนทนา"""
        self.conversation_history = []
        print("🗑️ ล้างประวัติการสนทนา")
    
    def get_stats(self) -> Dict:
        """ดูสถิติ"""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "avg_response_time": self.avg_response_time,
            "history_size": len(self.conversation_history)
        }
    
    def print_stats(self):
        """แสดงสถิติ"""
        stats = self.get_stats()
        print("\n" + "="*50)
        print("🤖 LLM Statistics")
        print("="*50)
        print(f"Total Requests: {stats['total_requests']}")
        print(f"Total Tokens: {stats['total_tokens']}")
        print(f"Avg Response Time: {stats['avg_response_time']:.2f}s")
        print(f"History Size: {stats['history_size']}")
        print("="*50 + "\n")

# Global LLM handler
llm_handler = LLMHandler()
"""
admin_commands.py - Admin Command System
ระบบคำสั่งสำหรับ admin
"""

import logging
import os
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AdminUser:
    """ข้อมูล admin user"""
    user_id: str
    username: str
    role: str  # "owner", "moderator"


class AdminCommandHandler:
    """จัดการคำสั่ง admin"""
    
    def __init__(self):
        # โหลด admin IDs จาก .env
        self.owner_ids = self._load_admin_ids("OWNER_IDS")
        self.moderator_ids = self._load_admin_ids("MODERATOR_IDS")
        
        # คำสั่งที่มี
        self.commands = {
            "approve": self.cmd_approve,
            "reject": self.cmd_reject,
            "status": self.cmd_status,
            "queue": self.cmd_queue,
            "skip": self.cmd_skip,
            "unlock": self.cmd_unlock,
            "lock": self.cmd_lock,
            # เพิ่มคำสั่งควบคุมการรับคิวจาก youtube/voice
            "yt_on": self.cmd_youtube_on,
            "yt_off": self.cmd_youtube_off,
            "voice_on": self.cmd_voice_on,
            "voice_off": self.cmd_voice_off,
        }
        
        # Secret unlock code
        self.unlock_code = os.getenv("UNLOCK_CODE", "unlock123")
        self.is_unlocked = False
    
    def _load_admin_ids(self, env_key: str) -> List[str]:
        """โหลด admin IDs จาก .env"""
        ids_str = os.getenv(env_key, "")
        if not ids_str:
            return []
        return [id.strip() for id in ids_str.split(",")]
    
    def is_owner(self, user_id: str) -> bool:
        """เช็คว่าเป็น owner หรือไม่"""
        return user_id in self.owner_ids
    
    def is_moderator(self, user_id: str) -> bool:
        """เช็คว่าเป็น moderator หรือไม่"""
        return user_id in self.moderator_ids or self.is_owner(user_id)
    
    def is_admin(self, user_id: str) -> bool:
        """เช็คว่าเป็น admin (owner หรือ moderator)"""
        return self.is_moderator(user_id)
    
    async def handle_command(
        self,
        command: str,
        args: List[str],
        user_id: str,
        context: dict
    ) -> Optional[str]:
        """
        ประมวลผลคำสั่ง admin
        
        Args:
            command: ชื่อคำสั่ง
            args: arguments
            user_id: ID ของผู้ใช้
            context: context เพิ่มเติม (safety_filter, queue_manager, etc.)
        
        Returns:
            response message หรือ None
        """
        # เช็คสิทธิ์
        if not self.is_admin(user_id):
            return "❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้"
        
        # เรียกใช้คำสั่ง
        if command in self.commands:
            try:
                return await self.commands[command](args, user_id, context)
            except Exception as e:
                logger.error(f"❌ Command error: {e}", exc_info=True)
                return f"❌ เกิดข้อผิดพลาด: {e}"
        else:
            return f"❌ ไม่พบคำสั่ง: {command}"
    
    async def cmd_approve(self, args: List[str], user_id: str, context: dict) -> str:
        """อนุมัติ approval request"""
        if len(args) < 1:
            return "❌ ใช้: !approve <approval_id>"
        
        approval_id = args[0]
        safety_filter = context.get("safety_filter")
        
        if not safety_filter:
            return "❌ Safety filter ไม่พร้อม"
        
        success = safety_filter.approve_request(approval_id, approved=True)
        if success:
            return f"✅ อนุมัติแล้ว: {approval_id}"
        else:
            return f"❌ ไม่พบ approval ID: {approval_id}"
    
    async def cmd_reject(self, args: List[str], user_id: str, context: dict) -> str:
        """ปฏิเสธ approval request"""
        if len(args) < 1:
            return "❌ ใช้: !reject <approval_id>"
        
        approval_id = args[0]
        safety_filter = context.get("safety_filter")
        
        if not safety_filter:
            return "❌ Safety filter ไม่พร้อม"
        
        success = safety_filter.approve_request(approval_id, approved=False)
        if success:
            return f"✅ ปฏิเสธแล้ว: {approval_id}"
        else:
            return f"❌ ไม่พบ approval ID: {approval_id}"
    
    async def cmd_status(self, args: List[str], user_id: str, context: dict) -> str:
        """ดูสถานะระบบ"""
        queue_manager = context.get("queue_manager")
        safety_filter = context.get("safety_filter")
        
        status_lines = ["📊 **สถานะระบบ**"]
        
        if queue_manager:
            status = queue_manager.get_stats()
            status_lines.extend([
                f"- คิว: {status['queue_size']} ข้อความ",
                f"- กำลังประมวลผล: {'✅' if status['processing'] else '❌'}",
                f"- ประมวลผลแล้ว: {status['total_processed']} ข้อความ",
                f"- ทิ้งไป: {status['total_dropped']}"
            ])
        
        if safety_filter:
            pending = safety_filter.get_pending_approvals()
            status_lines.append(f"- รออนุมัติ: {len(pending)} รายการ")

        return "\n".join(status_lines)

    async def cmd_queue(self, args: List[str], user_id: str, context: dict) -> str:
        """ดู/จัดการคิว: !queue [clear]"""
        queue_manager = context.get("queue_manager")
        scheduler = context.get("scheduler")
        if not queue_manager and not scheduler:
            return "❌ ไม่พบระบบคิว"

        action = args[0].lower() if args else None
        if action == "clear":
            # ล้างคิวของระบบที่มีอยู่
            cleared = 0
            try:
                if queue_manager:
                    queue_manager.clear_queue()
                    # ไม่ทราบจำนวนที่ล้างได้จาก PriorityQueue ง่าย ๆ
                    return "🧹 ล้างคิว QueueManager แล้ว"
                q = getattr(scheduler, 'queue', None)
                while q and not q.empty():
                    q.get_nowait()
                    cleared += 1
            except Exception:
                pass
            return f"🧹 ล้างคิว Scheduler แล้ว: {cleared} รายการ"

        # แสดงสถานะคิว
        if queue_manager:
            status = queue_manager.get_stats()
            return (
                "📋 **คิวข้อความ**\n"
                f"- จำนวน: {status['queue_size']}\n"
                f"- กำลังประมวลผล: {'✅' if status['processing'] else '❌'}\n"
                f"- YouTube: {'✅' if status['youtube_enabled'] else '❌'}\n"
                f"- โหมดคอแลป: {'✅' if status['collab_mode'] else '❌'}"
            )
        else:
            # Fallback to scheduler info
            try:
                q = getattr(scheduler, 'queue', None)
                size = q.qsize() if q else 0
            except Exception:
                size = 0
            return f"📬 ขนาดคิว: {size} รายการ (ใช้ !queue clear เพื่อล้าง)"
    
    # ลบเมธอดซ้ำ cmd_queue เดิม (รวมเข้าด้านบนแล้ว)
    
    async def cmd_skip(self, args: List[str], user_id: str, context: dict) -> str:
        """ข้ามข้อความปัจจุบัน"""
        # TODO: Implement skip functionality
        return "⏭️ ข้ามข้อความแล้ว"
    
    async def cmd_unlock(self, args: List[str], user_id: str, context: dict) -> str:
        """ปลดล็อคการเปิดเผยข้อมูลโปรเจค"""
        if not self.is_owner(user_id):
            return "❌ เฉพาะ owner เท่านั้น"
        
        if len(args) < 1:
            return "❌ ใช้: !unlock <code>"
        
        code = args[0]
        if code == self.unlock_code:
            self.is_unlocked = True
            return "🔓 ปลดล็อคแล้ว! สามารถพูดถึงโปรเจคได้"
        else:
            return "❌ รหัสผิด"
    
    async def cmd_lock(self, args: List[str], user_id: str, context: dict) -> str:
        """ล็อคการเปิดเผยข้อมูลโปรเจค"""
        if not self.is_owner(user_id):
            return "❌ เฉพาะ owner เท่านั้น"
        
        self.is_unlocked = False
        return "🔒 ล็อคแล้ว! ห้ามพูดถึงโปรเจค"

    def can_reveal_project_info(self) -> bool:
        """เช็คว่าสามารถเปิดเผยข้อมูลโปรเจคได้หรือไม่"""
        return self.is_unlocked

    # ===== Queue control commands =====
    async def cmd_youtube_on(self, args: List[str], user_id: str, context: dict) -> str:
        qm = context.get("queue_manager")
        if hasattr(qm, 'set_youtube_enabled'):
            qm.set_youtube_enabled(True)
            return "📺 เปิดรับคอมเม้น YouTube แล้ว"
        return "⚠️ ระบบคิวไม่รองรับการตั้งค่า YouTube"

    async def cmd_youtube_off(self, args: List[str], user_id: str, context: dict) -> str:
        qm = context.get("queue_manager")
        if hasattr(qm, 'set_youtube_enabled'):
            qm.set_youtube_enabled(False)
            return "📺 ปิดรับคอมเม้น YouTube แล้ว"
        return "⚠️ ระบบคิวไม่รองรับการตั้งค่า YouTube"

    async def cmd_voice_on(self, args: List[str], user_id: str, context: dict) -> str:
        qm = context.get("queue_manager")
        if hasattr(qm, 'set_collab_mode'):
            qm.set_collab_mode(True)
            return "🎤 เปิดโหมดรับเสียง (collab) แล้ว"
        return "⚠️ ระบบคิวไม่รองรับการตั้งค่า Voice"

    async def cmd_voice_off(self, args: List[str], user_id: str, context: dict) -> str:
        qm = context.get("queue_manager")
        if hasattr(qm, 'set_collab_mode'):
            qm.set_collab_mode(False)
            return "🎤 ปิดโหมดรับเสียง (collab) แล้ว"
        return "⚠️ ระบบคิวไม่รองรับการตั้งค่า Voice"


# Singleton
_admin_handler = None

def get_admin_handler() -> AdminCommandHandler:
    """ดึง AdminCommandHandler instance"""
    global _admin_handler
    if _admin_handler is None:
        _admin_handler = AdminCommandHandler()
    return _admin_handler
#!/usr/bin/env python3
"""
Test script for VTube Studio connection
ทดสอบการเชื่อมต่อ VTube Studio
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.config import get_settings
from src.adapters.vts.vts_client import VTSClient

async def test_vts_connection():
    """ทดสอบการเชื่อมต่อ VTube Studio"""
    print("🔄 กำลังทดสอบการเชื่อมต่อ VTube Studio...")
    
    try:
        # โหลดการตั้งค่า
        config = get_settings()
        print(f"📋 VTS Host: {config.VTS_HOST}")
        print(f"📋 VTS Port: {config.VTS_PORT}")
        print(f"📋 Plugin Name: {config.VTS_PLUGIN_NAME}")
        
        # สร้าง VTS client
        vts_client = VTSClient()
        
        # ทดสอบการเชื่อมต่อ (รวมการรับรองตัวตน)
        print("\n🔌 กำลังเชื่อมต่อ VTube Studio...")
        await vts_client.connect()
        print("🔐 การรับรองตัวตนสำเร็จ")
        
        # ทดสอบการส่งคำสั่งง่ายๆ
        print("🎭 กำลังทดสอบการส่งคำสั่ง...")
        
        # ทดสอบการตั้งค่า parameter
        print("   - ทดสอบการตั้งค่า parameter...")
        await vts_client.set_parameter("MouthOpen", 0.5)
        
        # ทดสอบการเปิด expression
        print("   - ทดสอบการเปิด expression...")
        await vts_client.set_expression("happy", True)
        
        # รอสักครู่แล้วปิด expression
        await asyncio.sleep(1)
        await vts_client.set_expression("happy", False)
        
        print("   ✅ ทดสอบการส่งคำสั่งสำเร็จ")
        
        print("\n✅ การทดสอบสำเร็จ! VTube Studio เชื่อมต่อได้แล้ว")
        
    except Exception as e:
        print(f"\n❌ เกิดข้อผิดพลาด: {str(e)}")
        print("\n💡 แนะนำการแก้ไข:")
        print("1. ตรวจสอบว่า VTube Studio เปิดอยู่")
        print("2. ตรวจสอบว่าเปิด API ใน VTube Studio (Settings > General > Allow plugins)")
        print("3. ตรวจสอบ port 8001 ว่าไม่ถูกใช้งานโดยโปรแกรมอื่น")
        print("4. ตรวจสอบการตั้งค่าใน .env file")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 AI VTuber Demo - VTube Studio Connection Test")
    print("=" * 50)
    
    # รันการทดสอบ
    success = asyncio.run(test_vts_connection())
    
    if success:
        print("\n🎉 พร้อมใช้งานระบบ AI VTuber แล้ว!")
    else:
        print("\n⚠️  กรุณาแก้ไขปัญหาก่อนใช้งาน")
        sys.exit(1)
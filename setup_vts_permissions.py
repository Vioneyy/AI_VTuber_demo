#!/usr/bin/env python3
"""
VTube Studio Permissions Setup Guide
คู่มือการตั้งค่า permissions สำหรับ AI VTuber Demo
"""

import asyncio
import sys
from src.adapters.vts.vts_client import VTSClient

def print_setup_guide():
    """แสดงคู่มือการตั้งค่า VTube Studio permissions"""
    print("=" * 60)
    print("🎭 AI VTuber Demo - VTube Studio Setup Guide")
    print("=" * 60)
    print()
    print("📋 ขั้นตอนการตั้งค่า VTube Studio:")
    print()
    print("1️⃣ เปิด VTube Studio")
    print("2️⃣ ไปที่ Settings (⚙️) > Plugins")
    print("3️⃣ ตรวจสอบว่า 'Allow plugins' เปิดอยู่")
    print("4️⃣ รอให้ 'AI VTuber Demo' ปรากฏในรายการ plugins")
    print("5️⃣ คลิกที่ 'AI VTuber Demo' plugin")
    print("6️⃣ เปิดใช้งาน 'Load custom images' ✅")
    print("7️⃣ คลิก 'Done' เพื่อบันทึก")
    print("8️⃣ หากยังไม่ได้ผล ให้ restart VTube Studio")
    print()
    print("⚠️  หมายเหตุสำคัญ:")
    print("   - Custom Parameters จะปรากฏใน VTS หลังจากเชื่อมต่อสำเร็จ")
    print("   - 'Load custom images' ต้องอนุญาตผ่าน UI เท่านั้น")
    print("   - หาก parameters ไม่ขึ้น ให้ลองเชื่อมต่อใหม่")
    print()

async def test_connection_and_setup():
    """ทดสอบการเชื่อมต่อและแสดงสถานะ"""
    print("🔄 กำลังทดสอบการเชื่อมต่อ VTube Studio...")
    print()
    
    try:
        vts = VTSClient()
        success = await vts.connect()
        
        if success:
            print("✅ เชื่อมต่อ VTube Studio สำเร็จ!")
            print(f"📊 พบ {len(vts.available_parameters)} parameters")
            print(f"🎯 พบ {len(vts.available_hotkeys)} hotkeys")
            
            # ตรวจสอบ custom parameters
            custom_params = [p for p in vts.available_parameters if p.startswith("AIVTuber_")]
            if custom_params:
                print(f"🎨 พบ {len(custom_params)} custom parameters:")
                for param in custom_params:
                    print(f"   - {param}")
            else:
                print("⚠️  ไม่พบ custom parameters - ลองเชื่อมต่อใหม่")
            
            print()
            print("💡 ตรวจสอบใน VTube Studio:")
            print("   - Settings > Plugins > Custom parameters")
            print("   - ควรเห็น AIVTuber_* parameters")
            print("   - Config/Permissions > Load custom images ควรเปิดอยู่")
            
        else:
            print("❌ ไม่สามารถเชื่อมต่อ VTube Studio ได้")
            print("🔧 แนะนำการแก้ไข:")
            print("   1. ตรวจสอบว่า VTube Studio เปิดอยู่")
            print("   2. ตรวจสอบว่า 'Allow plugins' เปิดอยู่")
            print("   3. ตรวจสอบ port 8001 ว่าง")
            print("   4. ลอง restart VTube Studio")
        
        await vts.disconnect()
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        print("🔧 ลองตรวจสอบ:")
        print("   - VTube Studio เปิดอยู่หรือไม่")
        print("   - Plugin API เปิดใช้งานหรือไม่")

async def main():
    """ฟังก์ชันหลัก"""
    print_setup_guide()
    
    while True:
        print("🎮 เลือกการดำเนินการ:")
        print("1. ทดสอบการเชื่อมต่อ")
        print("2. แสดงคู่มืออีกครั้ง")
        print("3. ออกจากโปรแกรม")
        print()
        
        try:
            choice = input("กรุณาเลือก (1-3): ").strip()
            
            if choice == "1":
                print()
                await test_connection_and_setup()
                print()
                input("กด Enter เพื่อดำเนินการต่อ...")
                print()
                
            elif choice == "2":
                print()
                print_setup_guide()
                
            elif choice == "3":
                print("👋 ขอบคุณที่ใช้ AI VTuber Demo!")
                break
                
            else:
                print("❌ กรุณาเลือก 1, 2, หรือ 3")
                print()
                
        except KeyboardInterrupt:
            print("\n👋 ขอบคุณที่ใช้ AI VTuber Demo!")
            break
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาด: {e}")
            print()

if __name__ == "__main__":
    asyncio.run(main())
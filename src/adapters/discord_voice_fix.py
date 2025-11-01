"""
discord_voice_fix.py - Discord Voice Connection Fix Utility
แก้ปัญหา Error 4006 (Invalid Session)
"""

import asyncio
import discord
import logging
import socket
from typing import Optional

logger = logging.getLogger(__name__)


class VoiceConnectionFixer:
    """ตัวช่วยแก้ปัญหา Voice Connection"""
    
    @staticmethod
    def force_ipv4():
        """บังคับใช้ IPv4 only (แก้ปัญหา IPv6 conflict)"""
        original_getaddrinfo = socket.getaddrinfo
        
        def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        
        socket.getaddrinfo = ipv4_only_getaddrinfo
        logger.info("✅ Force IPv4 mode enabled")
        
        return original_getaddrinfo
    
    @staticmethod
    def restore_getaddrinfo(original):
        """คืนค่า getaddrinfo เดิม"""
        socket.getaddrinfo = original
    
    @staticmethod
    def check_voice_dependencies():
        """เช็ค dependencies ที่จำเป็นสำหรับ voice"""
        issues = []
        
        # Check PyNaCl
        try:
            import nacl
            logger.info("✅ PyNaCl installed")
        except ImportError:
            issues.append("❌ PyNaCl not installed (pip install PyNaCl)")
        
        # Check discord.py voice support (opus)
        try:
            if not discord.opus.is_loaded():
                # ลองโหลด opus
                try:
                    discord.opus.load_opus('opus')
                    logger.info("✅ Opus codec loaded")
                except Exception as e:
                    logger.warning(f"⚠️ Could not load opus: {e}")
                    logger.info("💡 Discord.py will use built-in opus (this is OK)")
            else:
                logger.info("✅ Opus codec already loaded")
        except Exception as e:
            logger.warning(f"⚠️ Opus check failed: {e}")
            logger.info("💡 Discord.py will use built-in opus (this is OK)")
        
        return issues
    
    @staticmethod
    async def robust_voice_connect(
        channel: discord.VoiceChannel,
        timeout: float = 15.0,
        max_retries: int = 3
    ) -> Optional[discord.VoiceClient]:
        """
        เชื่อมต่อ voice แบบ robust (พยายามหลายครั้ง)
        
        Args:
            channel: Voice channel ที่จะเชื่อมต่อ
            timeout: Timeout ต่อครั้ง
            max_retries: จำนวนครั้งที่ลองใหม่
        
        Returns:
            VoiceClient หรือ None
        """
        original_getaddrinfo = VoiceConnectionFixer.force_ipv4()
        
        try:
            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 Attempting voice connection ({attempt + 1}/{max_retries})...")
                    
                    # เช็คสิทธิ์ก่อน
                    perms = channel.permissions_for(channel.guild.me)
                    if not perms.connect or not perms.speak:
                        logger.error("❌ Bot ไม่มีสิทธิ์ Connect หรือ Speak!")
                        return None
                    
                    # พยายามเชื่อมต่อ
                    voice_client = await asyncio.wait_for(
                        channel.connect(timeout=timeout, reconnect=True),
                        timeout=timeout
                    )
                    
                    # รอให้ stable
                    await asyncio.sleep(2.0)
                    
                    # เช็คว่าเชื่อมต่ออยู่จริง
                    if voice_client.is_connected():
                        logger.info(f"✅ Voice connected successfully on attempt {attempt + 1}")
                        return voice_client
                    else:
                        logger.warning(f"⚠️ Voice client not connected after join")
                        await voice_client.disconnect(force=True)
                
                except asyncio.TimeoutError:
                    logger.warning(f"⏱️ Timeout on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2.0)
                
                except discord.errors.ClientException as e:
                    if "4006" in str(e):
                        logger.error(f"❌ Error 4006 on attempt {attempt + 1}: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(3.0)
                    else:
                        logger.error(f"❌ Client error: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2.0)
                
                except Exception as e:
                    logger.error(f"❌ Unexpected error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2.0)
            
            logger.error("❌ Failed to connect after all retries")
            return None
        
        finally:
            VoiceConnectionFixer.restore_getaddrinfo(original_getaddrinfo)


async def diagnose_voice_connection():
    """วินิจฉัยปัญหา Voice Connection"""
    print("\n" + "="*60)
    print("🔍 Discord Voice Connection Diagnostics")
    print("="*60)
    
    fixer = VoiceConnectionFixer()
    
    # 1. Check dependencies
    print("\n1️⃣ Checking dependencies...")
    issues = fixer.check_voice_dependencies()
    
    if issues:
        print("\n❌ Found issues:")
        for issue in issues:
            print(f"   {issue}")
        print("\n💡 Fix:")
        print("   pip install PyNaCl opuslib")
    else:
        print("   ✅ All dependencies installed")
    
    # 2. Check network
    print("\n2️⃣ Checking network...")
    try:
        # Test DNS resolution
        socket.gethostbyname("discord.com")
        print("   ✅ DNS resolution works")
    except Exception as e:
        print(f"   ❌ DNS resolution failed: {e}")
    
    # 3. Check firewall (Windows)
    print("\n3️⃣ Checking Windows Firewall...")
    try:
        import subprocess
        result = subprocess.run(
            ["netsh", "advfirewall", "show", "currentprofile"],
            capture_output=True,
            text=True
        )
        if "State" in result.stdout and "ON" in result.stdout:
            print("   ⚠️ Windows Firewall is ON")
            print("   💡 You may need to add firewall rules for Python")
        else:
            print("   ✅ Windows Firewall is OFF or rule exists")
    except Exception as e:
        print(f"   ⚠️ Could not check firewall: {e}")
    
    # 4. Recommendations
    print("\n" + "="*60)
    print("📋 Recommendations:")
    print("="*60)
    
    if issues:
        print("\n1. Install missing dependencies:")
        print("   pip install PyNaCl opuslib")
    
    print("\n2. Add Windows Firewall rules:")
    print("   Run PowerShell as Administrator:")
    print('   New-NetFirewallRule -DisplayName "Python Discord" \\')
    print('     -Direction Inbound -Protocol UDP -Action Allow \\')
    print('     -Program "D:\\py\\python.exe"')
    
    print("\n3. Try different network:")
    print("   - Use mobile hotspot")
    print("   - Use VPN (Cloudflare WARP, ProtonVPN)")
    
    print("\n4. Check bot permissions:")
    print("   - Connect, Speak, Use Voice Activity")
    print("   - Reinvite bot with proper permissions")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(diagnose_voice_connection())
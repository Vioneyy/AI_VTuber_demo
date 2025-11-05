"""
Discord Permissions Checker
ตรวจสอบว่า bot มี permissions ที่ถูกต้องหรือไม่
"""
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

# Required permissions for voice bot
REQUIRED_PERMISSIONS = {
    'view_channel': True,
    'send_messages': True,
    'connect': True,
    'speak': True,
    'use_voice_activation': True,
    'read_message_history': True,
}

# Required intents
REQUIRED_INTENTS = [
    'guilds',
    'guild_messages',
    'message_content',
    'voice_states',
]

def check_permissions():
    """ตรวจสอบ permissions"""
    print("=" * 60)
    print("🔍 Discord Permissions Checker")
    print("=" * 60)
    
    # Check token
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ DISCORD_BOT_TOKEN not found in .env")
        return False
    
    print("✅ Bot token found")
    print(f"Token: {token[:20]}...")
    
    # Create bot
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True
    intents.members = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        print("\n" + "=" * 60)
        print(f"✅ Bot connected: {bot.user.name}#{bot.user.discriminator}")
        print(f"Bot ID: {bot.user.id}")
        print("=" * 60)
        
        # Check intents
        print("\n📋 Checking Intents...")
        print("-" * 60)
        for intent in REQUIRED_INTENTS:
            has_intent = getattr(bot.intents, intent, False)
            status = "✅" if has_intent else "❌"
            print(f"{status} {intent}: {has_intent}")
        
        # Check guilds
        print("\n🏰 Checking Guilds...")
        print("-" * 60)
        
        if not bot.guilds:
            print("❌ Bot is not in any guilds!")
            print("\nInvite URL:")
            print(f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=53803072&scope=bot")
        else:
            for guild in bot.guilds:
                print(f"\n🏰 Guild: {guild.name} (ID: {guild.id})")
                
                # Get bot member
                bot_member = guild.get_member(bot.user.id)
                if not bot_member:
                    print("  ❌ Bot member not found")
                    continue
                
                # Check text channel permissions
                text_channels = guild.text_channels
                if text_channels:
                    channel = text_channels[0]
                    perms = channel.permissions_for(bot_member)
                    
                    print(f"\n  📝 Text Channel Permissions ({channel.name}):")
                    for perm, required in REQUIRED_PERMISSIONS.items():
                        if perm in ['connect', 'speak', 'use_voice_activation']:
                            continue  # Skip voice perms for text channel
                        
                        has_perm = getattr(perms, perm, False)
                        status = "✅" if has_perm else "❌"
                        print(f"    {status} {perm}: {has_perm}")
                
                # Check voice channel permissions
                voice_channels = guild.voice_channels
                if voice_channels:
                    channel = voice_channels[0]
                    perms = channel.permissions_for(bot_member)
                    
                    print(f"\n  🎤 Voice Channel Permissions ({channel.name}):")
                    for perm, required in REQUIRED_PERMISSIONS.items():
                        has_perm = getattr(perms, perm, False)
                        status = "✅" if has_perm else "❌"
                        required_str = " (REQUIRED)" if required else ""
                        print(f"    {status} {perm}: {has_perm}{required_str}")
                    
                    # Check if all required permissions are present
                    missing_perms = []
                    for perm, required in REQUIRED_PERMISSIONS.items():
                        if required and not getattr(perms, perm, False):
                            missing_perms.append(perm)
                    
                    if missing_perms:
                        print(f"\n  ❌ Missing permissions: {', '.join(missing_perms)}")
                        print(f"\n  📋 Fix: Re-invite bot with correct permissions")
                        print(f"  URL: https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=53803072&scope=bot")
                    else:
                        print(f"\n  ✅ All required permissions present!")
        
        print("\n" + "=" * 60)
        print("✅ Permission check complete!")
        print("=" * 60)
        
        await bot.close()
    
    # Run bot
    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print("\n❌ Login failed!")
        print("Possible causes:")
        print("  1. Invalid bot token")
        print("  2. Token has been regenerated")
        print("  3. Bot has been deleted")
        print("\nFix: Get a new token from Discord Developer Portal")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    check_permissions()
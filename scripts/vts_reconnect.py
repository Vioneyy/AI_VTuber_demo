import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.vts.vts_client import VTSClient
from src.core.config import get_settings


async def main():
    settings = get_settings()
    host = settings.VTS_HOST
    port = settings.VTS_PORT
    plugin_name = settings.VTS_PLUGIN_NAME or os.getenv("VTS_PLUGIN_NAME", "AI VTuber Demo")

    client = VTSClient(
        plugin_name=plugin_name,
        plugin_developer="VIoneyy",
        host=host,
        port=port,
        config=settings,
    )

    # Perform disconnect then reconnect
    await client.disconnect()
    ok = await client.connect()
    if ok:
        print("✅ Reconnected to VTube Studio successfully")
    else:
        print("❌ Failed to reconnect to VTube Studio")


if __name__ == "__main__":
    asyncio.run(main())
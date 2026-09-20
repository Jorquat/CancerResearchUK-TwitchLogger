import asyncio
import json

from donation_tracker import TwitchBot


async def main():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("config not found")
        return

    channel = config.get('twitch_channel')
    print(f"Connecting to #{channel}")

    bot = TwitchBot(config.get('twitch_token'), config.get('twitch_bot_username'), channel)
    await bot.connect()
    await asyncio.sleep(5)

    if not bot.connected:
        return

    await bot.send_message("TestDonor just donated £5.00 to Cancer Research! PogChamp")
    print("Sent")

    await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())

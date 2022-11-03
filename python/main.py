import asyncio
import os
from pprint import pprint
from telethon.tl.functions.channels import GetFullChannelRequest

import sql
import helper
from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
bot_token = os.environ['BOT_TOKEN']


async def main():
    client = TelegramClient('bot', api_id, api_hash)
    client.parse_mode = 'html'
    await client.start(bot_token=bot_token)
    sql.init()

    @client.on(events.ChatAction())
    async def handler(event):
        if event.user_joined or event.user_left:
            # pprint(f'{event.user.id} - {event.user.first_name}')
            await helper.do(client, event)
            # channel = helper.get_channel(event)['entity']
            # chat_full = await client(GetFullChannelRequest(channel=channel))
            # pprint(chat_full.full_chat.participants_count)

    @client.on(events.NewMessage(func=helper.check))
    async def handler(event):
        await helper.do(client, event)

    @client.on(events.CallbackQuery(func=helper.check))
    async def handler(event):
        await helper.do(client, event)

    await client.run_until_disconnected()


asyncio.run(main())

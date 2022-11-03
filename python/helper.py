import os
import re
from telethon.events import ChatAction
import sql
from telethon import Button
from telethon.tl.types import ChannelParticipantCreator, ChannelParticipantAdmin, PeerUser
from telethon.tl.functions.channels import GetParticipantRequest
from commands import Commands
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

suffixes = {
    'male': {
        'name': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_NAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_NAME_2'].split(','))),
        },
        'surname': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_SURNAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_MALE_SURNAME_2'].split(','))),
        },
    },
    'female': {
        'name': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_2'].split(','))),
        },
        'surname': {
            1: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_1'].split(','))),
            2: list(map(lambda x: x.strip(), os.environ['SUFFIX_FEMALE_NAME_2'].split(','))),
        },
    },
}

custom_admins = list(map(
    lambda x: int(x.strip()),
    os.environ['CUSTOM_ADMINS'].split(',')
)) if os.environ['CUSTOM_ADMINS'] else []

user_commands = {
    **Commands.user_commands.copy(),
}

admin_commands = {
    **Commands.admin_commands.copy(),
}

timezone = timezone(timedelta(hours=3), name=os.environ['TZ'])


# Just to remember that this func exists
async def check(event) -> bool:
    return True


async def can(client, event, command) -> bool:
    if type(event) == ChatAction.Event:
        return True

    if f'/{command}' in user_commands:
        return True

    user = await get_user(event)
    channel = await get_channel(event)

    participant = await client(
        GetParticipantRequest(channel=channel, participant=user)
    )

    if f'/{command}' in admin_commands and \
            (type(participant.participant) == ChannelParticipantAdmin or
             type(participant.participant) == ChannelParticipantCreator or
             user.id in custom_admins):
        return True

    print('helper.can() failed')
    return False


async def do(client, event):
    commands = Commands(client)

    if not (payload := await get_command(event)):
        return

    command, kwargs = payload

    if not kwargs:
        kwargs = {}
    elif kwargs and '|' in kwargs:
        kwargs = list(map(lambda x: int(x) if x.isnumeric() else x, kwargs.split('|')))
        kwargs = dict(zip(i := iter(kwargs), i))

    if await can(client, event, command) and \
            hasattr(commands, command) and \
            callable(func := getattr(commands, command)):
        await func(event, **kwargs)


async def get_command(event):
    channel = await get_channel(event)
    user = await get_user(event)
    all_commands = {**user_commands.copy(), **admin_commands.copy()}
    possible_list = []

    # Show captcha to new joined user
    if (hasattr(event, 'user_joined') and event.user_joined):
        return ['on_user_joined', None]

    if (hasattr(event, 'user_left') and event.user_left) or (hasattr(event, 'user_kicked') and event.user_kicked):
        kwargs = {
            'data': {
                'chat_id': channel.id,
                'user_id': user.id,
                'status': 'left',
                'args': {}
            }
        }

        return ['on_user_left', kwargs]

    if hasattr(event, 'message'):
        # Resolve new user's answer
        if (user_row := sql.fetchone(table='users', user_id=user.id, chat_id=channel.id)) \
                and ((args := user_row.get('args')) and args.get('pending')):
            return ['solve_captcha', None]

        possible_list.append(event.message.message)

    if hasattr(event, 'query') and getattr(event.query, 'data'):
        possible_list.append(event.query.data.decode("utf-8"))

    if hasattr(event, 'get_reply_message') and callable(event.get_reply_message):
        """Get command from previous message that this message is replying to"""
        reply_message = await event.get_reply_message()

        if reply_message is not None and hasattr(reply_message, 'message'):
            possible_list.append(reply_message.message)

    for text in possible_list:
        kwargs = re.sub(r'(/)*([\w\s]+)?(:*)([^@]*)?(@*)(.*)', r'\4', text)
        text = re.sub(r'(/)*([\w\s]+)?(:*)([^@]*)?(@*)(.*)', r'\1\2\3', text)

        for key, value in all_commands.items():
            if (key.startswith('/') and key == text.replace(':', '')) or value == text:
                command = key.replace('/', '')

                return [command, kwargs]

    return


def get_run_date(minutes=5):
    return datetime.now(tz=timezone) + timedelta(minutes=minutes)


async def get_user(event):
    if hasattr(event, 'user'):
        return event.user

    return await event.get_sender()


async def get_channel(event):
    if hasattr(event, 'chat'):
        return event.chat

    return await event.get_chat()


def get_list(string, sep=','):
    return list(map(lambda x: x.strip(), string.split(sep)))


def get_plural(num, words):
    cases = [2, 0, 1, 1, 1, 2]
    key = 2 if (4 < num % 100 < 20) else cases[min(num % 10, 5)]

    return f'{num} {words[key]}'


def declension(string, case, gender='male'):
    words = string.strip().split(' ')

    for k, word in enumerate(words):
        name_type = 'name' if k == 0 else 'surname'

        for key, value in enumerate(suffixes[gender][name_type][1]):
            value = value.strip()
            pattern = fr'^(.+)({value})$'
            replacement = fr'\1{suffixes[gender][name_type][case][key].strip()}'

            if re.search(pattern, word):
                words[k] = re.sub(pattern, replacement, word)
                break

    return ' '.join(words)


def remove_emojis(string):
    pattern = u"[" \
              u"\U0001F600-\U0001F64F" \
              u"\U0001F300-\U0001F5FF" \
              u"\U0001F680-\U0001F6FF" \
              u"\U0001F1E0-\U0001F1FF" \
              u"\U00002500-\U00002BEF" \
              u"\U00002702-\U000027B0" \
              u"\U00002702-\U000027B0" \
              u"\U000024C2-\U0001F251" \
              u"\U0001f926-\U0001f937" \
              u"\U00010000-\U0010ffff" \
              u"\u2640-\u2642" \
              u"\u2600-\u2B55" \
              u"\u200d" \
              u"\u23cf" \
              u"\u23e9" \
              u"\u231a" \
              u"\ufe0f" \
              u"\u3030" \
              u"]+"

    return re.sub(pattern, '', string).strip()

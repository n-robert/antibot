import traceback
import random
import helper
import sql
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta


class Commands:
    admin_commands = {
        '/captcha': None,
    }

    user_commands = {
        '/solve_captcha': None,
    }

    messages = {
        'new_user': (
            (
                'Здравствуйте, {mention}!',
                '{mention}, приветствуем!',
                'Рады видеть вас, {mention}!',
            ),
            (
                'Сейчас я задам вам вопрос и вы должны на него ответить в течение 5 минут, иначе я вас забаню.',
                'У вас есть 5 минут, чтобы доказать, что вы - не бот.',
                'Надеюсь, что вы - не бот и у вас есть 5 минут, чтобы это доказать.',
            ),
            (
                'Итак, {question}',
                'Напишите, {question}',
                'Сообщите нам, {question}',
                'Можете сказать, {question}',
            ),
        ),
        'captcha': (
            {'Сколько всего участников в нашем чате?': 'chat_full.full_chat.participants_count'},
            {'Какое название у нашего чата?': 'channel.title'},
            {'Как меня зовут?': 'me.first_name'},
            {'Сколько всего участников в чате, не считая вас?': 'chat_full.full_chat.participants_count - 1'},
            {'Как пишется мое имя?': 'me.first_name'},
            {'Как называется наш чат?': 'channel.title'},
        ),
        'trying': (
            'Ответ не верный, {mention}. Попробуйте еще.',
            'Неправильно. Следующая попытка, {mention}.',
            '{mention}, возможно, вы допустили опечатку. Давайте еще раз.',
        ),
        'greeting': (
            'Добро пожаловать, {mention}, в наш чат! Расскажите немного о себе!',
            'Отлично, {mention}, добро пожаловать! Что вас привело в наш чат?',
            '{mention}, будьте, как дома! Надеюсь, что вы найдете у нас много полезного и внесете в чат свой вклад.',
        )
    }

    feedbacks = {
        'captcha': 'Вам даются 2 минуты, чтобы пройти проверку на бот.',
    }

    placeholders = {
        'captcha': 'Введите ответ...',
    }

    def __init__(self, client: TelegramClient):
        self.client = client
        self.client.parse_mode = 'html'
        self.timezone = helper.timezone
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

    async def do_captcha(self, event):
        channel = await helper.get_channel(event)
        user = await helper.get_user(event)
        mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
        message = chr(10).join(map(
            lambda x: random.choice(x),
            self.messages['new_user']
        ))
        quiz = random.choice(self.messages['captcha'])
        question = list(quiz.keys())[0].lower()
        answer = list(quiz.values())[0].lower()
        placeholder = self.placeholders['captcha']
        token = f'{channel.id}:{user.id}'

        send_message = await self.client.send_message(
            entity=channel,
            message=message.format(mention=mention, question=question),
        )

        user_data = {
            'user_id': user.id,
            'chat_id': channel.id,
            'status': 'joined',
            'joined_at': datetime.now().isoformat(timespec='seconds', sep=' '),
            'args': {'answer': answer, 'pending': True, 'token': token},
        }
        sql.upsert('users', user_data)

        message_data = {
            'message_id': send_message.id,
            'user_id': user.id,
            'chat_id': channel.id,
            'type': 'question',
            'payload': question,
        }
        sql.upsert('messages', message_data)

        kwargs = {
            'channel': channel,
            'user': user,
            'token': token,
        }

        await self.add_job('ban_user', **kwargs)

    async def solve_captcha(self, event):
        channel = await helper.get_channel(event)
        user = await helper.get_user(event)
        user_row = sql.fetchone(table='users', chat_id=channel.id, user_id=user.id)
        args = user_row.get('args') or {}
        mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'

        # These variables required for eval(command) while getting answer
        chat_full = await self.client(GetFullChannelRequest(channel=channel))
        me = await self.client.get_me()
        print(str(eval(args.get('answer'))).lower())
        print(str(event.message.message).strip().lower())

        if (command := args.get('answer')) \
                and ((answer := str(eval(command)).lower())
                     and answer == str(event.message.message).strip().lower()):
            await self.remove_args(event=event, keys=['answer', 'pending', 'token'])
            message = random.choice(self.messages['greeting'])
        else:
            message = random.choice(self.messages['trying'])

        await self.client.send_message(
            entity=channel,
            message=message.format(mention=mention),
        )

    def update_status(self, data):
        status = data.get('status')

        if f'{status}_at' not in data:
            data[f'{status}_at'] = datetime.now().isoformat(timespec='seconds', sep=' ')

        sql.upsert('users', data)

    async def ban_user(self, channel, user, token):
        user_row = sql.fetchone(table='users', chat_id=channel.id, user_id=user.id)

        try:
            if (args := user_row.get('args')) and token != args.get('token'):
                print("This job is abandoned, I'll skip it")

                return

            if args.get('answer') and args.get('pending'):
                await self.client.edit_permissions(
                    entity=channel,
                    user=user,
                    until_date=timedelta(minutes=2),
                    view_messages=False
                )

                data = {
                    'chat_id': channel.id,
                    'user_id': user.id,
                    'status': 'banned',
                    'args': {},
                }
                self.update_status(data)
            else:
                print(f"User {user.first_name} doesn't have pending status.")
        except BaseException:
            traceback.print_exc()

    async def user_left(self, event, **kwargs):
        self.update_status(**kwargs)

    async def remove_args(self, event, **kwargs):
        channel = await helper.get_channel(event)
        user = await helper.get_user(event)
        keys = kwargs.get('keys') or []

        if keys and (row := sql.fetchone(table='users', chat_id=channel.id, user_id=user.id)):
            args = row.get('args') or {}

            for key in keys:
                try:
                    if key in args:
                        args.pop(key)
                except BaseException:
                    print(f'key {key} not exists.')
                    traceback.print_exc()

            data = {
                'chat_id': channel.id,
                'user_id': user.id,
                'args': args,
            }
            sql.upsert('users', data)

    async def add_job(self, func_name, **kwargs):
        channel = kwargs.get('channel')
        user = kwargs.get('user')

        if not (user_row := sql.fetchone(table='users', chat_id=channel.id, user_id=user.id)):
            print('Not enough parameters or no such user')
            return

        kwargs = {
            'trigger': 'date',
            # 'next_run_time': run_date,
            'replace_existing': True,
            'id': f'{func_name}_{channel.id}_{user.id}',
            'run_date': helper.get_run_date(),
            'kwargs': kwargs,
        }

        if callable(func := getattr(self, func_name)):
            try:
                self.scheduler.add_job(func=func, **kwargs)
            except BaseException:
                print(f'Cannot add job #{func_name}_{channel.id}_{user.id}:')
                traceback.print_exc()

            try:
                self.scheduler.print_jobs()
            except BaseException:
                print('print_jobs() error:')
                traceback.print_exc()

    async def test(self, event):
        print(await helper.get_channel(event))

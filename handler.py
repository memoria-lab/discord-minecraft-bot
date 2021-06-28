import json
import os

import boto3
import requests
from nacl.signing import VerifyKey

REGION = os.getenv('REGION')
INSTANCE_ID = os.getenv('INSTANCE_ID')

DISCORD_ENDPOINT = "https://discord.com/api/v8"
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
APPLICATION_ID = os.getenv('APPLICATION_ID')
APPLICATION_PUBLIC_KEY = os.getenv('APPLICATION_PUBLIC_KEY')
COMMAND_GUILD_ID = os.getenv('COMMAND_GUILD_ID')
DISCORD_ROLE_ID = os.getenv('DISCORD_ROLE_ID')

ec2 = boto3.client('ec2', region_name=REGION)
verify_key = VerifyKey(bytes.fromhex(APPLICATION_PUBLIC_KEY))

COMMANDS = {
    'START': 'start',
    'STOP': 'stop',
    'REBOOT': 'reboot',
    'STATUS': 'status',
}
STATE = {
    'RUNNING': 'running',
    'STOPPED': 'stopped',
}

def registerCommands():
    endpoint = f"{DISCORD_ENDPOINT}/applications/{APPLICATION_ID}/guilds/{COMMAND_GUILD_ID}/commands"
    print(f"registering commands: {endpoint}")

    commands = [
        {
            "name": "minecraft",
            "description": "マイクラめもりあ鯖の制御コマンド",
            "options": [
                {
                    "name": "control",
                    "description": "制御タイプを指定します。",
                    "type": 3,
                    "required": True,
                    "choices": [
                        {
                            "name": "起動",
                            "value": COMMANDS['START']
                        },
                        {
                            "name": "停止",
                            "value": COMMANDS['STOP']
                        },
                        {
                            "name": "再起動",
                            "value": COMMANDS['REBOOT']
                        },
                        {
                            "name": "ステータスの確認",
                            "value": COMMANDS['STATUS']
                        }
                    ]
                }
            ]
        }
    ]

    headers = {
        "User-Agent": "discord-minecraft-bot",
        "Content-Type": "application/json",
        "Authorization": "Bot " + DISCORD_TOKEN
    }

    for c in commands:
        requests.post(endpoint, headers=headers, json=c).raise_for_status()

def verify(signature: str, timestamp: str, body: str) -> bool:
    try:
        verify_key.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
    except Exception as e:
        print(f"failed to verify request: {e}")
        return False

    return True

def commandCallback(event: dict, context: dict):
    # API Gateway has weird case conversion, so we need to make them lowercase.
    # See https://github.com/aws/aws-sam-cli/issues/1860
    headers: dict = { k.lower(): v for k, v in event['headers'].items() }
    rawBody: str = event['body']

    # validate request
    signature = headers.get('x-signature-ed25519')
    timestamp = headers.get('x-signature-timestamp')
    if not verify(signature, timestamp, rawBody):
        return {
            "cookies": [],
            "isBase64Encoded": False,
            "statusCode": 401,
            "headers": {},
            "body": ""
        }

    print('verified!')

    req: dict = json.loads(rawBody)
    print(req)

    if req['type'] == 1: # InteractionType.Ping
        print('InteractionType.Ping')
        registerCommands()
        return {
            "type": 1 # InteractionResponseType.Ping
        }

    elif req['type'] == 2: # InteractionType.ApplicationCommand
        print('InteractionType.ApplicationCommand')
        # command options list -> dict
        options = {v['name']: v['value'] for v in req['data']['options']} if 'options' in req['data'] else {}

        print(options)
        text = ''

        if not DISCORD_ROLE_ID in req['member']['roles']:
            print('モデレーター以外がコマンドを実行しようとしました。ユーザー: ' + req['member']['user']['username'])
            text = "Minecraft Moderator以外の方は、サーバーの起動や停止はできません。"

            return {
                "type": 4, # InteractionResponseType.ChannelMessageWithSource
                "data": {
                    "content": text
                }
            }

        instanceStatus = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
        print(instanceStatus)
        instance = instanceStatus['Reservations'][0]['Instances'][0]
        instanceState = instance['State']['Name']
        print(instanceState)

        if options['control'] == COMMANDS['START']:
            print('起動: ' + str(INSTANCE_ID))
            if instanceState == STATE['RUNNING']:
                print('起動済み')
                text = "すでにマイクラめもりあ鯖は起動しています。\n問題がある場合は再起動してください。"
            else:
                ec2.start_instances(InstanceIds=[INSTANCE_ID])
                print('インスタンスの起動')
                text = "マイクラめもりあ鯖を起動します。\nサーバー起動まで少々お待ち下さい。\nサーバーの起動が完了すると、`minecraft`チャンネルに「サーバーを起動しました。」と表示されます。"

        elif options['control'] == COMMANDS['STOP']:
            print('停止: ' + str(INSTANCE_ID))
            if instanceState == STATE['STOPPED']:
                print('停止済み')
                text = "すでにマイクラめもりあ鯖は停止しています。"
            else:
                ec2.stop_instances(InstanceIds=[INSTANCE_ID])
                print('インスタンスの停止')
                text = "マイクラめもりあ鯖を停止します。"

        elif options['control'] == COMMANDS['REBOOT']:
            print('再起動: ' + str(INSTANCE_ID))
            if instanceState == STATE['STOPPED']:
                ec2.start_instances(InstanceIds=[INSTANCE_ID])
                print('停止済み -> インスタンスの起動')
                text = "マイクラめもりあ鯖を起動します。\nサーバー起動まで少々お待ち下さい。\nサーバーの起動が完了すると、`minecraft`チャンネルに「サーバーを起動しました。」と表示されます。"
            else:
                ec2.reboot_instances(InstanceIds=[INSTANCE_ID])
                print('インスタンスの再起動')
                text = "マイクラめもりあ鯖を再起動します。\nサーバー起動まで少々お待ち下さい。\nサーバーの起動が完了すると、`minecraft`チャンネルに「サーバーを起動しました。」と表示されます。"

        elif options['control'] == COMMANDS['STATUS']:
            print('ステータスの確認: ' + str(INSTANCE_ID))
            if instanceState == STATE['STOPPED']:
                print('停止済み')
                text = "マイクラめもりあ鯖は停止しています。"
            else:
                print('停止済み以外')
                text = "マイクラめもりあ鯖は起動しています。"

        return {
            "type": 4, # InteractionResponseType.ChannelMessageWithSource
            "data": {
                "content": text
            }
        }

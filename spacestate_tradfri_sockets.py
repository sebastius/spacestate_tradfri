#!/usr/bin/env python3
# Hack to allow relative import above top level package
"""
MQTT spacestate switch for our powerswitches.
"""

# Hack to allow relative import above top level package
import sys
import os
import time

folder = os.path.dirname(os.path.abspath(__file__))  # noqa
sys.path.insert(0, os.path.normpath("%s/.." % folder))  # noqa

from pytradfri import Gateway
from pytradfri.api.aiocoap_api import APIFactory
from pytradfri.error import PytradfriError
from pytradfri.util import load_json, save_json

import asyncio
import uuid
import argparse
import paho.mqtt.client as mqtt

CONFIG_FILE = 'tradfri_standalone_psk.conf'

parser = argparse.ArgumentParser()
parser.add_argument('host', metavar='IP', type=str,
                    help='IP Address of your Tradfri gateway')
parser.add_argument('-K', '--key', dest='key', required=False,
                    help='Key found on your Tradfri gateway')

makestate = False

args = parser.parse_args()

if args.host not in load_json(CONFIG_FILE) and args.key is None:
    print("Please provide the 'Security Code' on the back of your "
          "Tradfri gateway:", end=" ")
    key = input().strip()
    if len(key) != 16:
        raise PytradfriError("Invalid 'Security Code' provided.")
    else:
        args.key = key

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("revspace/state")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    global makestate
    print('\nMQTT BERICHT:', msg.topic+" "+str(msg.payload))
    if msg.payload == b'open':
        makestate=True
        asyncio.get_event_loop().run_until_complete(run())
    if msg.payload == b'closed':
        makestate=False
        asyncio.get_event_loop().run_until_complete(run())


async def run():
    global makestate
    # Assign configuration variables.
    # The configuration check takes care they are present.
    conf = load_json(CONFIG_FILE)

    try:
        identity = conf[args.host].get('identity')
        psk = conf[args.host].get('key')
        api_factory = APIFactory(host=args.host, psk_id=identity, psk=psk)
    except KeyError:
        identity = uuid.uuid4().hex
        api_factory = APIFactory(host=args.host, psk_id=identity)

        try:
            psk = await api_factory.generate_psk(args.key)
            print('Generated PSK: ', psk)

            conf[args.host] = {'identity': identity,
                               'key': psk}
            save_json(CONFIG_FILE, conf)
        except AttributeError:
            raise PytradfriError("Please provide the 'Security Code' on the "
                                 "back of your Tradfri gateway using the "
                                 "-K flag.")

    api = api_factory.request

    gateway = Gateway()

    devices_command = gateway.get_devices()
    devices_commands = await api(devices_command)
    devices = await api(devices_commands)
    sockets = [dev for dev in devices if dev.has_socket_control]
    for socket in sockets:
        # Print all sockets
        state = (socket.socket_control.sockets[0].state)
        print(socket.name, state, 'naar', makestate)
        state_command = socket.socket_control.set_state(makestate)
        await api(state_command)

    await asyncio.sleep(2)
    print('\n')
    await api_factory.shutdown()

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=15)
#asyncio.get_event_loop().run_until_complete(run())

while True:
    try:
        client.connect("mosquitto.space.revspace.nl", 1883, 60)
        print('MQTT verbonden!')
        client.loop_forever()
    except:
        print('Kan de MQTT niet vinden, ik kijk zo wel effe, ok?')
        time.sleep(5)


import json
import socket
import time

with open('config.json', 'r') as f:
    config = json.load(f)

token = config['twitch_token']
username = config['twitch_bot_username']
channel = config['twitch_channel']


def read(sock, label):
    try:
        data = sock.recv(4096).decode('utf-8', errors='ignore')
    except Exception:
        return
    if data:
        print(f"\n{label}:\n{data}")


print(f"Connecting to Twitch IRC as {username}")

sock = socket.socket()
sock.connect(('irc.chat.twitch.tv', 6667))

sock.send(b"CAP REQ :twitch.tv/tags twitch.tv/commands\n")
sock.send(f"PASS {token}\n".encode('utf-8'))
sock.send(f"NICK {username}\n".encode('utf-8'))
sock.send(f"JOIN #{channel}\n".encode('utf-8'))

time.sleep(3)
sock.setblocking(0)
read(sock, "server said")

sock.send(f"PRIVMSG #{channel} :Test message from donation tracker\n".encode('utf-8'))
print("Test message sent")

time.sleep(2)
read(sock, "after sending")

print("\nCheck the chat now")
time.sleep(10)
sock.close()

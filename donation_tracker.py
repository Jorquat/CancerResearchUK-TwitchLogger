import asyncio
import json
import re
import socket
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

DEFAULT_PAGE = 'https://fundraise.cancerresearchuk.org/page/laurens-giving-page-10015407'
KEYWORDS = ('total', 'raised', 'online', 'offline', 'target', 'complete', 'gift aid')
BACKUP_KEYWORDS = ('ago', 'charity', 'total', 'raised', 'gift aid', 'offline', 'online', 'update', 'filter')
LINES = ('menu', 'share', 'donations')
HEADERS = ('latest updates', 'filter updates', 'all updates')

def new_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(30)
    return driver


def looks_like_name(text: str) -> bool:
    lower = text.lower()
    if not 0 < len(text) < 30:
        return False
    if '£' in text or '(' in text:
        return False
    if lower in LINES or lower.startswith('all '):
        return False
    return not any(word in lower for word in BACKUP_KEYWORDS)


def looks_like_message(text: str) -> bool:
    lower = text.lower()
    return len(text) > 10 and '£' not in text and 'ago' not in lower and lower not in HEADERS


class TwitchBot:
    def __init__(self, token: str, bot_username: str, channel: str):
        self.token = token
        self.bot_username = bot_username.lower().strip()
        self.channel_name = channel.lower().strip()
        self.sock = None
        self.connected = False

    async def connect(self):
        try:
            self.sock = socket.socket()
            self.sock.connect(('irc.chat.twitch.tv', 6667))

            self.sock.send(f"PASS {self.token}\n".encode('utf-8'))
            self.sock.send(f"NICK {self.bot_username}\n".encode('utf-8'))
            self.sock.send(f"JOIN #{self.channel_name}\n".encode('utf-8'))
            time.sleep(2)

            self.connected = True
            print(f'Joined #{self.channel_name}')

            await asyncio.sleep(1)
            await self.send_message("Donation tracker is up")
            asyncio.create_task(self._listen())
        except Exception as e:
            print(f'Error connecting to Twitch: {e}')
            self.connected = False

    async def _listen(self):
        self.sock.setblocking(0)
        while self.connected:
            try:
                response = self.sock.recv(2048).decode('utf-8', errors='ignore')
                if response.startswith('PING'):
                    self.sock.send(b"PONG :tmi.twitch.tv\n")
            except BlockingIOError:
                pass
            except Exception as e:
                if "10053" in str(e):
                    print(f'Connection lost: {e}')
                    self.connected = False
                    break
            await asyncio.sleep(0.5)

    def _write(self, message: str):
        self.sock.send(f"PRIVMSG #{self.channel_name} :{message}\n".encode('utf-8'))

    async def send_message(self, message: str):
        if not self.connected:
            await self.connect()

        if not (self.connected and self.sock):
            print(f'dropped: {message}')
            return

        try:
            self._write(message)
        except Exception as e:
            print(f'Send failed, reconnecting: {e}')
            self.connected = False
            await self.connect()
            try:
                self._write(message)
            except Exception:
                print('Still failed after reconnect')


class DonationTracker:
    def __init__(self, page_url: str, check_interval: int = 10):
        self.page_url = page_url
        self.check_interval = check_interval
        self.latest_donation = None
        self.driver = new_driver()

    def _dismiss_cookie_banner(self):
        for xpath in ("//button[contains(text(), 'OK')]",
                      "//button[contains(text(), 'Accept')]",
                      "//button[contains(text(), 'continue')]",
                      "//a[contains(text(), 'continue to site')]"):
            try:
                self.driver.find_element(By.XPATH, xpath).click()
                time.sleep(1)
                return
            except Exception:
                continue

    def _scroll_to_updates(self):
        try:
            heading = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Latest updates')]")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", heading)
        except Exception:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(2)

    def _first_donation(self, lines):
        for i, line in enumerate(lines):
            amount_match = re.search(r'£(\d+\.\d{2})', line)
            if not amount_match or any(word in line.lower() for word in KEYWORDS):
                continue
            name = next((lines[i - j] for j in range(1, min(6, i + 1))
                         if looks_like_name(lines[i - j])), None)
            if not name:
                continue

            message = next((lines[i + k] for k in range(1, min(4, len(lines) - i))
                            if looks_like_message(lines[i + k])), None)

            amount = float(amount_match.group(1))
            return {'name': name, 'amount': amount, 'message': message, 'id': f"{name}_{amount}"}

        return None

    def get_latest_donation(self):
        try:
            try:
                self.driver.current_url
            except Exception:
                #closed driver
                self.driver = new_driver()

            self.driver.get(self.page_url)
            time.sleep(2)

            self._dismiss_cookie_banner()
            self._scroll_to_updates()

            body = self.driver.find_element(By.TAG_NAME, 'body')
            lines = [l.strip() for l in body.text.split('\n') if l.strip()]

            # cut off
            start = next((i for i, line in enumerate(lines) if 'latest updates' in line.lower()), None)
            if start is None:
                print("No 'Latest updates' section on the page")
                return None

            return self._first_donation(lines[start:])

        except Exception as e:
            print(f"Error fetching latest donation: {e}")
            return None

    def check_for_new_donation(self):
        current = self.get_latest_donation()
        if current is None:
            return None

        if self.latest_donation and current['id'] == self.latest_donation['id']:
            return None

        self.latest_donation = current
        message = f"{current['name']} just donated £{current['amount']:.2f} to Cancer Research! PogChamp"
        if current.get('message'):
            message += f' "{current["message"]}"'
        return message

    def _prime(self):
        print(f"Tracking {self.page_url} every {self.check_interval}s") #startup log

        self.latest_donation = self.get_latest_donation()
        if self.latest_donation:
            print(f"Most recent so far: {self.latest_donation['name']} "
                  f"- £{self.latest_donation['amount']:.2f}")
        else:
            print("No donations found yet")

    def close(self):
        try:
            self.driver.quit()
        except Exception:
            pass

    async def run_async(self, twitch_bot=None):
        self._prime()
        try:
            while True:
                try:
                    message = self.check_for_new_donation()
                    if message:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
                        if twitch_bot:
                            await twitch_bot.send_message(message)
                except Exception as e:
                    print(f"Error: {e}")

                await asyncio.sleep(self.check_interval)
        except KeyboardInterrupt:
            print("\nStopping")
        finally:
            self.close()

    def run(self, callback=None):
        self._prime()
        try:
            while True:
                message = self.check_for_new_donation()
                if message:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")
                    if callback:
                        callback(message)

                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            print("\nStopping")
        finally:
            self.close()


def main():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}

    tracker = DonationTracker(config.get('page_url', DEFAULT_PAGE),
                              config.get('check_interval', 30))

    token = config.get('twitch_token')
    bot_username = config.get('twitch_bot_username')
    channel = config.get('twitch_channel')

    if not all([token, bot_username, channel]):
        return

    bot = TwitchBot(token, bot_username, channel)

    async def run_with_twitch():
        await bot.connect()
        await tracker.run_async(bot)

    asyncio.run(run_with_twitch())


if __name__ == "__main__":
    main()

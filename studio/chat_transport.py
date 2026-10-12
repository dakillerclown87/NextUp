"""NextUp-only Twitch IRC transport. No audio recognition dependencies."""
import asyncio
import logging
import re
import ssl
import time

def clean_text(value, length=160):
    return " ".join(str(value or "").split())[:length]

def parse_irc(line):
    tags, prefix = {}, ""
    if line.startswith("@"):
        tag_text, line = line[1:].split(" ", 1)
        for tag in tag_text.split(";"):
            key, _, value = tag.partition("=")
            tags[key] = value
    if line.startswith(":"):
        prefix, line = line[1:].split(" ", 1)
    head, separator, trailing = line.partition(" :")
    parts = head.split()
    return tags, prefix, parts[0], parts[1:], trailing if separator else ""


def chat_line(channel, message_id, text):
    reply = f"@reply-parent-msg-id={message_id} " if re.fullmatch(r"[a-zA-Z0-9-]{1,80}", message_id) else ""
    prefix = f"{reply}PRIVMSG #{channel} :"
    # Respect the IRC wire limit in bytes, including reply tags and CRLF.
    budget = 510 - len(prefix.encode())
    payload = clean_text(text, 2000).replace("\x00", "").encode()[:budget].decode("utf-8", "ignore")
    return (prefix + payload + "\r\n").encode()


class TwitchBot:
    def __init__(self, config, auth):
        self.config, self.auth = config, auth
        self.channel = config['channel']
        self.status = 'Connecting to Twitch'
        self.writer = None
        self.queue = asyncio.Queue(maxsize=100)
        self.work = set()
        self.last_sent = 0.0

    def reply(self, message_id, text):
        try:
            self.queue.put_nowait((time.monotonic(), message_id, text))
        except asyncio.QueueFull:
            logging.warning("Chat output is full; some replies may be dropped.")


    async def send_loop(self, writer):
        while True:
            created, message_id, text = await self.queue.get()
            try:
                if time.monotonic() - created > 90:
                    continue
                await asyncio.sleep(max(0, 1.65 - (time.monotonic() - self.last_sent)))
                writer.write(chat_line(self.channel, message_id, text))
                await writer.drain()
                self.last_sent = time.monotonic()
            finally:
                self.queue.task_done()


    async def keep_auth_valid(self, writer, token):
        while True:
            await asyncio.sleep(1800)
            new_token, _ = await self.auth.valid()
            if new_token != token:
                writer.close()
                return


    async def run(self):
        delay = 2
        try:
            while True:
                tasks = []
                writer = None
                try:
                    token, login = await self.auth.valid()
                    reader, writer = await asyncio.wait_for(asyncio.open_connection(
                        "irc.chat.twitch.tv", 6697, ssl=ssl.create_default_context(), limit=65536), timeout=20)
                    self.writer = writer
                    writer.write((f"PASS oauth:{token}\r\nNICK {login}\r\n"
                        "CAP REQ :twitch.tv/tags twitch.tv/commands\r\n"
                        f"JOIN #{self.channel}\r\n").encode())
                    await writer.drain()
                    logging.info("Twitch login sent as %s for #%s", login, self.channel)
                    delay = 2
                    tasks = [asyncio.create_task(self.receive_loop(reader, writer, login)),
                        asyncio.create_task(self.send_loop(writer)),
                        asyncio.create_task(self.keep_auth_valid(writer, token))]
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        task.result()
                except (OSError, TimeoutError, ValueError) as e:
                    self.status = "Twitch disconnected; retrying"
                    logging.warning("Twitch reconnect needed (%s). If this persists, reconnect Twitch in Settings > Integrations.", type(e).__name__)
                finally:
                    self.status = "Twitch disconnected; retrying"
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    if writer:
                        writer.close()
                        try:
                            await writer.wait_closed()
                        except OSError:
                            pass
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
        finally:
            for task in list(self.work):
                task.cancel()
            await asyncio.gather(*self.work, return_exceptions=True)

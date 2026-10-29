"""LXMF bot that sends new gluek.info posts to its subscribers over Reticulum.

Commands (any case, with or without a leading slash):
  подписаться / sub        subscribe to new posts
  отписаться / unsub       unsubscribe
  последние / last         the latest posts, no subscription needed
Anything else gets a short help.

New posts come from the RSS feed. The first poll only remembers what is already
there, so a fresh database never floods subscribers with the whole archive.
Messages go directly; if a subscriber is offline, through a propagation node.
"""
import os
import threading
import time

import LXMF
import RNS
from LXMF.LXMF import pn_announce_data_is_valid
from RNS.vendor import umsgpack

import feed
from database import Database

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
RNS_CONFIG = os.environ.get("RNS_CONFIG", os.path.join(DATA_DIR, "reticulum"))
FEED_URL = os.environ.get("FEED_URL", "https://gluek.info/rss.xml")
NODE_HASH = os.environ.get("NODE_HASH", "")  # NomadNet mirror, for links in messages
DISPLAY_NAME = os.environ.get("DISPLAY_NAME", "gluek.info")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "900"))
ANNOUNCE_INTERVAL = int(os.environ.get("ANNOUNCE_INTERVAL", str(6 * 3600)))
LAST_COUNT = int(os.environ.get("LAST_COUNT", "5"))
PROPAGATION_NODE = os.environ.get("PROPAGATION_NODE", "")  # empty: the nearest one heard
MONITOR_URL = os.environ.get("MONITOR_URL", "")  # pinged after every successful feed poll
# Path requests and delivery to an address the bot has never heard of can take a while
PATH_TIMEOUT = 30

COMMANDS = {
    "sub": {"подписаться", "подписка", "sub", "subscribe", "start"},
    "unsub": {"отписаться", "отписка", "unsub", "unsubscribe", "stop"},
    "last": {"последние", "последнее", "last", "latest"},
}

HELP = """Привет! Я присылаю новые посты блога gluek.info.

Команды:
  подписаться — присылать новые посты
  отписаться — больше не присылать
  последние — {count} последних постов

Зеркало блога в NomadNet: {node}
Сайт: https://gluek.info"""


def parse_command(text):
    word = (text or "").strip().lstrip("/").split(maxsplit=1)
    word = word[0].lower() if word else ""
    for command, aliases in COMMANDS.items():
        if word in aliases:
            return command
    return "help"


class PropagationNodes:
    """Remembers announced propagation nodes, so the nearest one can be used for offline subscribers."""
    aspect_filter = "lxmf.propagation"

    def __init__(self):
        self.nodes = set()

    def received_announce(self, destination_hash, announced_identity, app_data):
        try:
            if app_data and pn_announce_data_is_valid(app_data) and umsgpack.unpackb(app_data)[2]:
                self.nodes.add(destination_hash)
        except Exception:
            pass

    def nearest(self):
        known = [h for h in self.nodes if RNS.Transport.has_path(h)]
        return min(known, key=RNS.Transport.hops_to) if known else None


class Bot:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.db = Database(os.path.join(DATA_DIR, "bot.db"))
        self.reticulum = RNS.Reticulum(RNS_CONFIG)

        identity_path = os.path.join(DATA_DIR, "identity")
        if os.path.isfile(identity_path):
            self.identity = RNS.Identity.from_file(identity_path)
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(identity_path)

        self.router = LXMF.LXMRouter(identity=self.identity, storagepath=os.path.join(DATA_DIR, "lxmf"))
        self.destination = self.router.register_delivery_identity(self.identity, display_name=DISPLAY_NAME)
        self.router.register_delivery_callback(self.on_message)

        self.pn = PropagationNodes()
        RNS.Transport.register_announce_handler(self.pn)
        if PROPAGATION_NODE:
            self.router.set_outbound_propagation_node(bytes.fromhex(PROPAGATION_NODE))

        self.posts = []  # latest feed, newest first
        RNS.log(f"LXMF address of the bot: {RNS.prettyhexrep(self.destination.hash)}", RNS.LOG_NOTICE)

    # --- Incoming messages ---------------------------------------------------

    def on_message(self, message):
        sender = message.source_hash
        command = parse_command(message.content_as_string())
        RNS.log(f"Command {command} from {RNS.prettyhexrep(sender)}", RNS.LOG_INFO)

        if command == "sub":
            new = self.db.subscribe(sender.hex())
            text = ("Готово, новые посты будут приходить сюда. Отписаться — «отписаться»." if new
                    else "Вы уже подписаны. Отписаться — «отписаться».")
            self.send(sender, "Подписка", text)
        elif command == "unsub":
            gone = self.db.unsubscribe(sender.hex())
            self.send(sender, "Подписка", "Вы отписаны." if gone else "Вы и не были подписаны.")
        elif command == "last":
            posts = self.posts[:LAST_COUNT]
            if not posts:
                self.send(sender, "Последние посты", "Лента пока не загружена, попробуйте через пару минут.")
            for post in reversed(posts):
                self.send(sender, *feed.message_for(post, NODE_HASH))
        else:
            self.send(sender, DISPLAY_NAME, HELP.format(count=LAST_COUNT, node=f"{NODE_HASH}:/page/index.mu"))

    # --- Outgoing messages ---------------------------------------------------

    def recall(self, dest_hash):
        """Identity behind an LXMF address, asking the network for a path if it is unknown."""
        identity = RNS.Identity.recall(dest_hash)
        if identity is None:
            RNS.Transport.request_path(dest_hash)
            deadline = time.time() + PATH_TIMEOUT
            while identity is None and time.time() < deadline:
                time.sleep(0.5)
                identity = RNS.Identity.recall(dest_hash)
        return identity

    def send(self, dest_hash, title, content):
        threading.Thread(target=self._send, args=(dest_hash, title, content), daemon=True).start()

    def _send(self, dest_hash, title, content):
        identity = self.recall(dest_hash)
        if identity is None:
            RNS.log(f"No identity known for {RNS.prettyhexrep(dest_hash)}, message dropped", RNS.LOG_WARNING)
            return
        destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        message = LXMF.LXMessage(destination, self.destination, content, title=title,
                                 desired_method=LXMF.LXMessage.DIRECT)
        message.register_failed_callback(self.on_failed)
        self.router.handle_outbound(message)

    def on_failed(self, message):
        """Direct delivery failed (the recipient is offline): leave it on a propagation node."""
        if message.desired_method == LXMF.LXMessage.PROPAGATED:
            RNS.log(f"Could not deliver to {RNS.prettyhexrep(message.destination_hash)} even via propagation",
                    RNS.LOG_WARNING)
            return
        node = self.router.get_outbound_propagation_node() or self.pn.nearest()
        if node is None:
            RNS.log("Direct delivery failed and no propagation node is known yet", RNS.LOG_WARNING)
            return
        self.router.set_outbound_propagation_node(node)
        RNS.log(f"{RNS.prettyhexrep(message.destination_hash)} is offline, leaving the message on "
                f"propagation node {RNS.prettyhexrep(node)}", RNS.LOG_NOTICE)
        retry = LXMF.LXMessage(message.get_destination(), self.destination, message.content, title=message.title,
                               desired_method=LXMF.LXMessage.PROPAGATED)
        retry.register_failed_callback(self.on_failed)
        retry.register_delivery_callback(lambda m: RNS.log(
            f"Message for {RNS.prettyhexrep(m.destination_hash)} accepted by the propagation node", RNS.LOG_NOTICE))
        self.router.handle_outbound(retry)

    # --- Feed ----------------------------------------------------------------

    def poll(self):
        self.posts = feed.parse(feed.fetch(FEED_URL))
        guids = [p.guid for p in self.posts]
        if not self.db.has_seen_any():
            self.db.mark_seen(guids)
            RNS.log(f"First poll: {len(guids)} existing posts remembered, nothing sent", RNS.LOG_NOTICE)
            return
        new = set(self.db.unseen(guids))
        for post in reversed([p for p in self.posts if p.guid in new]):
            subscribers = self.db.subscribers()
            RNS.log(f"New post «{post.title}», sending to {len(subscribers)} subscribers", RNS.LOG_NOTICE)
            for hash_hex in subscribers:
                self.send(bytes.fromhex(hash_hex), *feed.message_for(post, NODE_HASH))
        self.db.mark_seen(guids)

    def run(self):
        next_poll = next_announce = 0
        while True:
            now = time.time()
            if now >= next_announce:
                self.router.announce(self.destination.hash)
                next_announce = now + ANNOUNCE_INTERVAL
            if now >= next_poll:
                try:
                    self.poll()
                    if MONITOR_URL:
                        feed.fetch(MONITOR_URL, timeout=10)
                except Exception as e:
                    RNS.log(f"Feed poll failed: {e}", RNS.LOG_ERROR)
                next_poll = now + POLL_INTERVAL
            time.sleep(5)


if __name__ == "__main__":
    Bot().run()

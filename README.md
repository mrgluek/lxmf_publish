# LXMF Publish Bot (`lxmf_publish`)

An [LXMF](https://github.com/markqvist/LXMF) bot that sends new posts of [gluek.info](https://gluek.info) to its subscribers over the [Reticulum](https://reticulum.network) network (Sideband, Columba, MeshChat, NomadNet).

LXMF address: `777777779e7beceb13399c0ab0c63613`

## Commands

Send any of these to the bot (any case, a leading `/` is fine):

| Command | Aliases | |
|---|---|---|
| `подписаться` | `sub`, `subscribe`, `start` | send new posts |
| `отписаться` | `unsub`, `unsubscribe`, `stop` | stop sending |
| `последние` | `last`, `latest` | the latest posts, no subscription needed |

Anything else gets a short help with links to the NomadNet mirror and the site.

## How it works

- **New posts** come from the RSS feed (`FEED_URL`), polled every `POLL_INTERVAL` seconds. The first poll of a fresh database only remembers the posts that are already there, so subscribers never get the whole archive.
- **Messages** link to the post on the NomadNet mirror (`NODE_HASH`) and on the site.
- **Delivery** is direct first. If a subscriber is offline, the message is left on a propagation node: `PROPAGATION_NODE`, or the nearest one announced on the network. The subscriber's client picks it up on its next sync.
- **Announces** of the bot's address go out at start and every `ANNOUNCE_INTERVAL` seconds (6 hours).
- **Not a relay:** the bot's Reticulum instance must run with `enable_transport = No`, so it never forwards other nodes' traffic.

State lives in `data/`: `identity` (the bot's key, 64 bytes, keep it private), `bot.db` (subscribers and announced posts), `lxmf/` (LXMF router storage) and `reticulum/` (Reticulum config and storage).

## Setup

```sh
git clone https://github.com/mrgluek/lxmf_publish.git && cd lxmf_publish
cp .env.example .env
mkdir -p data/reticulum
# data/identity: put an existing key here, or let the bot create a new one on first start
# data/reticulum/config: see below
sudo chown -R 10002:10002 data && sudo chmod 700 data
docker compose up -d --build
docker compose logs -f   # shows "LXMF address of the bot: <…>"
```

A minimal `data/reticulum/config`: two entry points, no transport.

```ini
[reticulum]
  enable_transport = No
  share_instance = No

[logging]
  loglevel = 3

[interfaces]
  [[RNS Moscow catz]]
    type = TCPClientInterface
    enabled = yes
    target_host = catz.rns.moscow
    target_port = 4242

  [[RMAP Germany]]
    type = TCPClientInterface
    enabled = yes
    target_host = rmap.world
    target_port = 4242
```

## Updates

`update.sh` deploys the newest `vX.Y.Z` tag (pin one with `UPDATE_REF` in `.env.local`). It fetches from GitHub and falls back to the [Forgejo mirror](https://git.gluek.info/gluek/lxmf_publish) when GitHub is unreachable. Run it from cron:

```sh
*/10 * * * * /bin/bash /root/lxmf_publish/update.sh >> /root/lxmf_publish/update.log 2>&1
```

## Tests

```sh
python -m unittest -v
```

## License

MIT, see [LICENSE](LICENSE).

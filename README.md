# home-control

Local-only control of home devices. No cloud. Today it drives Tuya Wi-Fi curtain/shutter switches over the LAN (`tuya_lan`).
The library holds no device data: the application using it owns a JSON device file and passes its contents in.

## Install

```
pip install "home-control @ https://github.com/aGallea/home-control/releases/download/v0.2.1/home_control-0.2.1-py3-none-any.whl"
```

## Use

```python
from home_control import Home, load_config_file

home = Home.from_config(load_config_file(path_you_choose))
await home.down("Kitchen")
```

## Device file (version 1)

```json
{
  "version": 1,
  "rooms": {"Kitchen": {"aliases": ["המטבח"]}},
  "devices": [
    {
      "name": "Kitchen left",
      "room": "Kitchen",
      "type": "shutter",
      "backend": "tuya_lan",
      "connection": {"id": "dev-kitchen-left", "ip": "192.0.2.10", "key": "0123456789abcdef", "version": 3.3},
      "options": {"inverted": false}
    }
  ]
}
```

Keep the file readable only by you (`chmod 600`); it holds local keys. Devices with a `type` or `backend` this version doesn't know are skipped and listed in `Home.skipped`.

## CLI

```
home-control --config path/to/home.json list
home-control --config path/to/home.json down Kitchen
home-control --config path/to/home.json status all
home-control --config path/to/home.json import tinytuya-devices.json
home-control --config path/to/home.json scan
```

`HOME_CONTROL_CONFIG` can stand in for `--config`.

## Contributing

Never commit device data. Install a local pre-push hook (it stays in `.git/hooks`, so your paths never reach the repo):

```sh
cat > .git/hooks/pre-push <<'HOOK'
#!/bin/sh
cd "$(git rev-parse --show-toplevel)" || exit 1
uv run --quiet pytest -q tests/test_privacy.py || exit 1
python3 scripts/check_no_private_data.py --also you@example.com path/to/your/home.json path/to/tinytuya-devices.json
HOOK
chmod 700 .git/hooks/pre-push
```

The check scans every commit (content, messages, identities, merges, tags) for values from your device files and
prints any match redacted. Values shorter than four characters are matched as whole words.

"""ntfy.sh backend: zero-config pub/sub. No signup, no token.

Each message is one ntfy publish; polling reads the JSON stream. Message
history on the free tier is limited (cached briefly), so this backend suits
high-frequency ping-style relays better than long archives. Use an
unguessable topic name — anyone with the topic can read it.
"""
import json
import urllib.request
import urllib.error
import urllib.parse


class NtfyBackend:
    name = "ntfy"

    def __init__(self, cfg):
        self.topic = cfg["topic"]
        self.base = cfg.get("server", "https://ntfy.sh").rstrip("/")

    def setup(self):
        return {}  # nothing to create; topics are implicit

    def _url(self, suffix=""):
        return f"{self.base}/{urllib.parse.quote(self.topic, safe='')}{suffix}"

    def append(self, msg):
        data = json.dumps(msg).encode()
        r = urllib.request.Request(
            self._url(), data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(r, timeout=30):
                pass
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ntfy {e.code}: {e.read().decode()[:200]}")

    def read(self):
        # pull cached messages as JSON stream, one object per line
        r = urllib.request.Request(
            self._url("/json?since=72h"), method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                out = []
                for line in resp.read().decode().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    ev = json.loads(line)
                    if ev.get("event") == "message":
                        try:
                            out.append(json.loads(ev["message"]))
                        except (json.JSONDecodeError, TypeError):
                            pass
                return out
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"ntfy {e.code}: {e.read().decode()[:200]}")

    def update(self, msg_id, patch):
        # ntfy is append-only: status changes are new messages referencing the id
        self.append({"id": msg_id, "type": "_patch", "patch": patch})

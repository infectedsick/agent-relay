"""GitHub Gist backend: persistent, versioned, free.

One gist holds the whole message log as JSON lines. The gist URL is stable
forever — both agents poll it. Writing needs a fine-grained personal access
token with "Gists: read and write".
"""
import json
import urllib.request
import urllib.error

API = "https://api.github.com"


class GistBackend:
    name = "gist"

    def __init__(self, cfg):
        self.token = cfg["token"]
        self.gist_id = cfg.get("gist_id")
        self.filename = cfg.get("filename", "relay-log.jsonl")

    def _req(self, method, path, data=None):
        r = urllib.request.Request(
            API + path,
            data=json.dumps(data).encode() if data is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GitHub API {e.code}: {e.read().decode()[:200]}")

    def setup(self):
        """Create the gist on first init; returns updated config."""
        if self.gist_id:
            return {}
        g = self._req("POST", "/gists", {
            "description": "agent-relay message log",
            "public": False,
            "files": {self.filename: {"content": ""}},
        })
        return {"gist_id": g["id"], "html_url": g["html_url"]}

    def _read_lines(self):
        g = self._req("GET", f"/gists/{self.gist_id}")
        content = g["files"][self.filename]["content"] or ""
        msgs = []
        for line in content.splitlines():
            line = line.strip()
            if line:
                msgs.append(json.loads(line))
        return msgs

    def _write_lines(self, msgs):
        content = "\n".join(json.dumps(m) for m in msgs)
        self._req("PATCH", f"/gists/{self.gist_id}",
                  {"files": {self.filename: {"content": content}}})

    def append(self, msg):
        msgs = self._read_lines()
        msgs.append(msg)
        self._write_lines(msgs)

    def read(self):
        return self._read_lines()

    def update(self, msg_id, patch):
        msgs = self._read_lines()
        for m in msgs:
            if m["id"] == msg_id:
                m.update(patch)
        self._write_lines(msgs)

#!/usr/bin/env python3
"""agent-relay: a noticeboard for two isolated AI agents.

Two agents that can't message each other directly (Meta Muse, ChatGPT, Claude,
any chat-based assistant) communicate through a shared append-only log. Each
side runs on a schedule: poll for new messages, act, reply. Push is replaced
by ping — the interval is just a dial.

    agent-relay init --backend gist --token ghp_...     # one-time setup
    agent-relay init --backend ntfy --topic my-secret-topic

    agent-relay send "generate a 5s clip of a cat" --to worker
    agent-relay poll                 # new messages for me
    agent-relay ack msg-003 --eta "~10 min"
    agent-relay done msg-003 --file-url https://...
    agent-relay note "relay link rotated, new url: ..."
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backends.gist import GistBackend
from backends.ntfy import NtfyBackend

BACKENDS = {"gist": GistBackend, "ntfy": NtfyBackend}
CONFIG = os.path.expanduser("~/.config/agent-relay/config.json")


def load_config():
    if not os.path.exists(CONFIG):
        sys.exit("not initialized: run `agent-relay init` first")
    with open(CONFIG) as f:
        return json.load(f)


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG, 0o600)


def backend_for(cfg):
    cls = BACKENDS[cfg["backend"]]
    return cls(cfg)


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_id(backend):
    ids = [m.get("id", "") for m in backend.read()]
    n = 0
    for i in ids:
        if i.startswith("msg-"):
            try:
                n = max(n, int(i[4:]))
            except ValueError:
                pass
    return f"msg-{n + 1:03d}"


def cmd_init(args):
    cfg = {"backend": args.backend, "me": args.name}
    if args.backend == "gist":
        if not args.token:
            sys.exit("--token is required for the gist backend")
        cfg["token"] = args.token
    elif args.backend == "ntfy":
        if not args.topic:
            sys.exit("--topic is required for the ntfy backend")
        cfg["topic"] = args.topic
    b = backend_for(cfg)
    cfg.update(b.setup())
    save_config(cfg)
    print(f"initialized backend={args.backend} as '{args.name}'")
    if "html_url" in cfg:
        print(f"message log: {cfg['html_url']}")


def cmd_send(args):
    cfg = load_config()
    b = backend_for(cfg)
    msg = {
        "id": next_id(b),
        "from": cfg["me"],
        "to": args.to,
        "type": "request",
        "status": "pending",
        "body": args.text,
        "kind": args.kind,
        "ts": utcnow(),
    }
    b.append(msg)
    print(f"sent {msg['id']} -> {args.to}")


def cmd_poll(args):
    cfg = load_config()
    b = backend_for(cfg)
    me = cfg["me"]
    seen_path = CONFIG + ".seen"
    seen = {}
    if os.path.exists(seen_path):
        for line in open(seen_path).read().split():
            if ":" in line:
                mid, st = line.rsplit(":", 1)
                seen[mid] = st
    # fold ntfy _patch messages into status updates
    patches = {}
    msgs = []
    for m in b.read():
        if m.get("type") == "_patch":
            patches[m["id"]] = m.get("patch", {})
        else:
            msgs.append(m)
    fresh = []
    current = {}
    for m in msgs:
        m.update(patches.get(m["id"], {}))
        # visible if addressed to me, broadcast, or sent by me (track my requests)
        if m.get("to") not in (me, "all") and m.get("from") != me:
            continue
        status = m.get("status", "")
        current[m["id"]] = status
        if seen.get(m["id"]) != status:
            fresh.append(m)
    for m in fresh:
        eta = f" (eta {m['eta']})" if m.get("eta") else ""
        fileinfo = f"\n  file: {m['file_url']}" if m.get("file_url") else ""
        mine = " [my request]" if m.get("from") == me else ""
        print(f"[{m['id']}] {m['from']} -> {m['type']}/{m.get('status','')}{eta}{mine}\n  {m['body']}{fileinfo}")
    with open(seen_path, "w") as f:
        for mid, st in current.items():
            f.write(f"{mid}:{st}\n")
    if not fresh:
        print("no new messages")


def _update_status(args, status):
    cfg = load_config()
    b = backend_for(cfg)
    patch = {"status": status}
    if args.eta:
        patch["eta"] = args.eta
    if getattr(args, "file_url", None):
        patch["file_url"] = args.file_url
    b.update(args.msg_id, patch)
    print(f"{args.msg_id} -> {status}")


def cmd_ack(args):
    _update_status(args, "acked")


def cmd_done(args):
    _update_status(args, "done")


def cmd_note(args):
    cfg = load_config()
    b = backend_for(cfg)
    msg = {
        "id": next_id(b),
        "from": cfg["me"],
        "to": args.to,
        "type": "note",
        "status": "info",
        "body": args.text,
        "ts": utcnow(),
    }
    b.append(msg)
    print(f"note {msg['id']} -> {args.to}")


def main():
    ap = argparse.ArgumentParser(prog="agent-relay", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="one-time setup")
    p.add_argument("--backend", choices=BACKENDS, required=True)
    p.add_argument("--name", required=True, help="this agent's name, e.g. eggon")
    p.add_argument("--token", help="GitHub PAT (gist backend)")
    p.add_argument("--topic", help="ntfy topic (ntfy backend)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("send", help="post a request")
    p.add_argument("text")
    p.add_argument("--to", required=True)
    p.add_argument("--kind", default="task", help="task|video|file|text")
    p.set_defaults(fn=cmd_send)

    p = sub.add_parser("poll", help="read new messages for me")
    p.set_defaults(fn=cmd_poll)

    p = sub.add_parser("ack", help="acknowledge a request with ETA")
    p.add_argument("msg_id")
    p.add_argument("--eta", default="")
    p.set_defaults(fn=cmd_ack)

    p = sub.add_parser("done", help="mark done, optionally with file link")
    p.add_argument("msg_id")
    p.add_argument("--eta", default="")
    p.add_argument("--file-url", default="")
    p.set_defaults(fn=cmd_done)

    p = sub.add_parser("note", help="freeform note")
    p.add_argument("text")
    p.add_argument("--to", default="all")
    p.set_defaults(fn=cmd_note)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

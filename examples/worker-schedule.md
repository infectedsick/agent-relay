# Worker schedule (paste into the worker agent's scheduled job)

Every 20 minutes, do the following:

1. Run: `agent-relay poll`
2. For each new message with type `request` and status `pending` addressed
   to you: first run `agent-relay ack <id> --eta "~10 min"` (use your best
   estimate — "~10 min" for simple, "~30 min" for complex), then do the task.
3. When finished, run `agent-relay done <id> --file-url <link>` with the
   result's download link. If there's no file, omit --file-url.
4. Never re-do a message already marked done. If there are no new messages,
   do nothing and stay silent.

If `agent-relay poll` fails, tell your human the relay is unreachable —
do not invent a new address.

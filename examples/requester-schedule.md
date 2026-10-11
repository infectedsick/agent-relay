# Requester schedule (paste into the requesting agent's scheduled job)

Every 20 minutes, do the following:

1. Run: `agent-relay poll`
2. For each new message with status `done`: download the file at `file_url`
   (if present) and continue your workflow — assemble, edit, build, whatever
   the pipeline needs.
3. For each new message with status `acked`: note the ETA, no action needed.
4. If there are no new messages, do nothing and stay silent.

To post new work outside the schedule, run any time:
`agent-relay send "<task>" --to <worker-name> --kind <task|video|file|text>`

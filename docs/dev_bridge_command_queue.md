# Pixiu Dev Bridge Command Queue / Clipboard Bundle

## Purpose

This helper reduces repetitive copy/paste in the Pixiu local development loop.

It lets a local queue run safe commands, save logs, and generate an AI-ready bundle for review.

## Commands

```bash
python3 scripts/pixiu_dev_queue.py status
python3 scripts/pixiu_dev_queue.py classify --queue templates/pixiu_command_queue.template.json
python3 scripts/pixiu_dev_queue.py execute --queue templates/pixiu_command_queue.template.json
python3 scripts/pixiu_dev_queue.py bundle --limit 5
```

Wrapper:

```bash
./scripts/run_pixiu_dev_queue.sh status
./scripts/run_pixiu_dev_queue.sh classify --queue templates/pixiu_command_queue.template.json
./scripts/run_pixiu_dev_queue.sh execute --queue templates/pixiu_command_queue.template.json
./scripts/run_pixiu_dev_queue.sh bundle --limit 5
```

## Level Rules

Level 1: inspect, status, compile, syntax check, query, targeted verifier.

Level 2: local report generation, normal verification, docs/templates/scripts.

Level 3: commit, push, snapshot, delete, schema/migration, scoring formula changes, provider/API integration, safety-boundary changes.

Level 3 queues are refused unless explicitly run with:

```bash
--yes-level3
```

## Output

```text
outputs/dev_loop_queue/
```

The generated `AI_BUNDLE.txt` is suitable for pasting back into ChatGPT / Claude Code / Codex / Cursor Agent.

# Pixiu Daily Queue Presets

## Purpose

Daily queue presets make the v2.2F.1 command queue useful for regular research operations.

The default preset runs the proven daily research workflow:

```bash
./scripts/run_pixiu_daily_queue.sh
```

## Classify Only

```bash
./scripts/run_pixiu_daily_queue.sh classify
```

Expected:

```text
max_level: 2
requires_yes_level3: no
```

## Execute

```bash
./scripts/run_pixiu_daily_queue.sh
```

Equivalent explicit command:

```bash
./scripts/run_pixiu_daily_queue.sh execute
```

## Bundle Latest Logs

```bash
./scripts/run_pixiu_daily_queue.sh bundle
```

## Verify Preset

```bash
./scripts/verify_pixiu_daily_queue.sh
```

## Preset Template

```text
templates/pixiu_daily_research_queue.template.json
```

## Safety

This preset is research-only.

It does not:

- connect to brokerage
- place orders
- automate trading
- store credentials
- add provider/API integration
- change schema
- change scoring formulas

Generated queue logs remain ignored under:

```text
outputs/dev_loop_queue/
```

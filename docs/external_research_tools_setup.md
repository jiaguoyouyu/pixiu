# External Research Tools Setup

Manual setup helper for Pixiu external research tools.

Required notices:

- Not financial advice
- Model output requires human review
- Data quality may affect results
- Research-only. No brokerage connection, no order placement, no account scraping, no credential storage.

## Tool Roles

- Koyfin = chart/dashboard visual layer.
- Fiscal.ai = fundamental analyst research layer.
- Quartr = earnings call/transcript layer.

## Recommended Free-First Setup

1. Start with free or lowest-commitment plans where available.
2. Register manually in your browser.
3. Verify email manually.
4. Skip payment or trial forms unless you intentionally choose to subscribe.
5. Do not store passwords, session cookies, tokens, or API keys in this project.
6. Keep Pixiu outputs as research inputs only.

## Koyfin Manual Signup Checklist

Official URL: https://app.koyfin.com/register

Manual steps:

1. Open the official Koyfin registration page.
2. Review the current plan options and free access limits.
3. Register manually using your own email and password manager.
4. Complete CAPTCHA and email verification manually.
5. Sign in manually after verification.
6. Create watchlists manually using `outputs/koyfin_watchlists.csv` or `outputs/koyfin_watchlists.md` as references.
7. Verify ticker symbols, exchange suffixes, ETF availability, and CAD-listed alternatives inside Koyfin.

Pixiu use:

- Use Koyfin for chart review, relative strength, dashboards, sector views, ETF holdings checks, and visual confirmation.
- Do not treat Koyfin charts as automatic buy/sell signals.

Do not automate:

- Registration form filling.
- Login.
- CAPTCHA.
- Email verification.
- Payment or trial submission.
- Watchlist upload if it requires private account interaction.

## Fiscal.ai Manual Signup Checklist

Official URL: https://fiscal.ai/

Manual steps:

1. Open the official Fiscal.ai page.
2. Review available free, trial, or paid research features.
3. Register manually if you decide to use it.
4. Complete email verification manually.
5. Do not add Fiscal.ai API keys to this project.
6. Use `outputs/fiscal_ai_research_questions.md` as a manual prompt queue.
7. Paste only non-private research prompts that you are comfortable sharing with the service.

Pixiu use:

- Use Fiscal.ai for fundamentals, financial statements, analyst-style questions, comparable company review, and thesis validation.
- Fiscal.ai API integration remains disabled/stubbed unless explicitly requested later.

Do not automate:

- Registration form filling.
- Login.
- CAPTCHA.
- Email verification.
- Payment or trial submission.
- API key capture, storage, or printing.

## Quartr Manual Signup Checklist

Official URL: https://quartr.com/

Manual steps:

1. Open the official Quartr page.
2. Review app, web, and plan availability.
3. Register manually if you decide to use it.
4. Complete email verification manually.
5. Search for earnings calls, transcripts, investor presentations, and management commentary manually.
6. Use findings to update research notes outside this project, or summarize them manually into your own workflow.

Pixiu use:

- Use Quartr for earnings calls, transcripts, investor events, management guidance, margin commentary, and demand signals.
- Re-run the Pixiu after important earnings events or guidance updates.

Do not automate:

- Registration form filling.
- Login.
- CAPTCHA.
- Email verification.
- Payment or trial submission.
- Transcript scraping or bulk downloading.

## What Not To Automate

Do not use scripts, browser automation, scraping, or hidden API calls for:

- Creating accounts.
- Logging in.
- Completing CAPTCHA.
- Verifying email.
- Submitting payment, billing, or trial forms.
- Extracting session cookies.
- Storing passwords, tokens, API keys, or private account data.
- Bypassing product limits or terms of service.

## Daily Manual Workflow

1. Run Pixiu daily outputs.
2. Run research desk exports:

```bash
./scripts/run_research_desk_exports.sh
```

3. Open the manual setup/helper links:

```bash
./scripts/open_external_research_tools.sh
```

4. Use Koyfin for visual chart/dashboard review.
5. Use Fiscal.ai prompts manually for fundamentals and thesis review.
6. Use Quartr manually for call/transcript review.
7. Keep all final decisions under human review.

## Safety Reminder

These external tools are research aids only. Pixiu does not place trades, connect to brokerages, manage accounts, submit orders, or recommend naked options.

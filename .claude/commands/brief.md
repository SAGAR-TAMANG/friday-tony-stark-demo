---
description: Run FRIDAY's morning briefing — news, markets, weather, calendar
---

Invoke the morning briefing flow by calling the MCP tools in this order and summarizing the result:

1. `get_world_news` (top 5)
2. `get_market_overview` (S&P, NASDAQ, BTC, ETH)
3. `get_weather` for the user's default city (fall back to "New York" if unset)
4. `get_todays_events` (calendar — skip silently if no creds)
5. `check_mail` unread count only (skip silently if no creds)

Format the output as a single Tony-Stark-flavored briefing, <150 words, no bullet salad. End with one suggested action.

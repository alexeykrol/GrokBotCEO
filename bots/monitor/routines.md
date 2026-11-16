# Monitor routines

Grok Bot keeps routines on its server, not in files. A bot creates its own routines when asked.
None is created without the user's yes: the install plan asks once ("Yes, with routines"), or the
user asks Monitor in its chat later.

- **weekly report** — every Sunday at 20:00 in the user's timezone (cron form:
  `CRON_TZ=<the user's timezone> 0 20 * * 0`). Monitor writes the report for the week that ends
  that Sunday in its own chat and sends the proposals to Bot Maker, which shows each change in
  #Improvements and applies it only after the user's yes.

The user can change the day or time, or stop the report, by telling Monitor in its chat.

# discord-badge-spoofer

A tool for inflating your Discord profile badges by adding playtime hours and marking games as played.

## overview

This project does not send your information to a remote server. Your Discord token and cookie are saved only on your own machine in `science_state.json` and are not shared with anyone else.

The tool posts the same analytics events Discord itself uses (`launch_game` and `running_game_heartbeat`) to the `/api/v9/science` endpoint, but with custom game lists and playtime values.

**Important:** the token and cookie belong to your own account only. They are stored locally on your device and are not uploaded to a third-party service by this project.

**Status:** experimental. Discord accepting the events (HTTP 204) does not guarantee a badge changes, and Discord may patch the endpoint at any time. Badge updates are not instant and can take around 1 to 3 days to appear.

**Note:** this tool is open source and available for review. It is provided as-is without warranty. It may break Discord's Terms of Service, so only use it on accounts you are comfortable with risking.

## join https://discord.gg/haland2 for support

**First run:** the tool asks you to open a YouTube channel and a Discord invite (10 second wait each) before it continues.

## setup

no dependencies - pure python stdlib (needs python 3.10+).

1. run it:
   ```
   python spoofer.py
   ```

2. first run asks for your discord account token. paste it and it gets saved to `science_state.json` (reused after that). the analytics token is fetched automatically from `GET /users/@me?with_analytics_token=true`.

3. you also need a cookie (`cf_clearance`). on startup it'll ask for one, or you can add/update it later via option `2` (refresh auth). grab the full `cookie` header from any `/science` request in devtools (network tab). it gets saved to `science_state.json`.

4. **optional: fingerprint for games-played count.** the fingerprint isn't strictly necessary - users have reported getting the games-played badge without setting one. if you want to set it, grab a real `executable_fingerprint` from a `launch_game` request in your client's devtools and add it to `science_state.json` as `"fingerprint": "..."`.

## menu

- `1` claim games - asks how many games and hours per game, then sends the events
- `2` refresh auth - pulls a fresh analytics token and lets you update the cookie
- `3` set fingerprint - windows only, generates an `executable_fingerprint` from a game exe path or pid
- `4` exit

## how auth works

- `token` - your account token, entered on first run, saved to `science_state.json`
- `analytics_token` - fetched from `GET /users/@me?with_analytics_token=true`
- `super_props` / heartbeat / launch ids - generated automatically
- `cookie` (cf_clearance) - pasted by hand, via option `2`
- `fingerprint` - optional, only needed for the games-played count (see below)

badges update on discord's analytics cycle (1-2 days), so don't expect to see results right away.

## about the fingerprint

hours work with just your token and cookie. the games-played count might need a real `executable_fingerprint` - we're not 100% sure yet. users have reported getting badges without one, so try it first. if it doesn't work after a few days, grab a real `executable_fingerprint` from a `launch_game` request in your client's devtools and add it to `science_state.json`:

```json
{ "fingerprint": "Ab5ekw..." }
```

either way, the tool will post the events - we just want feedback on whether the badges move with or without the fingerprint so we can figure out what's actually required.

## disclaimer

this breaks discord's terms of service. use it on accounts you're fine losing.
provided as-is with no warranty.

## license

released under the mit license. see [LICENSE](LICENSE).

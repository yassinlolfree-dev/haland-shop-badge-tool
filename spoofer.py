#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import webbrowser
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator, Sequence

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = Path(__file__).resolve().parent
GAMES_FILE = ROOT.parent / "data" / "games.json"
STATE_FILE = ROOT / "science_state.json"

ME_URL = "https://discord.com/api/v9/users/@me?with_analytics_token=true"
SCIENCE_URL = "https://discord.com/api/v9/science"
PROPERTIES_URL = "https://cordapi.dolfi.es/api/v2/properties/windows"
GAMES_CDN_URL = "https://cdn.discordapp.com/detectables/games.json"
SUBSCRIBE_URL = "https://www.youtube.com/@Channel-Haland?sub_confirmation=1"
DISCORD_INVITE_LABEL = "discord.gg/haland2"
DISCORD_INVITE_URL = "https://discord.gg/haland2"
GATE_WAIT = 10

BATCH_SIZE = 50
BATCH_DELAY = 1
AUTH_MAX_AGE = 12 * 3600
DEBUG = False

CLIENT_VERSION = "1.0.9253"
CLIENT_BUILD_NUMBER = 594031
NATIVE_BUILD_NUMBER = 88414
OS_VERSION = "10.0.26200"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) discord/1.0.9253 Chrome/148.0.7778.280 "
    "Electron/42.7.1 Safari/537.36"
)


def _user_id_from_token(token: str) -> str:
    try:
        first = token.split(".", 1)[0]
        pad = "=" * (-len(first) % 4)
        return base64.b64decode(first + pad).decode("utf-8")
    except Exception:
        return ""


_FINGERPRINT_PS1 = r'''
param(
  [int]$ProcessId = 0,
  [string]$Path,
  [Parameter(Mandatory = $true)][string]$UserId
)
'''


def generate_fingerprint(user_id: str, path: str = "", pid: int = 0) -> str:
    if os.name != "nt":
        raise RuntimeError("fingerprint generation is windows-only")
    script = Path(tempfile.gettempdir()) / f"disc_fp_{uuid.uuid4().hex}.ps1"
    script.write_text(_FINGERPRINT_PS1, encoding="utf-8")
    try:
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(script), "-UserId", user_id]
        args += (["-ProcessId", str(pid)] if pid else ["-Path", path])
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "powershell failed")
    out = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not out:
        raise RuntimeError("generator produced no output")
    return out[-1]


class Console:
    RED = "\x1b[91m"
    ORANGE = "\x1b[38;5;46m"
    GREEN = "\x1b[92m"
    YELLOW = "\x1b[93m"
    WHITE = "\x1b[97m"
    GREY = "\x1b[90m"
    RESET = "\x1b[0m"
    RULE = "─" * 44

    def __init__(self) -> None:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        if sys.platform == "win32":
            self._enable_ansi()

    @staticmethod
    def _enable_ansi() -> None:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)

    def _stamp(self) -> str:
        return f"{self.GREY}{time.strftime('%H:%M:%S')}{self.RESET}"

    def _line(self, glyph: str, target: str, detail: str, color: str) -> None:
        print(f"  {self._stamp()} {glyph} {self.WHITE}{target}{self.RESET} "
              f"{self.GREY}·{self.RESET} {color}{detail}{self.RESET}")

    def ok(self, target: str, detail: str) -> None:
        self._line(f"{self.GREEN}✓{self.RESET}", target, detail, self.GREEN)

    def sent(self, target: str, detail: str) -> None:
        self._line(f"{self.GREY}·{self.RESET} {self.GREEN}sent{self.RESET}", target, detail, self.GREEN)

    def warn(self, target: str, detail: str) -> None:
        self._line(f"{self.YELLOW}!{self.RESET}", target, detail, self.YELLOW)

    def err(self, target: str, detail: str) -> None:
        self._line(f"{self.RED}✗{self.RESET}", target, detail, self.RED)

    def info(self, detail: str) -> None:
        print(f"  {self._stamp()} {self.GREY}·{self.RESET} {self.WHITE}{detail}{self.RESET}")

    def rule(self) -> None:
        print(f"  {self.GREY}{self.RULE}{self.RESET}")

    def clear(self) -> None:
        print("\x1b[2J\x1b[3J\x1b[H", end="")

    def banner(self) -> None:
        self.clear()
        print()
        print(f"  {self.ORANGE}spoofer (Token Only){self.RESET} {self.GREY}·{self.RESET} {self.WHITE}discord badges{self.RESET}")
        print(f"    {self.GREY}by revere group{self.RESET}")
        print()


@dataclass
class State:
    token: str = ""
    fingerprint: str = ""
    analytics_token: str = ""
    fetched_at: int = 0
    used_games: list[str] = None
    total_games_claimed: int = 0
    total_hours_claimed: float = 0.0
    subscribed: bool = False
    joined_discord: bool = False

    def __post_init__(self) -> None:
        if self.used_games is None:
            self.used_games = []

    @classmethod
    def load(cls) -> "State":
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state = cls(**{k: data.get(k, v) for k, v in cls().__dict__.items() if k != "used_games"})
            state.used_games = data.get("used_games", [])
            return state
        return cls()

    def save(self) -> None:
        STATE_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @property
    def is_stale(self) -> bool:
        return not self.analytics_token or (time.time() - self.fetched_at) > AUTH_MAX_AGE

    @property
    def has_token(self) -> bool:
        return bool(self.token.strip())


def _local_props() -> dict:
    return {
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": CLIENT_VERSION,
        "os_version": OS_VERSION,
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-GB",
        "has_client_mods": False,
        "browser_user_agent": USER_AGENT,
        "browser_version": "42.7.1",
        "os_sdk_version": "26200",
        "client_build_number": CLIENT_BUILD_NUMBER,
        "native_build_number": NATIVE_BUILD_NUMBER,
        "client_event_source": None,
        "client_app_state": "focused",
    }


def build_super_props(launch_signature: str, heartbeat_session: str) -> str:
    try:
        req = urllib.request.Request(PROPERTIES_URL, method="POST", data=b"{}",
                                     headers={"content-type": "application/json", "user-agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as response:
            props = json.loads(response.read().decode("utf-8"))["properties"]
    except Exception:
        props = _local_props()
    props["client_launch_id"] = str(uuid.uuid4())
    props["launch_signature"] = launch_signature
    props["client_heartbeat_session_id"] = heartbeat_session
    raw = json.dumps(props, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _read_analytics_token(auth_token: str, super_props: str) -> str:
    req = urllib.request.Request(ME_URL, headers={
        "authorization": auth_token,
        "user-agent": USER_AGENT,
        "x-super-properties": super_props,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"token rejected ({exc.code})") from exc
    token = data.get("analytics_token")
    if not token:
        raise RuntimeError("no analytics_token in response")
    return token


def ensure_token(state: State, super_props: str) -> None:
    if not state.is_stale:
        return
    state.analytics_token = _read_analytics_token(state.token, super_props)
    state.fetched_at = int(time.time())
    state.save()


@dataclass(frozen=True)
class Session:
    heartbeat_session: str
    launch_signature: str
    super_props: str

    @classmethod
    def new(cls) -> "Session":
        hb = str(uuid.uuid4())
        sig = str(uuid.uuid4())
        return cls(hb, sig, build_super_props(sig, hb))


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    exe: str


def _win_exe(game: dict) -> str:
    for entry in game.get("executables", []):
        if entry.get("os") == "win32" and entry.get("name"):
            return entry["name"]
    return "game.exe"


def _download_games() -> str:
    request = urllib.request.Request(GAMES_CDN_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
    try:
        GAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        GAMES_FILE.write_text(raw, encoding="utf-8")
    except OSError:
        pass
    return raw


def _parse_games(raw: str) -> list[Game]:
    data = json.loads(raw)
    games: list[Game] = []
    seen: set[str] = set()
    for entry in data:
        gid = str(entry.get("id", ""))
        if not gid.isdigit() or gid in seen:
            continue
        if not any(e.get("os") == "win32" and e.get("name") for e in entry.get("executables", [])):
            continue
        seen.add(gid)
        games.append(Game(gid, entry.get("name", "Unknown"), _win_exe(entry)))
    return games


def load_games() -> list[Game]:
    raw = ""
    if GAMES_FILE.exists():
        raw = GAMES_FILE.read_text(encoding="utf-8").strip()
    if raw:
        try:
            games = _parse_games(raw)
            if games:
                return games
        except (json.JSONDecodeError, ValueError):
            pass
    try:
        return _parse_games(_download_games())
    except Exception:
        return []


class ScienceClient:
    def __init__(self, state: State, session: Session) -> None:
        self.state = state
        self.session = session
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def build_launch(self, game: Game) -> dict:
        now = int(time.time() * 1000)
        props = {
            "client_track_timestamp": now,
            "client_heartbeat_session_id": self.session.heartbeat_session,
            "event_sequence_number": self._next_seq(),
            "game": game.name,
            "game_id": game.id,
            "verified": True,
            "elevated": False,
            "is_launcher": False,
            "game_platform": "desktop",
            "detection_method": "verified_game",
            "is_overlay_enabled": False,
            "is_overlay_game_enabled": True,
            "is_overlay_game_source": "OOP_DEFAULT_DATABASE",
            "fullscreen_type": "UNKNOWN",
            "hardware_display_count": 1,
            "overlay_method": "Disabled",
            "activity_status_enabled": True,
            "activity_status_shared_guilds": [],
            "current_user_status": "online",
            "game_detection_enabled": True,
            "executable_path": game.exe,
            "voice_channel_id": None,
            "voice_channel_type": None,
            "voice_channel_bitrate": None,
            "voice_channel_guild_id": None,
            "hidden_by_distributor": False,
            "game_metadata": None,
            "executable_fingerprint": self.state.fingerprint,
            "client_performance_cpu": None,
            "client_performance_memory": None,
            "cpu_core_count": None,
            "accessibility_features": 0,
            "rendered_locale": "en-GB",
            "launch_signature": self.session.launch_signature,
            "client_rtc_state": None,
            "client_app_state": "focused",
            "client_send_timestamp": now,
        }
        if not self.state.fingerprint:
            del props["executable_fingerprint"]
        return {"type": "launch_game", "properties": props}

    def build_heartbeat(self, game: Game, duration_ms: int, session_id: str,
                        initial: bool, final: bool, ts: int | None = None) -> dict:
        ts = int(time.time() * 1000) if ts is None else ts
        return {
            "type": "running_game_heartbeat",
            "properties": {
                "client_track_timestamp": ts,
                "client_heartbeat_session_id": self.session.heartbeat_session,
                "event_sequence_number": self._next_seq(),
                "game_id": game.id,
                "game_name": game.name,
                "game_metadata": None,
                "game_executable": game.exe,
                "game_detection_enabled": True,
                "initial_heartbeat": initial,
                "final_heartbeat": final,
                "game_session_id": session_id,
                "duration_tracked_ms": duration_ms,
                "rtc_connection_id": None,
                "media_session_id": None,
                "launch_signature": self.session.launch_signature,
                "client_app_state": "focused",
                "client_send_timestamp": ts,
            },
        }

    def build_session(self, game: Game, duration_ms: int) -> list[dict]:
        sid = str(uuid.uuid4())
        now = int(time.time() * 1000)
        start = now - duration_ms
        if start < 0:
            start = now
        return [
            self.build_heartbeat(game, 0, sid, initial=True, final=False, ts=start),
            self.build_launch(game),
            self.build_heartbeat(game, duration_ms, sid, initial=False, final=True, ts=now),
        ]

    def post(self, events: Sequence[dict]) -> int:
        payload = {"token": self.state.analytics_token, "events": list(events)}
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "accept": "*/*",
            "accept-language": "en-GB",
            "authorization": self.state.token,
            "content-type": "application/json",
            "origin": "https://discord.com",
            "referer": "https://discord.com/channels/@me",
            "user-agent": USER_AGENT,
            "x-debug-options": "bugReporterEnabled",
            "x-discord-locale": "en-GB",
            "x-discord-timezone": "Europe/Oslo",
            "x-super-properties": self.session.super_props,
        }
        request = urllib.request.Request(SCIENCE_URL, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception:
            return 0


class Spoofer:
    def __init__(self, client: ScienceClient, console: Console) -> None:
        self.client = client
        self.console = console

    def run(self, games: Sequence[Game], build_events) -> int:
        total = len(games)
        sent_ok = 0
        for request_no, chunk in enumerate(range(0, len(games), BATCH_SIZE), start=1):
            batch_games = games[chunk:chunk + BATCH_SIZE]
            events = []
            for game in batch_games:
                events.extend(build_events(game))
            status = self.client.post(events)
            if status == 204:
                sent_ok += len(batch_games)
                self.console.sent(f"batch {request_no}", f"{sent_ok}/{total} games")
            elif status in (401, 403):
                self.console.err(f"batch {request_no}", f"[{status}] auth rejected · check your token")
                return sent_ok
            else:
                self.console.warn(f"batch {request_no}", f"[{status}]")
            time.sleep(BATCH_DELAY)
        return sent_ok


class App:
    def __init__(self) -> None:
        self.console = Console()
        self.state = State.load()
        self.session: Session | None = None
        self.client: ScienceClient | None = None
        self.games: list[Game] = []

    def _flush_stdin(self) -> None:
        try:
            if sys.platform == "win32":
                import msvcrt
                while msvcrt.kbhit():
                    msvcrt.getwch()
            else:
                import termios
                termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception:
            pass

    def _gate(self) -> None:
        if self.state.subscribed and self.state.joined_discord:
            return
        C = self.console
        steps = [
            ("subscribed", "youtube", SUBSCRIBE_URL, "subscribe to the youtube channel"),
            ("joined_discord", "discord", DISCORD_INVITE_URL, f"join {DISCORD_INVITE_LABEL}"),
        ]
        for attr, name, url, text in steps:
            if getattr(self.state, attr):
                continue
            C.banner()
            print()
            C.info(f"{C.ORANGE}required{C.WHITE} · {text}")
            try:
                webbrowser.open(url)
            except Exception:
                C.warn(name, f"open manually: {url}")
            for left in range(GATE_WAIT, 0, -1):
                print(f"\r  {C.GREY}you can continue in {left}s...{C.RESET}  ", end="", flush=True)
                time.sleep(1)
            print("\r" + " " * 50 + "\r", end="")
            self._flush_stdin()
            input(f"  {C.ORANGE}›{C.RESET} press enter once you're done ")
            setattr(self.state, attr, True)
            self.state.save()
            C.ok(name, "done")
            time.sleep(0.5)

    def start(self) -> None:
        self.console.banner()
        time.sleep(0.8)
        print()

        self._gate()

        C = self.console
        if not self.state.has_token:
            self._prompt_token()
        else:
            C.ok("auth", "token loaded")
            time.sleep(0.5)
        if not self.state.has_token:
            C.err("token", "required to run")
            return

        self.console.banner()
        print()
        C.info("loading games...")
        time.sleep(0.4)
        self.games = load_games()
        if not self.games:
            C.err("games", "couldn't load the game list")
            return
        C.ok("games", f"{C.ORANGE}{len(self.games)}{C.WHITE} loaded")
        time.sleep(0.5)

        print()
        C.info("validating auth...")
        self._new_session()
        try:
            ensure_token(self.state, self.session.super_props)
        except Exception as exc:
            C.err("token", str(exc))
            return
        C.ok("auth", "ready")
        time.sleep(0.5)

        print()
        self.menu()

    def _new_session(self) -> None:
        self.session = Session.new()
        self.client = ScienceClient(self.state, self.session)

    def _prompt_token(self) -> None:
        self.console.info("paste your discord account token")
        entered = input(f"  {self.console.GREY}token:{self.console.RESET} ").strip()
        if entered:
            self.state.token = entered
            self.state.save()
            self.console.ok("token", "saved")
            time.sleep(1.5)

    def _refresh(self) -> None:
        self.console.info("refreshing analytics token...")
        try:
            self.state.fetched_at = 0
            ensure_token(self.state, self.session.super_props)
        except Exception as exc:
            self.console.err("auth", str(exc))
            return
        self._new_session()
        self.state.save()
        self.console.ok("auth", "refreshed")
        time.sleep(1.5)

    def _require_ready(self) -> bool:
        if not self.state.has_token:
            self.console.err("token", "not set")
            return False
        if self.state.is_stale:
            try:
                ensure_token(self.state, self.session.super_props)
            except Exception as exc:
                self.console.err("auth", str(exc))
                return False
            self._new_session()
        return bool(self.state.analytics_token)

    def claim_games(self) -> None:
        if not self._require_ready():
            return
        C = self.console
        print()
        C.info(f"loaded {C.GREEN}{len(self.games)}{C.WHITE} games available")

        raw_count = input(f"  {C.GREY}how many games? [all]:{C.RESET} ").strip()
        try:
            count = int(raw_count) if raw_count else len(self.games)
        except ValueError:
            C.err("input", "invalid count")
            return
        count = min(count, len(self.games))

        raw_hours = input(f"  {C.GREY}hours per game? [1]:{C.RESET} ").strip()
        try:
            hours = float(raw_hours) if raw_hours else 1.0
        except ValueError:
            C.err("input", "invalid hours")
            return

        selected = self._select_games(count)
        if not selected:
            C.err("games", "none selected")
            return

        duration_ms = int(hours * 3600 * 1000)
        total_hours = len(selected) * hours
        print()
        C.info(
            f"claiming {C.ORANGE}{hours:g}h{C.WHITE} on "
            f"{C.ORANGE}{len(selected)}{C.WHITE} games "
            f"{C.GREY}·{C.WHITE} {total_hours:,.0f}h total"
        )
        C.rule()
        ok = Spoofer(self.client, self.console).run(
            selected,
            lambda g: self.client.build_session(g, duration_ms),
        )
        print()
        C.ok("complete", f"{ok}/{len(selected)} games · {ok * hours:,.0f}h claimed")
        self.state.total_games_claimed += ok
        self.state.total_hours_claimed += ok * hours
        self.state.save()

        C.rule()
        input(f"  {C.ORANGE}›{C.RESET} press enter to continue")
        C.rule()

    def _select_games(self, count: int) -> list[Game]:
        available_ids = {g.id for g in self.games}
        unused_ids = [g.id for g in self.games if g.id not in self.state.used_games]
        used_ids = [gid for gid in self.state.used_games if gid in available_ids]

        if len(unused_ids) >= count:
            selected_ids = unused_ids[:count]
        else:
            selected_ids = unused_ids
            if used_ids:
                remaining = count - len(selected_ids)
                rotated = used_ids[remaining:] + used_ids[:remaining]
                selected_ids.extend(rotated[:remaining])

        self.state.used_games = [gid for gid in self.state.used_games if gid not in selected_ids] + selected_ids
        id_map = {g.id: g for g in self.games}
        return [id_map[gid] for gid in selected_ids if gid in id_map]

    def menu(self) -> None:
        C = self.console
        while True:
            C.clear()
            C.banner()
            print()
            C.info(f"loaded {C.ORANGE}{len(self.games)}{C.WHITE} games")
            C.info(f"claimed {C.ORANGE}{self.state.total_games_claimed}{C.WHITE} games · {C.ORANGE}{self.state.total_hours_claimed:,.0f}h{C.WHITE} total")
            C.rule()
            C.info(f"{C.ORANGE}1{C.RESET} · claim games")
            C.info(f"{C.ORANGE}2{C.RESET} · refresh auth")
            C.info(f"{C.ORANGE}3{C.RESET} · exit")
            C.rule()
            choice = input(f"  {C.ORANGE}›{C.RESET} ").strip()
            print()
            if choice == "1":
                self.claim_games()
            elif choice == "2":
                self._refresh()
            elif choice in ("3", ""):
                break
            else:
                C.warn("input", "invalid option")


def main() -> None:
    try:
        App().start()
    except KeyboardInterrupt:
        print()
        Console().warn("exit", "interrupted")


if __name__ == "__main__":
    main()

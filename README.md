# CyberRace

A top-down arcade racer with **true/false cybersecurity questions**. Every time
you cross the start/finish line a question pops up (the race clock pauses while
it's on screen):

- **Right answer:** a 10-second speed boost. The car goes about 35% faster
  (260 -> ~350 px/s) and turns sharper to match, so it handles the same.
  It turns yellow and a countdown bar shows how much boost is left.
- **Wrong answer:** 10 seconds added to your race time.

There are 3 laps, so 3 questions per race (the last one, at the finish, can only
cost you time). The **fastest total time** (driving + penalties) wins, and your
name and time go on a local leaderboard.

Built as a runnable prototype now, structured to move onto a Raspberry Pi +
joystick with no code changes.

---

## 1. Stack, and why

| Piece | Choice | Why |
|---|---|---|
| Game engine | **Python 3 + pygame** | Runs identically on a laptop and a Raspberry Pi; `pygame.joystick` reads USB joysticks/gamepads with no extra driver config. |
| Physics/logic | Plain Python (`car.py`, `track.py`, `questions.py`) | No pygame dependency in the logic itself, so it's fast to unit test and easy to reason about. |
| Storage | **SQLite** (`leaderboard.db`, one file) | Zero setup, no server process to run on the Pi, durable across power cycles, trivial to back up or export to CSV. |

## 2. Project layout

```
cyberrace/
├── main.py               # game loop: menu -> race -> leaderboard, and all the screens
├── theme.py              # the look: colour modes, fonts, glow / panel / scanline effects
├── settings.py           # accessibility settings (colour mode, text size, effects), saved to settings.json
├── cvd.py                # colour-blindness simulation, used to check the colour modes
├── fonts/                # Orbitron + Share Tech Mono (free, SIL Open Font License)
├── car.py                # car physics (accel, steering, friction, 10s boost, grass, wall collisions)
├── track.py              # the circuit, grass verge and walls, nearest-road lookup, checkpoint lap counter
├── controls.py           # joystick input, with keyboard fallback
├── questions.py          # cybersecurity true/false question bank
├── leaderboard.py        # SQLite read/write for results
├── test_game_logic.py    # AI driver + real physics + lap counter (no pygame needed)
├── test_race_loop.py     # runs main.run_race() with a stand-in for pygame
├── test_accessibility.py # colour modes vs colour blindness, every setting draws, menu works + saves
└── requirements.txt
```

## 3. How to run it

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python3 main.py
```

No joystick plugged in? It still runs — steer with **arrow keys / WASD**,
throttle with **up/down / W/S**, **T** or **F** to answer a question when one
pops up, **ESC** to quit. Press **TAB** (or click the button in the top-right
of the start screen) for the accessibility settings.

Everything except the actual drawing can be tested on any machine, no display or
joystick needed:
```bash
python3 track.py             # circuit fits the screen, doesn't overlap, corners drivable, laps count
python3 car.py               # physics, grass slowdown, walls stop the car all round
python3 test_game_logic.py   # an AI driver completes 3 laps; boosted car is faster but still holds the road
python3 test_race_loop.py    # the real race loop: a question every lap, boost, penalty, clock pauses
python3 settings.py          # settings save/load, and survive a missing or corrupt file
python3 test_accessibility.py # colour modes checked against colour blindness, all 24 setting combos, the menu
python3 questions.py         # 30 questions: short enough, balanced True/False
python3 leaderboard.py
```

## 3a. The look

A neon "cyber" style: a dark circuit-board grid, cyan glowing road edges, a green
data-grid verge (the grass), magenta glowing walls, scanlines, and a glowing car
with a light trail (cyan normally, yellow while boosted). Questions appear as a
"SECURITY CHALLENGE" terminal; answers show **ACCESS GRANTED** or **ACCESS DENIED**.

- All colours are at the top of `theme.py` -- change them there to re-skin the game.
- The two fonts are bundled in `fonts/` so it looks the same on a Pi as on a
  laptop. Both are free to use and share (SIL Open Font License, files included).
  If they're missing, a system monospace font is used instead.
- The expensive effects (glow, scanlines, background) are drawn once at start-up,
  so a frame is mostly simple blits -- well under 1 ms per frame on a laptop,
  comfortably inside 60 fps on a Raspberry Pi 4.

## 3c. Accessibility settings

Open them from the start screen: press **TAB**, click the **ACCESSIBILITY**
button in the top-right corner, or press DOWN to select it and ENTER. In the
menu: UP/DOWN to choose, LEFT/RIGHT (or ENTER, or a mouse click) to change,
ESC to go back. Changes show straight away, with a live preview of the colours,
and are saved to `settings.json` so they stick between games and reboots.

| Setting | Options | What it does |
|---|---|---|
| **Colour mode** | Standard, Red-green friendly, Blue-yellow friendly, High contrast | Swaps the whole palette. Red-green friendly makes right/wrong blue/orange and the walls amber; blue-yellow friendly makes right/wrong cyan/red and the boosted car white; high contrast uses plain black with white road edges and orange walls. |
| **Text size** | Normal, Large (120%), Extra large (140%) | Makes all reading text bigger -- questions, the HUD, menus, the leaderboard. Boxes resize to fit, and the answer banner stays up a little longer. |
| **Reduce flashing & effects** | Off / On | Turns off blinking prompts, the screen flash when you hit a wall, scanlines, glow and colour fringing. Good for anyone sensitive to flashing or who finds the effects distracting. |

Right and wrong never rely on colour alone: answers always show a **tick** or
**cross** as well as the words ACCESS GRANTED / ACCESS DENIED.

**How the colour modes were checked:** `cvd.py` simulates the three main types
of colour blindness (Machado et al., 2009) and `test_accessibility.py` checks
that the colours that matter -- right vs wrong, road edge vs wall, car vs
boosted car, grass vs road -- stay clearly different (delta-E 20 or more) for
the people each mode is for. The standard neon palette scores only about 21 for
road edge vs wall with deuteranopia (the most common type), which is why the
red-green mode exists; in that mode the smallest difference is 45.

## 3b. The track, walls and lap counting

**The circuit** is a closed spline through the `CONTROL_POINTS` list in `track.py`:
a long start/finish straight along the bottom, a fast sweeper, a chicane, a climb,
a hairpin at the top right, a dip along the top, an S-bend, and a big left-hander back
onto the straight. About 4,000px per lap, 96px wide.
Run `python3 track.py` after editing the points -- it fails if the road overlaps
itself, leaves the screen, or has a corner so tight the inside edge pinches shut.

**Grass and walls** go all the way round. Each side of the tarmac has a strip of
grass `GRASS_WIDTH` px wide (20px by default). It's drivable but slow. Behind the
grass is a hard wall: the car can't get past it, slides along it, loses some speed,
and "WALL!" flashes. Where two parts of the circuit run side by side, the grass
strips meet and a single wall runs between them, so you can't cut across. There's
also a wall round the edge of the screen as a backstop. To change how much grass
there is, edit `GRASS_WIDTH` in `track.py`. Then run `python3 track.py`, which
checks there's still room for grass and a wall between close sections and at the
screen edges.

**Laps** are counted with 16 ordered checkpoint gates around the circuit. A lap only
counts when the car crosses every gate in order and then the start line, so reversing
over the line, shunting back and forth on it, or cutting across the infield can't add
laps. Driving the wrong way round gives no laps either.

---

## 4. Hardware and software needed

- **Any joystick/gamepad with buttons**, connected via USB (or Bluetooth if
  paired as a standard HID controller). Standard USB flight-stick-style
  joysticks with at least 2 buttons work well (one for True, one for False).
  No special driver is needed — pygame reads any
  device the OS recognises as a joystick.
- **Raspberry Pi** (3B+ or newer recommended; a 4 handles the display more
  comfortably) running **Raspberry Pi OS**, with a monitor/TV attached (HDMI).
- Python 3.9+ and the packages in `requirements.txt`.

## 5. How the Raspberry Pi is used

The Pi is the whole game console here:
- It runs `main.py` directly — the Pi's own CPU/GPU renders the track, car,
  and question overlay via pygame/SDL, so there's no separate server or PC involved.
- The joystick plugs into one of the Pi's USB ports; pygame enumerates it as
  `Joystick(0)` automatically on boot of the script.
- The SQLite leaderboard file lives on the Pi's SD card, so results persist
  between sessions even after a reboot.
- For a "kiosk" setup (e.g. at a school open day), you'd typically set
  `main.py` to auto-launch on boot (a systemd service or a line in
  `~/.config/lxsession/LXDE-pi/autostart`) so it's ready the moment the Pi
  powers on.

**Finding your joystick's exact button/axis numbers:** different controllers
number their buttons differently. Run this on the Pi with the joystick
plugged in:
```bash
python3 controls.py
```
It prints live axis and button values as you move the stick and press
buttons — use that to correct the `AXIS_STEER`, `AXIS_THROTTLE`,
`BUTTON_TRUE`, `BUTTON_FALSE` constants at the top of
`controls.py` if your device numbers them differently from the defaults.

---

## 6. The leaderboard

Shown after every race, ranked by **fastest final time** (3 laps of driving
plus 10s for each wrong answer). Each entry shows: rank, name, final time,
penalties, and questions answered correctly (e.g. `2/3`).

Results are stored in a `race_results` table. If you have a `leaderboard.db`
from an older version (which ranked by points), its old `results` table is
simply ignored.

## 7. Cybersecurity questions (true/false)

30 questions live in `questions.py`, written for players **aged 8-18**: short
statements in plain language (no jargon), on things young people actually come
across online -- passwords, scams and fake messages, strangers and oversharing,
downloads and viruses, and telling a trusted adult when something's wrong.
There are 15 True and 15 False, so just pressing the same button every time
doesn't pay off.

Each question has a one-line explanation, shown under the ACCESS GRANTED /
ACCESS DENIED message after answering, so players learn something even when
they get it wrong. `QuestionDeck` shuffles through the whole pool before
repeating any question.

To add more, append to the `QUESTIONS` list and run `python3 questions.py` --
it checks each question is short enough (72 characters max), the explanation
fits (80 max), and the True/False mix stays balanced.

## 8. Data: what's collected, how it's processed, stored, and shared

**Collected**, once per finished race:
- Player name (typed in at the start; capped at 16 characters, non-printable
  characters stripped)
- Final time (time to complete 3 laps, plus penalties)
- Penalty seconds (10s per wrong answer)
- Questions answered correctly / total answered (for an accuracy stat)
- A server-side timestamp (set by SQLite, not user-editable)

**Processed:** entirely on-device, in memory, while the race is running —
lap count, timer, and penalties are computed locally frame by frame. Nothing is
sent anywhere during play.

**Stored:** written to a single local SQLite file, `leaderboard.db`, only
*after* a race finishes (`leaderboard.add_result`). This is the only
persistent record of players kept. The accessibility settings are saved
separately in `settings.json` -- just the three choices, nothing personal.

**Shared:** **nothing, by default.** This is a local-only, single-device
leaderboard — appropriate for a classroom or event kiosk where you don't
want names leaving the device. If you do want results visible across
multiple machines or online, see the extension idea below — that's a
deliberate opt-in change, not something this prototype does silently.

**Privacy note for real deployment (e.g. with kids' names):** keep names
first-name-only or nickname-based by instruction/sign-posting at the kiosk,
and periodically clear the DB (`python3 -c "from leaderboard import clear_all; clear_all()"`)
if it's a public event rather than a long-running installation.

---

## 9. What I'd extend first

Roughly in order of "most bang for the least effort":

1. **Difficulty scaling / question categories.** Split the question bank into
   easy/medium/hard, and get harder as laps progress, or let the player pick a
   category (passwords, phishing, malware, network basics) at the name-entry screen.
2. **A countdown and a rolling-start timer**, so the clock starts at "GO" and the
   grid has a proper lights sequence.
3. **A second car (AI ghost or 2-player)** using a second joystick -- `controls.py`
   already works with `Joystick(0)`; accept an index to support `Joystick(1)`.
4. **Networked/shared leaderboard** -- swap `leaderboard.py`'s SQLite calls for a small
   Flask/FastAPI backend (or Supabase/Firebase) so several Pi kiosks at an event feed
   one live leaderboard on a big screen.
5. **Sound** -- engine hum, a "access granted / denied" chime, and a synth soundtrack.

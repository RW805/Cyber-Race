"""
Runs the real main.run_race() loop with pygame replaced by a stand-in (so it works
on any machine, with no display or joystick), an AI driver on the controls, a
fake clock, and scripted answers to the end-of-lap questions.

It checks the glue code in main.py: track drawing, lap counting hooked up to the
car, a question popping up every time a lap is completed, a correct answer giving
a boost, a wrong answer adding a 10s penalty, the clock pausing while a question
is on screen, finishing after 3 laps and returning a result.
It does NOT check how anything looks on screen -- run `python3 main.py` for that.

Run:  python3 test_race_loop.py
"""
import math
import sys
import types
from unittest.mock import MagicMock

pg = MagicMock(name="pygame")
pg.event.get.return_value = []
sys.modules["pygame"] = pg

import main  # noqa: E402  (must come after the stand-in is installed)
from track import TRACK  # noqa: E402
from car import BOOST_MULTIPLIER  # noqa: E402

FRAME = 1 / 60


class FakeClock:
    now = 0.0

    def tick(self, fps):
        FakeClock.now += FRAME
        return FRAME * 1000


main.time = types.SimpleNamespace(time=lambda: FakeClock.now)


class OneQuestionDeck:
    """Every question's correct answer is True."""
    def next_question(self):
        return {"text": "Test statement", "answer": True, "explain": "Because."}


main.QuestionDeck = OneQuestionDeck

holder = {}
RealCar = main.Car


def capturing_car(*args, **kwargs):
    holder["car"] = RealCar(*args, **kwargs)
    return holder["car"]


main.Car = capturing_car


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


THINK_FRAMES = 180   # the AI "reads" each question for 3 seconds before answering


class AIControls:
    """Drives the racing line and answers the end-of-lap questions: right on
    lap 1 (boost), wrong on lap 2 (penalty), right on lap 3."""

    def __init__(self, answers=(True, False, True)):
        self.answers = list(answers)
        self.questions_seen = 0
        self.waiting = 0
        self.max_speed = 0.0
        self.max_speed_after_lap1 = 0.0

    def get_drive_input(self):
        car = holder["car"]
        self.max_speed = max(self.max_speed, car.speed)
        if self.questions_seen == 1:
            self.max_speed_after_lap1 = max(self.max_speed_after_lap1, car.speed)
        tx, ty = TRACK.samples[(car.track_idx + 12) % TRACK.n]
        steer = max(-1.0, min(1.0, wrap(math.atan2(ty - car.y, tx - car.x) - car.heading) * 3.0))
        target = 150 * (BOOST_MULTIPLIER if car.boost_timer > 0 else 1.0)
        return (1.0 if car.speed < target else -0.2), steer

    def _answer(self, value):
        # Only called while a question is on screen. Wait a bit, then answer.
        self.waiting += 1
        if self.waiting < THINK_FRAMES:
            return False
        if self.answers[0] is value:
            self.waiting = 0
            self.answers.pop(0)
            self.questions_seen += 1
            return True
        return False

    def true_pressed(self):
        return self._answer(True)

    def false_pressed(self):
        self.waiting -= 1          # true_pressed already counted this frame
        return self._answer(False)


def test_full_race():
    font = MagicMock()
    font.size.side_effect = lambda txt: (12 * len(txt), 24)   # rough text width for word-wrapping
    font.render.return_value.get_rect.return_value.height = 24
    ai = AIControls()
    FakeClock.now = 0.0
    result = main.run_race(MagicMock(), FakeClock(), ai, font, font, font, "TESTER")
    assert result is not None, "race returned no result"
    assert ai.questions_seen == 3, f"expected a question at the end of each of the 3 laps, got {ai.questions_seen}"
    assert result["questions_total"] == 3 and result["questions_correct"] == 2, result
    assert result["penalty_secs"] == main.WRONG_ANSWER_PENALTY, result
    assert abs(result["time_secs"] - (result["race_secs"] + main.WRONG_ANSWER_PENALTY)) < 1e-6, result
    assert ai.max_speed_after_lap1 > 150 * 1.2, "correct answer on lap 1 should have boosted the car"
    # The AI spent 3 x 3s answering; that time must not be on the race clock.
    paused = 3 * THINK_FRAMES * FRAME
    assert FakeClock.now - result["race_secs"] >= paused - 0.5, "race clock kept running during questions"
    assert result["race_secs"] is not None and 30 < result["race_secs"] < 120, result
    print(f"  finished: driving={result['race_secs']:.1f}s + penalties={result['penalty_secs']:.0f}s "
          f"= {result['time_secs']:.1f}s, questions={result['questions_correct']}/{result['questions_total']}, "
          f"top speed while boosted={ai.max_speed_after_lap1:.0f}")


def test_track_surface_builds():
    surf = main.build_track_surface(TRACK)
    assert surf is not None
    print("  track surface drawn without errors")


if __name__ == "__main__":
    for fn in (test_track_surface_builds, test_full_race):
        print(fn.__name__)
        fn()
    print("\nOK: main.py race loop runs a 3-lap race with end-of-lap questions, boosts and penalties.")

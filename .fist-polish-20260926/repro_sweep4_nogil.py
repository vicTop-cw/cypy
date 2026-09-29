#!/usr/bin/env python3
"""Live repro for the two candidates the fourth-pass sweep surfaced in cypy_bridge/nogil.py.

Each check prints PASS(=defect reproduced) / NO(=no defect) with the measured numbers, and the
script exits non-zero if either expected repro fails to reproduce — so a ticket can only be
filed on evidence that is re-runnable.
"""
import sys
import threading
import warnings

warnings.simplefilter("ignore")
sys.stdout.reconfigure(encoding="utf-8")

from cypy_bridge.nogil import GilState, NoGilError, nogil_thread  # noqa: E402


def repro_gilstate_masks_user_exception():
    """`with GilState()` whose body re-acquires: __exit__ raises NoGilError over the user error."""
    raised = None
    try:
        with GilState() as state:
            state.acquire()          # body legitimately returns the GIL early
            raise ValueError("user error")
    except Exception as exc:         # noqa: BLE001 - the point is *which* type escapes
        raised = exc
    escaped = type(raised).__name__
    print(f"  escaped exception type = {escaped} (expected ValueError if the user error survived)")
    print(f"  isinstance NoGilError  = {isinstance(raised, NoGilError)}")
    return escaped == "NoGilError"


def repro_nogil_thread_leaks_executor():
    """Documented one-shot idiom `nogil_thread(fn)()` never shuts its executor down."""
    def compute():
        return 1

    before = threading.active_count()
    for _ in range(12):
        assert nogil_thread(compute)() == 1
    after = threading.active_count()
    live = after - before
    print(f"  threading.active_count() {before} -> {after} (delta {live}) after 12 one-shot calls")
    # A one-shot call that leaked its pool leaves a live non-daemon worker behind.
    leaked_threads = [t for t in threading.enumerate()
                      if t is not threading.main_thread() and t.name.startswith("ThreadPoolExecutor")]
    print(f"  live ThreadPoolExecutor workers = {len(leaked_threads)}")
    return live >= 10 and len(leaked_threads) >= 10


def main():
    a = repro_gilstate_masks_user_exception()
    print(f"[repro A] GilState.__exit__ 覆盖用户异常: {'REPRODUCED' if a else 'not reproduced'}")
    b = repro_nogil_thread_leaks_executor()
    print(f"[repro B] nogil_thread 一次性调用泄漏执行器线程: {'REPRODUCED' if b else 'not reproduced'}")
    print(f"summary: A={a} B={b}")
    if not (a and b):
        sys.exit(1)


if __name__ == "__main__":
    main()

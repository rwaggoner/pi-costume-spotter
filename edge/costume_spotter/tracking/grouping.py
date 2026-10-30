"""Group assembly: visitors who arrive together are greeted together (02-F7).

Sits between the tracker and the event bus. The tracker announces each person
the moment they are stable; this module decides when those announcements form a
*group* that gets one Claude call and one spoken greeting.

The rule is built so a lone visitor pays no extra latency:

- When someone is announced, a group opens.
- If nobody else is on their way to being announced (``pending`` is 0), the
  group closes immediately — a single visitor is greeted as fast as before.
- If other people are in view and about to be announced, the group stays open
  for them, but never longer than ``wait_seconds`` after it opened, and never
  beyond ``max_size`` people (a big crowd is split into several groups).

Synchronous, no I/O, clock passed in — tested like the tracker (02-N3).
"""

from dataclasses import dataclass, field

from costume_spotter.tracking.tracker import NewVisitor


@dataclass
class GroupAssembler:
    """Collects tracker announcements into groups."""

    wait_seconds: float = 1.0  # 02-F7: longest a group waits for stragglers
    max_size: int = 6          # 02-F7: one Claude call handles at most this many people

    _open: list[NewVisitor] = field(default_factory=list)
    _deadline: float = 0.0

    def update(self, announced: list[NewVisitor], pending: int,
               now: float) -> list[list[NewVisitor]]:
        """Feed one frame's announcements; return the groups that closed this frame.

        ``pending`` is how many people in view are about to be announced
        (``VisitorTracker.pending_count()``).
        """
        closed: list[list[NewVisitor]] = []
        for visitor in announced:
            if not self._open:
                self._deadline = now + self.wait_seconds
            self._open.append(visitor)
            if len(self._open) >= self.max_size:
                closed.append(self._close())

        if self._open and (pending == 0 or now >= self._deadline):
            closed.append(self._close())
        return closed

    def _close(self) -> list[NewVisitor]:
        group, self._open = self._open, []
        return group

    @property
    def is_open(self) -> bool:
        return bool(self._open)

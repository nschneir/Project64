# TODO

Open items carried out of recent reviews and dogfood runs. Items are deleted
as they land — what was actually done is recorded in `CHANGELOG.md` and in git
history, so this file stays a list of work still open.

Every item is written to stand on its own — anchor, what's wrong now, the fix
direction if one was ruled, and how to verify. The process ledgers that
produced these items (`.superpowers/sdd/*/progress.md`) are deleted when a plan
finishes, so this file is the only surviving record. Line numbers are a hint;
the function/test names are the durable anchors.

## VICE wedges at real time with no recorder armed

**Anchor:** `audio.pin_realtime`, `audio.pinned_record_start`,
`audio.pinned_record_stop`, `session.Session.launch(warp=False)`.

**Status:** unfixed. A retry mitigating the symptom **is** shipped
(`audio.warp_state`); the ordering fix below is not. The root cause is a
strong hypothesis, not a verified diagnosis — nobody has tested the fix.

**What's wrong now.** A headless session running at 100% speed with no sound
recorder armed stops answering its binary monitor. Reproduced during the SID
audio work: six reads, ~14 s each, all timed out. `Session.launch(warp=False)`
fails the same way ("monitor never answered").

**Mechanism (hypothesis).** VICE's sound device acts as flow control for the
emulation loop. At real time with no consumer draining it, the sound writer
blocks and starves the emulator thread, which wedges *both* monitors. This fits
every observation collected: warped sessions are fine, real-time-with-a-recorder
is fine, real-time-without-a-recorder dies.

**The evidence that points at ordering.** A measurement run over 1663
text-monitor opens found the confirmation readback stalling **39 times out of 39
on `warp on` and 0 times on `warp off`**. That asymmetry falls out of the call
order: `pinned_record_stop` disarms the recorder *first* and then calls
`restore_speed`, so the `warp on` write and its readback happen in exactly the
real-time-no-consumer window. `warp off`, by contrast, is issued during pinning
while the machine is still warped — before the transition — and never stalls.

Two more exposures of the same window:
- `pinned_record_start` pins first and arms second, leaving a
  real-time-no-recorder gap one or two monitor round trips wide. It survives
  only because it is sub-second.
- That function's arm-failure path calls `restore_speed` *while already in* the
  wedge condition, so a failed arm can strand the session at 1x.

**Fix direction (ruled, not implemented).** Re-warp *before* disarming the
recorder, or keep a sink armed across the restore. Keep the retry regardless —
it is cheap, measured, and defends against whatever residual remains.

**How to verify.** Reorder `pinned_record_stop` to restore warp before
disarming, then re-run the forced-arm experiment: drive ~100 pin/unpin cycles
with the first `warp on` reply discarded each cycle and count stalls. If the
`warp on` stall rate goes to zero, the hypothesis is confirmed. The pre-fix
baselines to compare against are 39/39 rescued stalls over 240 cycles, and
10 failures in 1663 opens (0.60%) in the un-retried population.

**There is now a reproducer in the test suite.** `test_capture_hears_a_live_arpeggio`
(`tests/test_audio.py`, marked `vice`) fails when the wedge fires, so the suite is
intermittently red through no fault of the code under test. This was confirmed
**not** to be a regression from any of the audio work: a clean worktree checked out
at `7983b57` fails identically. Whoever picks this up gets a live reproduction for
free — but note it is intermittent, so a single green run proves nothing. Run it
repeatedly and count, the way the original measurement did.

**One shipped change moves the odds.** The input-validation hardening added to the
capture primitives puts roughly 100 ms of extra work inside the exact
real-time-with-no-recorder window this defect lives in. It was measured as harmless
and it is not a reason to revert anything, but if the wedge rate is ever
re-measured, that 100 ms is a variable that changed between the original 0.60%
baseline and the current code. Compare like with like.

**Related, also open:** in `audio.capture`'s unpin handler, a disarm failure
*followed by* a restore failure keeps the pin sidecar and so takes the
survivable branch, because the sidecar is the only discriminator available.
Resolving it needs `pinned_record_stop` to report which half failed — a
contract change that was out of scope when found. The warning text was made
accurate for that case in the meantime (it states where the artifacts are
rather than claiming they are complete).

**Not investigated:** a second failure mode — four consecutive sessions in one
12-minute window dying with a binary-monitor timeout after a successful pin,
then vanishing — was never attributed. It may be this same defect, or may be
environmental; an internet outage on the host that day is a candidate. No
`ps`/CPU state was captured. Deliberately dropped rather than chased.

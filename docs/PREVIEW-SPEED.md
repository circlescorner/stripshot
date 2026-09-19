# Live preview target: 1–30 FPS

In Operator → Live preview speed, choose a target and Save between sessions.
The existing selected rate is preserved when the software is updated. Raising the
maximum does not set the booth to 30. A disabled preview remains disabled.

The saved target applies to both camera workers and is restored at startup and
reconnect. Operator reports **requested FPS and measured camera-frame FPS**. Camera
transfer speed, USB bandwidth and decoding can limit what each screen displays.
These figures are not a promise of 30 displayed frames per second.

Workers pace start-to-start intervals and always check camera commands before
requesting another preview. The browser fetches and decodes one frame at a time;
its timer subtracts fetch/decode time from the target interval. There is no 15-FPS
or 200-ms browser ceiling. Late results are fenced, timed-out requests aborted,
object URLs revoked, and errors back off. Capture operations keep priority.

Validation covers configuration and saved-setting limits, disabled defaults,
failed saves, authentication, both workers, restart/reconnect, a deterministic
30-FPS mock clock with command priority, stalled fetch/decode and URL cleanup.
No physical captures or sustained 30-FPS hardware test were used.

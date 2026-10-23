# Camera Paths

Record the camera by walking a route, then play it back. The same recording
serves a video and an exact before-and-after comparison between two rendering
configurations.

## Quick Start

All `/rtx camera` commands are typed in chat, are client-side, and do not need
cheats. They need the renderer to be running.

1. Arm a named recording:

   ```text
   /rtx camera record flythrough
   ```

2. Press `R` to start. Sending the command closes chat, and `R` is ignored
   while chat or a menu is open.
3. Fly the route, then press `R` again to stop and save.
4. Play it back:

   ```text
   /rtx camera play flythrough
   ```

The `record` command only arms the shortcut. Timing starts on the first `R`.

## Commands And Shortcuts

The [In-Game Guide](IN_GAME_GUIDE.md#camera-paths) lists the commands.
Seeking in a loaded path keeps its playing or paused state unless the seek
reaches the end, which finishes playback. Seeking by name loads a path and
stands at that point without playing. `/rtx camera stop` stops playback or
cancels an unsaved recording; cancellation never saves it.

`/rtx camera time` changes the world's time of day. It has nothing to do with
the `time` playback clock, which is the argument to `play`.

While a recording is running and no screen is open, `=` moves the time of day
forward and `-` moves it back. Hold `Ctrl` for larger steps. The shifted `+` on
the main keyboard works through the same `=` key; numpad `+` and `-` are left to
the Remix runtime.

Camera commands are unavailable while a benchmark is running. Stop the
benchmark first.

## For A Video

Playback moves the player, so fly the route in creative or spectator mode
rather than in survival.

Set the time of day before you record, with `/rtx camera time noon` or one of
its siblings. Time is stored per waypoint, so scrubbing it with `=` and `-`
while recording is part of the shot: playback interpolates between the times
you passed through, taking the shorter way around the day.

Use the default `time` clock, which replays at the pace you flew. Press `F1` to
hide the interface, including your own hand, and start your own screen
recorder: this mod records camera movement, not video. Playback holds the first
pose for a frame before it moves, so a recorder started a moment late still
catches the beginning.

## Choosing A Clock

`time` is the default and plays the route at the pace you recorded it. It reads
real time, and it smooths over a render hitch instead of jumping the camera
forward, so a stall costs a little wall-clock duration rather than a visible
lurch. Use it for anything anyone will watch.

`fixed-60` advances exactly one 60 Hz sample per rendered frame, so its speed
follows your frame rate: 120 FPS plays at about twice speed, 30 FPS at about
half. Use it to compare two rendering configurations, because every run sees
the same ordered camera poses no matter how fast the machine is. Benchmarks
replay the same files on the same fixed 60 Hz schedule.

Use `/rtx camera status` to compare render-frame time with camera advance and
see any outstanding smoothing lag. A gap in `time` mode is stall smoothing;
`fixed-60` keeps its fixed schedule.

## File Format

Camera files are strict version 1 JSON, and are meant to be readable and
hand-editable.

```json
{
  "version": 1,
  "interpolation": "catmull-rom",
  "waypoints": [
    {
      "timeMs": 0,
      "x": 0.0,
      "y": 80.0,
      "z": 0.0,
      "yaw": 0.0,
      "pitch": 0.0,
      "timeOfDay": 6000
    },
    {
      "timeMs": 2000,
      "x": 10.0,
      "y": 82.0,
      "z": 4.0,
      "yaw": 30.0,
      "pitch": -5.0,
      "timeOfDay": 6500
    }
  ]
}
```

The rules are:

- `version` must be the integer `1`, and `interpolation` must be
  `catmull-rom`. That string is the version 1 discriminator and does not change.
- A path needs at least two waypoints.
- Every waypoint needs `timeMs`, `x`, `y`, `z`, `yaw`, and `pitch`. `timeOfDay`
  is the only optional field, and is normalized into 0 through 23999.
- The first `timeMs` is `0`, and later ones are strictly increasing
  non-negative integers.
- Position, yaw, and pitch must be finite numbers.
- An unknown field, at the root or in a waypoint, is rejected rather than
  ignored, so a spelling mistake fails loudly.

Between waypoints the camera follows a shape-preserving curve fitted to the
timestamps, so it never overshoots a position you flew through. Yaw is unwrapped
the short way around, so a turn past 180 degrees does not become a full spin.
Before the first waypoint and after the last, the pose holds.

The clock is not stored in the file. A path recorded once plays on either.

A camera name is 1 to 128 letters, numbers, `.`, `_`, or `-`, and starts with a
letter or a number. A `.json` you type is removed. Path separators and Windows
device names are rejected.

## Where Recordings Live

Recordings are scoped to the world you made them in:

```text
<gameDir>/camera-paths/<world-key>/<name>.json
```

For a single-player world the key comes from the save folder name, and for a
server from a sanitized server identity. A path recorded in one world does not
appear in another.

A launcher may stage read-only paths in a `fixture/` subdirectory of the same
folder. A recording of your own in the parent directory wins over a staged one
of the same name, so refreshing the staged set never deletes your work.

## Still Shots

A camera path is a route. A still shot is one pose kept for a picture, and it
carries what a waypoint cannot: the weather, whether path tracing is on, and
which cloud style is showing. Mark one with `/rtx shot mark <name>` from the
pose you want, list the set with `/rtx shot`, and drop one with
`/rtx shot remove <name>`. Every mark is saved the moment it is made; there is
nothing to arm or stop.

Shots live beside the camera paths of the same world as `docs.shots.json`, a
version 1 file with its own strict schema; a camera path may not be named with
a `.shots` ending for that reason. Two shots whose names differ only in letter
case are one shot, since each becomes an image file. A tool that knows the set
can stand
at each pose, wait for the world to load and settle, and take the picture
again, which is how this repository's documentation screenshots are kept
current.

## Troubleshooting

- **Pressing `R` types in chat or does something else:** close the screen and
  run `/rtx camera record <name>` first. Plain `R` is only intercepted while a
  recording is armed or running.
- **A path is reported as missing:** check `/rtx camera status` and the world
  it was recorded in. Recordings do not cross worlds.
- **A JSON file is rejected:** confirm it is version 1, starts at
  `timeMs: 0`, has strictly increasing timestamps, and has no unknown fields. A
  file with a `frames` field is not a version 1 path and is rejected.
- **Playback does not advance while paused:** that is intended. A game pause is
  not playback time on either clock.
- **Playback briefly runs faster after a hitch on the `time` clock:** it repays
  the time the hitch cost at a capped rate, and `/rtx camera status` shows the
  outstanding lag. Long gaps are treated as renderer suspension instead, so
  the camera does not skip forward.
- **`fixed-60` playback is too fast or too slow:** expected unless the renderer
  is running at 60 FPS. It takes one sample per frame.

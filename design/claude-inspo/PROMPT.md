Design two things for Nebula, the Windows app that drives OBS. They share one material. Attach every PNG in the refs folder of this pack before you draw. Do not attach anything in the redundant folder. Those pictures win over this text if they disagree.

1. The toast. One capsule, bottom-right, never a stack. Status toasts are a single row, 384 by 60, as in 03-pause.png and 06-stop.png. Prompt toasts are 404 by 116, as in 08-prompt-with-controls.png and 08-prompt-august-gallery.png: the words stay on the upper row, and Record and Not now sit underneath, towards the left. Dust on a prompt sits toward the right. A violet line runs along the bottom and fades at both ends.
2. The dial menu. It opens when the user clicks the knob on a Redragon Terraflare K762 Pro. Rotating the knob moves the selection. Clicking again runs the highlighted row and closes the menu. The knob is not on this screen. The keyboard's little display is only a decorative GIF. This menu is a window on the PC, built from the same glass as the toast.

Desktop, dark. No phone frame. No keyboard. No fake numbers.

## Match the pictures

- True capsule. Ends are semicircles, including the taller prompt. No grey rectangle, no 8px rounded box, no window frame.
- Two-layer glass over a nebula. Deep ground #0A0812 and #100D1C, violet wash #8B7CF6, a hint of ember #FF5C7A only on start, stop, and error. Translucent core, about 3px inset, luminous hairline, no solid grey stroke.
- A round icon chip, about 28px, with a soft glow. Ember glow on start, stop, and error. Violet glow on pause, resume, and prompt.
- Seven specks. They move. They are not a twinkle. Do not attach the old twinkle GIF. That file is in the redundant folder because it is the wrong toast.
  - Recording started: specks burst outward from the left chip.
  - Recording stopped: they settle inward and down, still on the left.
  - Recording paused: a slow sideways float at the right end. That is the dust in 03-pause.png.
  - Recording resumed: they lift and brighten, on the left.
  - Something went wrong: uneven jitter, on the left.
  - The prompt: a calm orbit at the right end. That is the dust in 08.
- Type is Segoe UI Variable. Text #F5F3FF, secondary #9A93C4.
- The drain is a 2px tinted line. Both ends fade. It shrinks from the right. Hover would freeze it. Do not draw a countdown number.

Prompt controls are part of the toast, under the words, as in 08 and 09. Do not squeeze them onto the right of a short single-line pill. That short strip is a mismatch.

## Dial menu

Three frames, left to right, same size: just opened, highlight on the middle row, closing.

Rows, in this order, nothing else: Start Nebula · Pause recording · Save replay. No delete. No bitrate. No disk countdown. The menu stays until the second click, so it has no life-timer drain. A 2px violet rule may sit under the highlighted row only, fading at both ends.

Motion already chosen:

- Open: rise 8px over 260ms, then a soft overshoot and settle. Rows may stagger about 40ms after it lands. Easing cubic-bezier(.32, .72, 0, 1).
- Highlight: a pill slides to the row over 260ms, and the label brightens while a 2px mark slides with it.
- Dust on the menu: mostly a slow lateral float (about 3.6s), a few specks that lift and brighten (about 2.6s), a little uneven jitter (about 1.8s).
- Reduced motion pauses the dust. It does not delete it.
- Hover 500ms. Press scales to 0.98 in 120ms.

Rejected, do not draw these:

- A 28px rise over 420ms.
- Dust that bursts, sinks, or orbits on the menu. Those motions belong to the toast, not the menu.
- A highlight that only crossfades.
- Scaling the whole menu up from the corner as the default open.
- The opacity-only twinkle.

Close was not chosen. Draw the third frame as the capsule leaving in that same 260ms family. Then, on a second artboard, give four close alternatives as a preference gallery so they can be voted: fade 320ms; rise 12px and fade 320ms; scale to 0.98 and fade toward the corner; rows leave first and the card follows. Label them C1 C2 C3 C4. One pick. Each card gets Like, Nope, and Undecided.

Nothing else is up for a vote. The toast pictures and the menu motion above are locked.

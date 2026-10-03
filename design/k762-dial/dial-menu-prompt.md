Design one popup menu for Nebula, the Windows app that drives OBS. It opens when the user clicks the knob on a Redragon Terraflare K762 Pro. Rotating the knob moves the selection. Clicking again runs the highlighted row and closes the menu. The knob is not on this screen. The keyboard display only shows a decorative GIF. This menu is a window on the PC.

Show three states on one artboard, left to right, same menu, same size: just opened, highlight on the middle row, closing. Desktop, dark. No phone frame. No keyboard.

Material — copy the recovered Nebula toast, not a flat card. The loved captures are the August 2026 gallery in tools/_toast_demo/ (especially 08_prompt.png and 01_start.png). Do not use tools/_toast_demo_alien/. Those are the dead ones.

- Shape is a true capsule. Ends are semicircles. Radius is half the height. No grey rectangle, no 8px rounded box, no visible window frame.
- Glass is two layers over a nebula. Deep ground (#0A0812 / #100D1C) with a soft violet wash (#8B7CF6 at low opacity) and a hint of ember (#FF5C7A) bleeding through a translucent core. Inset about 3px. No solid grey stroke. A luminous hairline only.
- Seven tiny bright specks drift across the whole capsule, not only inside the icon. Mostly a slow lateral float (about 3.6s). A few specks lift and brighten (about 2.6s). A little uneven jitter (about 1.8s). They reseed when the menu opens.
- One icon chip, about 28px, with a soft violet glow. One line per row, label only. Type is Segoe UI Variable. Text #F5F3FF, secondary #9A93C4.
- A 2px violet rule may sit under the highlighted row only. Both ends of that rule fade out. It does not drain. This menu stays until the second click.

Rows, in this order, nothing else: Start Nebula · Pause recording · Save replay. No delete. No bitrate. No disk countdown. No fake numbers.

Motion that is locked:

- Open: the capsule rises 8px over 260ms, then a soft overshoot and settle. After it lands, the rows may stagger in about 40ms apart. Easing cubic-bezier(.32, .72, 0, 1).
- Highlight: a pill slides to the selected row over 260ms, and that label brightens while a 2px mark slides with it. Both at once.
- Reduced motion pauses the dust. It does not delete it.

Do not design these. They were rejected:

- Opening with a 28px rise over 420ms.
- Dust that bursts, sinks, or orbits.
- A highlight that only crossfades and does not travel.
- Scaling the whole menu up from the corner as the default open. That can be a quiet alternate, not the one you draw.

Close was not voted. Draw the third frame as the capsule simply leaving, same 260ms family, without inventing a new trick.

Hover and press, if you show them: hover 500ms, press scales to 0.98 in 120ms. Ember #FF5C7A is only for a real error, and this menu has no error state.

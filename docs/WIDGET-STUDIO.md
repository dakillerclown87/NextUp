# Native JSON widget studio

Requires NextUp 2.0.0-beta.41 or newer.

1. Install the update over your existing NextUp installation; do not uninstall or delete your user data. Your accounts and settings stay in the separate user data directory.
2. Open Stream widgets, then Import widget JSON.
3. Choose Halo-Orbit-Glow.json or Automata-Gradient.json.
4. Choose Save as new widget. The original presets remain intact.
5. Copy this widget URL into an OBS/Streamlabs browser source. Use the dimensions shown in Name & heading.

The menu belongs to the desktop app, not the widget. Only the widget is visible to viewers. JSON exports carry the design, images, fonts, gradient colors and animation settings. They are not HTML pages and do not execute custom scripts.

Progress gradient supports two to eight hex colors. Border lighting supports two colored lights moving at constant speed around a shape's rounded outline; select a shape, pick colors and set a lap duration. It follows changes to position, size, radius and rotation. From beta.42, it follows the shape's pulse, float, spin and custom layer motion.

Expand Layout, layers & advanced settings for geometry, background GIFs/images, custom fonts, artwork, transitions and motion. Preview song transition runs a demonstration without changing the live queue. Save changes overwrites your selected saved design; Save as new widget creates a separate copy.

These JSON effects need the updated renderer. Older NextUp versions do not preserve the new fields. Existing v1/v2/v3 presets continue working with the new version.

## Layer selection and motion (beta.42)

Use the always-visible Layers list to select a covered layer. Send to back / Bring to front changes drawing order. New shapes start behind existing content. The list runs front to back.

Selecting a layer motion automatically previews it on the canvas with simulated playback. Play layer motion / Stop layer motion controls the preview without changing music or OBS playback. Stop motion before precise positioning. Pulse grows and fades a visible layer, including its border lights. Give plain transparent shapes a fill or a visible border. Reduced-motion system preferences disable animation and show an explanatory message.

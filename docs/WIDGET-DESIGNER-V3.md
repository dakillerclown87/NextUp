# NextUp advanced widget designer

NextUp beta.30 adds `nextup-widget-v3`. Existing v1/v2 widgets continue to work.

## Automata record changer

Import `Automata-Animated.json` in Stream Widgets → Add widget, then choose **Save as new widget**. Open its saved preview or copy its browser-source URL to OBS / Streamlabs. Set the browser source to **1080 × 520**. Keep NextUp running.

The widget uses the song and queue NextUp reports, including Spotify and YouTube tracks controlled through NextUp's browser extension. It does not inspect arbitrary browser tabs. Artwork depends on the provider's available metadata. It has no playback controls.

The album disc spins while music is playing. On a track change a two-link arm grips the disc, lifts it outside the canvas, brings the new record down, releases it and retracts. Fast changes are coalesced before the exchange; subsequent changes run after the current exchange. Reduced-motion preference uses a short fade instead. Audio analysis remains optional and separate from disc motion.

## Editing

Select an element in the preview or Element menu. Drag to move, drag handles to resize, and use Shift to preserve proportions. Layer order controls change which items overlap. Layer opacity, fill, gradient, border, corner radius, rotation, font, color and text alignment are editable. Hex fields accept `#RRGGBB`, `#RRGGBBAA` or `transparent`.

Add or duplicate as many layers as your system can comfortably render. Art, labels, song title, artist, requester, time, progress, equalizer, queue, text, shapes and image layers are supported. Image layers accept PNG/JPG/WebP uploads (converted to PNG), or animated GIF. Exports include image and font assets.

For older widgets choose **Enable advanced design**. Save as new preserves the original. Special legacy horizon/prism decoration is not automatically converted; keep its original preset for that appearance.

Text templates support `{song}`, `{artist}`, `{requester}`, `{platform}` and `{duration}`. You can place multiple copies of an element. Queue layers can be horizontal or vertical, and progress can be straight or wavy.

Choose spin, float, pulse or custom keyframe motion. Custom frames specify offset (0–1), x/y translation, rotation, scale and opacity. The **Preview animation & song swap** window tests the actual renderer without changing your music. The editing canvas stays still to make dragging precise. Saved preview tabs show live playback.

Imported robotic designs store their artwork layer, base joint, off-canvas lift point, resting hand position, duration and colors in the JSON `robot` object. Dedicated robot controls are not shown in the launcher; its transition is labeled **Imported widget animation**. Keep the lift point high enough that the entire record is outside the canvas at exchange. For a disc use equal width/height and a large corner radius. You can remove the arm mount or switch to fade, slide, fold or no transition.

## Practical bounds

Saved-widget and custom-font count caps are removed. V3 allows arbitrary named layers rather than one fixed element per type. This is a declarative renderer, not a general JavaScript engine: JSON cannot execute scripts, arbitrary HTML or load untrusted code.

Safety bounds remain: canvas up to 7680 × 4320, 120 custom frames per layer, up to 100 queue entries displayed per layer, 40 MB imported JSON, 2 MB per normalized PNG/font and 20 MB per GIF. GIF frame/dimension and font decompression checks remain. These protect a live broadcast from invalid files or excessive memory usage. Many large layers, images or fonts can still increase CPU/GPU use.

## Selling a widget

You can distribute a design as a paid JSON download. This standalone build has no licensing, billing, premium entitlements or copy protection. An imported JSON file can be edited and shared by its recipient. A future account-based entitlement service would be a separate feature; naming a file “premium” does not enforce payment.

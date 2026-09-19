# Saved photos, sheet review and slideshow

Saved photos & sheets shows at most three completed sessions per page, with a
finished-sheets filter, session dates and navigation to older sessions. Held and
unfinished sessions stay out of the gallery. Cards use 480px JPEG thumbnails;
review and slideshow use at most 1920px display derivatives. Original files are
untouched and remain accessible through Full resolution.

The review dialog supports Previous/Next, arrow keys, Escape and focus restoration.
It keeps the current image visible while loading the next, reports errors, and
preloads only its two neighbors. Finished-sheet previews and numbered scan
references use the same viewer. Paper-free previews show the frozen composition,
not driver-only quality processing.

The slideshow retains source selection, shuffle, history, arrows, pause/play,
full screen, Space and F shortcuts. It polls for completed arrivals and keeps a
bounded 100-entry visit history. The server returns only the selected image and
two neighbors, independent of library size. Stable seeded shuffle ordering does
not reshuffle existing photos when new sessions arrive. New photos join the order
at the next catalog refresh (up to roughly 20 seconds including server cache).

Image loading has one active fetch/decode, a three-image cache, cancellation,
stale-result fencing and URL cleanup. The last good image stays visible during
loading/errors. Derivative responses use private browser caching with validators;
status remains uncached. Scaled JPEG decoding reduces cold-thumbnail work, and
thumbnail generation cannot hold the selected display image behind its queue.
The browser DOM, decoded image cache and per-poll response size stay bounded as
the library grows. The server maintains a metadata index of completed batches.

All browsing is read-only with respect to sessions, originals and print intents;
only regenerable derivatives are added. Focus styles, responsive sizing and
reduced-motion behavior are preserved. Space on focused Operator controls now
activates the control instead of taking a photo.

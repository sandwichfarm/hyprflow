# Cover Flow reference provenance

Retrieved October 6, 2026. These files support visual comparison and criticism of the reconstructed animation. They retain their original rights and are never loaded by the plugin.

## Original application screenshots

### `itunes-7-windowed-flickr.jpg`

- Title: *iTunes 7 Cover Flow*.
- Author: Jeremey Barrett (`jeremey` on Flickr).
- Source page: https://www.flickr.com/photos/jeremey/242170677/
- Direct image: https://live.staticflickr.com/89/242170677_6167b6cb76_b.jpg
- Source dates: taken September 12, 2006; uploaded September 13, 2006.
- Local image: 1024 × 683 JPEG; unchanged downloaded bytes.
- SHA-256: `45437f905878cf43bb637edbe94d75621439d4f81bd9022af50192b7d6cabbb9`.
- Use: selected-card dimensions, side-card perspective, overlap, reflection contact, stage color.

### `itunes-7.1-fullscreen.jpg`

- Source article: https://www.applegazette.com/itunes/first-impressions-of-itunes-71-w-screenshots/
- Direct image: https://www.applegazette.com/wp-content/uploads/2007/03/fullscreencoverflow.jpg
- Image metadata date: March 5, 2007, 18:15:18. The current article shows September 6, 2023; contemporary comments and image metadata establish the older capture context.
- Local image: 420 × 263 JPEG; unchanged downloaded bytes.
- SHA-256: `a88c4d5b99eb8298d29b1bd4dceee59edbc3c64a101866de6247eaab36e805f4`.
- Use: full-screen composition, black stage, reflection, selected-card scale.

### `itunes-7.1-windowed.jpg`

- Source article: same Apple Gazette article above.
- Direct image: https://www.applegazette.com/wp-content/uploads/2007/03/itunes71.jpg
- Image metadata date: March 5, 2007, 18:15:03.
- Local image: 420 × 279 JPEG; unchanged downloaded bytes.
- SHA-256: `ed2210baddd1ad2221f766c01a1402eb5eeac6cfb4c4c680fdbd977acb33bbda`.
- Use: independent confirmation of centering, perspective direction, side-stack density, and subdued labels.

## Motion sample

### `itunes-motion-samples.jpg`

- Video: [iTunes Cover Flow](https://www.youtube.com/watch?v=1nCeJWxp4yk).
- Author: bluemint.
- Published: April 9, 2007.
- Author’s description: “iTunes Cover Flow iShowU Capture”.
- Source stream: 320 × 240, 30 fps, duration approximately 161.6 s. Its encoded frame rate does not prove that the original screen recorder captured 30 unique frames each second.
- Local image: twelve frames beginning at approximately 2.5 s, sampled at 10 fps, arranged left-to-right then top-to-bottom in a 4 × 3 grid. Contact sheet is 1280 × 720. No interface elements were painted or reconstructed.
- SHA-256: `040b5cebb73815a54ad31e37b27d9df46857cb512160114447789461416ddde2`.
- Use: successive cards rotate continuously into the central position while the adjacent stack shifts. Several samples repeat, so this source cannot establish precise easing, frame pacing, or input latency.
- Extraction: `ffmpeg -ss 2.5 -i SOURCE.mp4 -vf 'fps=10,tile=4x3' -frames:v 1 itunes-motion-samples.jpg`.

The full source recording was inspected locally but is not included. The contact sheet is a bounded excerpt for animation comparison.

## Primary historical source

Apple’s September 12, 2006 announcement confirms that iTunes 7 introduced the Cover Flow view:
https://www.apple.com/ca/newsroom/2006/09/12Apple-Announces-iTunes-7-with-Amazing-New-Features/

## Measurement limits

Screenshots establish projected geometry, not a unique 3D camera. Different camera and depth combinations can produce similar projections. The design specification therefore labels its numerical camera model as a reconstruction and provides visual landmark tolerances. Timing is a tunable reconstruction; no Apple implementation constant is claimed.

Game Club is Obour's game room inside Telegram: Ludo first, then Esm-Famil and Hokm. Players play free or for points, and spend points on Obour services. The look follows social game apps like Plato: a light lavender-grey ground, white rounded cards with soft shadows, colorful game tiles, real Telegram photos for every player, and a dark game table for Ludo.

## Voice and copy

- Write Persian, informal second person singular ("تو"), short sentences. "نوبت شماست" is the only plural, kept for the turn bar.
- Say exactly what happens next: "روی تاس بزن تا بریزد", "مهره‌ای را که بالا و پایین می‌پرد بزن".
- Buttons are verbs: "شروع منچ", "شارژ", "پرداخت با امتیاز", "بیرون برو".
- Errors name the fix: "امتیاز کافی نیست؛ اول کیف را شارژ کن".
- Losses and rules are stated plainly before they happen: "خروج یعنی باخت و ۱۰۰ امتیاز ورودی برنمی‌گردد".
- Digits are always Persian (۰–۹) with `٬` for thousands. The product name stays Latin: "Game Club".
- No emoji in the interface. Mark every sample number with the `tag-sample` tag ("نمونه").

## Color

- Every screen sits on `ground`. Text on the ground is `ink`. The Ludo game screen is the exception: it sits on `game-bg` (dark), with `game-glass` cards and `game-ink` for secondary text.
- Content lives on `surface` cards; inner rows and tracks use `surface-sunk`; dividers use `line`.
- `ink` for text, `ink-muted` for meta lines. Both pass 4.5:1 on `surface` and `surface-sunk`.
- `sky` is the main action and the active bottom-nav circle; `violet` is the Ludo brand (feature card, Ludo tile); `coin` is points and prizes; text on `coin` is `coin-ink`, never white.
- Game tiles use `tile-violet` (Ludo), `tile-orange` (Esm-Famil) and `tile-coral` (Hokm) with white art on top.
- Buttons are pills (`radius-pill`) with a soft colored shadow; cards use `radius-xl` and `depth-md`.
- Players are shown by their Telegram photo (`GC.face`): `photo_url` from initData, else `/gc/pic/<key>` fetched by the bot, else the first letter of their Telegram name on a fixed color. Bots keep the cartoon avatar.
- `success` and `danger` always come with a word or icon (charge vs. leave), never color alone.
- The four player colors (`player-blue`, `player-red`, `player-green`, `player-yellow`) are only for game pieces, seats and the board. Yellow is always the local player.
- `obour-night` and `obour-aqua` appear only in panels that point to Obour services.

## Type

- One family: Rokh, five weights (400, 500, 700, 800, 900). Fallback `Vazirmatn, Tahoma`.
- Use the styles by name: `t-display` for the wordmark, `t-title` for page titles, `t-heading` for section heads, `t-subhead` for card titles, `t-body` for text, `t-button` for buttons, `t-label` for form labels and chips, `t-caption` for meta, `t-amount` for point totals.
- Don't use tabular numerals: Rokh spaces Persian digits apart with them.

## Space, radius, depth

- 4px base: `space-4` is the page gutter and card padding, `space-6` between sections, `space-2` between rows.
- Radii are generous: `radius-xl` for cards and sheets, `radius-lg` for buttons and seats, `radius-md` for rows and chips, `radius-pill` for pills.
- Objects stand on the ground with a solid bottom edge, never a blur: `depth-sm` for chips and rows, `depth-md` for cards, `press` inside buttons and dice. Only overlays (sheets, toasts, the nav) use `lift`.

## Motion

- Presses sink 2–3px in 80ms. Sheets slide up in 240ms; dialogs pop in 220ms.
- Pawns hop one cell at a time (165ms per step) so the player can count the move.
- Things that need the player bob gently: the die when it is their turn (`.ask`), movable pawns (`.can`), the active yard pulses.
- Respect `prefers-reduced-motion`: all of the above collapse to instant.

## Sound

All sounds are synthesized with Web Audio (no files) and start only after the player's first tap. The sound toggle sits in the game header and is remembered.

- `tap` on every button, `dice` rattle on each roll, `six` sparkle on a six, `step` rising pops per cell, `enter` arpeggio when a pawn leaves the yard, `capture` thud, `home` chime when a pawn reaches the center, `turn` two-note ding when it becomes your turn, `tick` when 5 seconds remain, `nomove` low buzz, `win` fanfare, `lose` falling phrase, `coin` on charge and purchases.

## Iconography

Line icons, 24px grid, 2.2px stroke, round caps, `currentColor`, drawn for this system (home, trophy, wallet, bag, help, back, sound, users, link, bot, globe, bolt, clock, spark, shield, check, copy, send, bell, dice). The coin is the one filled, colored icon. Game pieces (pawn, die, avatar, board) are illustrations, never icons. There is no logo yet: the wordmark is "Game Club" set in Rokh 900 in `sky-deep`.

## Layout

- One column, max 480px, centered; phone first.
- Main pages (home, leaderboard, wallet, Obour services) share the bottom nav: a white bar with rounded top corners, icons only (labels for screen readers), the current page inside a `sky` circle. Flow pages (Ludo lobby, game, help) have a back button and no nav.
- Every flow step or confirmation is a bottom sheet; results and exits are centered dialogs.

## Full-screen header (Telegram Mini App)

- Every page opens full screen on phones (`requestFullscreen`, Bot API 8.0). The header (`.appbar`) starts at the very top edge of the phone and has the page `ground` color (transparent on the game screen).
- It stacks three layers: the phone status bar (`--sa-t` from `safeAreaInset.top`), Telegram's floating-button band (`--csa-t` from `contentSafeAreaInset.top`), then the page row. In Telegram's band only a small centered title sits (`.appbar-cap`, 13px/900); never put a control there, because Telegram's close/back and menu buttons float over its corners.
- The page row holds the page title (`t-title` size, `ink`) and at most two controls on the end side: the balance pill and one icon button. In the game the row becomes the turn bar.
- Back is Telegram's native BackButton inside Telegram; the in-page back button (`.back`) shows only in a normal browser.
- Bottom-fixed parts (nav, dice dock) add `--sa-b` so they clear the home indicator. Side gutters grow to `--sa-l`/`--sa-r` in landscape.
- Telegram header and background colors are `#F5F6FB` (`ground`), and `#3A3350` (`game-bg`) on the Ludo screen, so non-full-screen clients show no seam.

## The Ludo screen

- Top to bottom: full-screen header with the turn bar, sound and rules → mode or prize tag → two seats → board (sized to the remaining height) → two seats → one-line event feed → dice dock.
- Every player sees their own color at the bottom-left: the board rotates by 90° steps and pawns, labels and the trophy counter-rotate to stay upright; seats follow their corner. Their die is the big one in the dock.
- Guidance is always visible: the turn bar says whose turn it is, the dock says the next action, the feed says what just happened, movable pawns bob and a dashed ring marks where each will land.
- 20 seconds per turn; when time runs out the roll and the best move happen automatically.
- The board geometry and rules live in one place (`GC.LUDO`); the live game computes dice and legal moves on the server.

## Accessibility

- Text meets 4.5:1 on its ground (3:1 for 24px+ titles with the outline). Focus shows a 3px `surface` ring with a `sky-deep` halo.
- Every icon-only button has a Persian `aria-label`; the turn bar and feed are live regions.
- Rokh is a licensed font: use the files only under a web license that covers this app.

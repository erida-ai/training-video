# training-video — плъгин „Обучително видео“ за Claude Code

Обучително видео с глас по зададени материали (PDF, документи, Google Drive, линкове) или по кода на продукт. Агентът пита каквото трябва, пише сценарий, иска одобрения (сценарий → цена → проба на гласа → визия), генерира и проверява гласа, прави слайдовете или записа и субтитрите.

## Инсталиране

Лично:

```
claude plugin marketplace add erida-ai/training-video
claude plugin install training-video@erida-training-video
```

За целия екип (собственик на организацията, claude.ai → Organization settings → Claude Code → Managed settings):

```json
{
  "extraKnownMarketplaces": {
    "erida-training-video": { "source": { "source": "github", "repo": "erida-ai/training-video" }, "autoUpdate": true }
  },
  "enabledPlugins": { "training-video@erida-training-video": true }
}
```

За рендера: `package.json` + `package-lock.json` (Playwright 1.63.0) — Claude Code ги инсталира сам при инсталиране на плъгина; Chromium: `npx playwright install chromium` (скилът го предлага). При работа от клонирано repo: `npm ci`.

**Gemini ключ — за всеки проект.** Проект е папката, в която работи Claude Code (repo на продукт или папка с документи). При първото ползване на скила в проект wizard-ът (`key.py setup <проект>`) отваря aistudio.google.com/apikey и прозорец, в който човекът поставя ключа; ключът се проверява в Gemini и остава само на този компютър — Keychain (macOS) или Credential Manager (Windows), под id-то на проекта. В проекта остава само `.training-video/project.json` (id и име, без тайни — може да е в git, за да има проектът един id за екипа). Всеки член на екипа въвежда ключа на проекта веднъж на своя компютър. `GEMINI_API_KEY` в средата важи за всички проекти — само за CI/Linux.

Нужни са ffmpeg и Node.js; скилът ги проверява (`doctor.py <проект>`) и дава командата за инсталиране за тази система.

### Windows 10/11

- Claude Code работи и с PowerShell, и с Git Bash; скилът няма нужда от Git Bash.
- Инсталиране (`doctor.py` дава същите команди): `winget install -e --id Python.Python.3.12`, `winget install -e --id Gyan.FFmpeg`, `winget install -e --id OpenJS.NodeJS.LTS`, по желание poppler за PDF. След инсталиране — рестарт на Claude Code (новият PATH).
- Python се пуска с `python` или `py -3` (на Windows `python3` обикновено е само препратка към Microsoft Store); `doctor.py` казва коя команда работи.
- Ключът на проекта е в Credential Manager (Windows Credentials → `training-video-gemini/<id>`).
- Проверка на нова машина: `python -B skills/training-video/tests/smoke.py` (без Gemini и без разходи).

## Структура

```
.claude-plugin/          plugin.json, marketplace.json (repo-то е и marketplace, и плъгин)
skills/training-video/
  SKILL.md               ходът на агента
  reference/             глас и качество, сценарий, режим „по материали“, режим „по код“
  languages/<код>.json   глас, стил и правила на проверката за всеки език
  scripts/               tvlib (достъп, проекти, цени), keystore (Keychain / Credential Manager), key (wizard за ключа), tts, check, narrate, voices, cost, lines, srt, sheets, doctor, extract
  tests/                 smoke.py — целият път без Gemini (слайдове, запис, монтаж, субтитри) за проверка на машина
  deck/                  слайдове → видео: render.cjs, deck.js (анимации), base.css (компоненти), catalog/ (пример за всеки компонент)
  screencast/            запис на уеб приложение като роля: survey.cjs (оглед), record.cjs, product.cjs (адаптер, роли), helpers.cjs, overlay.js, cards.cjs, assemble.py, adapter-template.cjs
themes/
  neutral/               тема по подразбиране
  _пример/               шаблон + какви материали трябват за нова тема
```

## Поддръжка

- **Нова тема:** копирайте `themes/_пример/` като `themes/<име>/` и следвайте README-то вътре. Проверка: `node skills/training-video/deck/render.cjs --catalog <име>` → кадри на всеки компонент в `~/.training-video/catalog/<име>/build/stills/`.
- **Нов език:** копирайте `languages/en.json`, преведете полетата (`fillers`, `not_differences`, `say_hints`, `greeting`).
- **Цени:** `PRICES` и `PRICES_DATE` в `scripts/tvlib.py` (от 01.01.2027 Google удвоява цените на тези модели).
- **Модели:** `TTS_MODEL` и `CHECK_MODEL` в `scripts/tvlib.py`. Моделът за проверка трябва да различава близки гласове — тествайте със запис на два различни гласа (вж. `reference/voice.md`).
- **Профил на продукт** за режим „по код“ живее в repo-то на продукта: `.training-video/profile.md` + `adapter.cjs` (вход, роли, данни) + скриптове за демо стека и примери. Шаблон: `skills/training-video/screencast/adapter-template.cjs`.
- Проверка на плъгина: `claude plugin validate .`

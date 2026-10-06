English · [日本語](README.ja.md)

# TTS Toolkit

<img src="docs/readme/00_tool_icon.png" width="200">

**A tool that lets you use three locally-run text-to-speech models through the same GUI and the same commands.** (Windows)

The dependencies of Qwen3-TTS / Chatterbox / Irodori-TTS are mutually exclusive, so they cannot live in a single virtual environment.  
This tool gives each model its own virtual environment, and lets you **switch between them with the same calls from the GUI / CLI**.

| Model                                                                   | Strengths                                                       |
| ----------------------------------------------------------------------- | --------------------------------------------------------------- |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) 1.7B                   | High quality in both Japanese and English. Clones a voice from a 3-second reference |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) Multilingual V3 | Lightweight at 0.5B, supports 23 languages                      |
| [Irodori-TTS](https://github.com/Aratako/Irodori-TTS) v4.1 Small        | Japanese only, 48 kHz. Voices can be crafted from a text description |

| What you can do                                                                                   | Output                   |
| ------------------------------------------------------------------------------------------------- | ------------------------ |
| **Generate speech from text** — one line at a time, or in bulk from a script                      | `.wav`                   |
| **Clone a voice from reference audio** — imitate a few seconds of audio (zero-shot cloning)       | `.wav`                   |
| **Design a voice from a description** — create the voice itself from "a calm, low female voice"   | `.wav`                   |
| **Batch-synthesize a character script** — writes a wav per line plus a record of durations and order | `.wav` + `manifest.json` |

<img src="docs/readme/01_gui_synthesis.png" width="720">

> Note: the detailed documents under `docs/` are written in Japanese.

---

## 1. Requirements

| Item   | Details                                                                                           |
| ------ | ------------------------------------------------------------------------------------------------- |
| OS     | Windows 11 (the setup and launch scripts are for Windows)                                         |
| Tools  | **mise / uv / git**                                                                               |
| Python | **Pinned to 3.12** (installed by mise. → [docs/setup/00_common.md](docs/setup/00_common.md))      |
| GPU    | NVIDIA GPU (driver reporting CUDA 12.8 or later). 8 GB or more of VRAM recommended                |
| Disk   | 30 GB or more free (four virtual environments plus model weights; downloads exceed 10 GB)        |

It also runs without a GPU, but not fast enough for mass production.

---

## 2. Setup

Create the virtual environments (common layer + three engines) and install the dependencies.

```powershell
git clone <this repository>
cd pyside-tts-toolkit
powershell scripts\win\SetupEngines.ps1
```

The first run involves a lot of downloading and takes tens of minutes.  
To limit which engines are set up, add `-Targets` (`common` / `qwen` / `chatterbox` / `irodori`).

```powershell
pwsh scripts\win\SetupEngines.ps1 -Targets common,irodori
```

When it finishes, verify with the command below. You are ready when all three engines show `CUDA ok`.

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli doctor
```

If mise / uv are not installed, or for per-engine instructions and troubleshooting, see
**[docs/setup/](docs/setup/README.md)**.

---

## 3. Usage

### Launch

```powershell
scripts\win\LaunchApp.bat
```

The window has two panes: input tabs on top and the log below. Drag the divider to resize.

You can also bundle just the GUI into an exe for distribution (see "6. Build" below).

| Tab          | What it does                                                     |
| ------------ | ---------------------------------------------------------------- |
| Synthesis    | Synthesize a single piece of text                                |
| Voice Design | Create a voice from a description and save it to `input/voices/` |
| Script       | Synthesize in bulk from a cast definition and a script           |

### Preparing reference audio

To clone a voice, put the reference audio in `input\voices\`; file dialogs open there first.  
If you don't have any, you can create one from a description in the **Voice Design tab** below.

Recommended reference length: about 3 seconds or more for Qwen / Chatterbox, and 30 seconds or more for Irodori (up to 120 seconds).

### Synthesis tab — synthesize a single piece of text

**Writes one wav that reads the text aloud.**

Enter `Text`, choose an `Engine`, and press `Run`.

#### Input / Output

| Item        | Default   | Description                                                                   |
| ----------- | --------- | ----------------------------------------------------------------------------- |
| Text        | empty     | The text to read aloud                                                        |
| Output Dir  | `output/` | Where to write. Press `...` to choose                                         |
| Output File | empty     | Output file name. If empty, a name derived from the text is used              |

#### Engine

| Item     | Default | Description                                                                  |
| -------- | ------- | ---------------------------------------------------------------------------- |
| Engine   | `qwen`  | The engine to use: `qwen` / `chatterbox` / `irodori`                         |
| Language | `Auto`  | Language: `Japanese (ja)` / `English (en)`. With Auto, the engine decides    |

Supported features differ per engine.

|            | Japanese | English | Voice cloning | Voice Design | Speed | Seed |   Rate |
| ---------- | :------: | :-----: | :-----------: | :----------: | :---: | :--: | -----: |
| qwen       |    ○     |    ○    |       ○       |      ○       |   ×   |  ○   | 24 kHz |
| chatterbox |    ○     |    ○    |       ○       |      ×       |   ×   |  ○   | 24 kHz |
| irodori    |    ○     |  **×**  |       ○       |      ○       |   ○   |  ○   | 48 kHz |

**Unsupported settings are not silently ignored; they raise an error.** The check happens before the engine starts, so you don't have to wait.

#### Voice

| Item         | Default        | Description                                                                                  |
| ------------ | -------------- | -------------------------------------------------------------------------------------------- |
| Voice Source | `Preset voice` | How the voice is chosen. As shown in the table below, irrelevant input fields are hidden     |
| Seed         | `random`       | Left as `random`, it changes every time. Fixing it makes the voice more stable               |
| Speed        | `1.00`         | Speaking speed (0.5–2.0). **Irodori only**. Leave at `1.00` for other engines                |

| Voice Source                 | Fields shown                         | Description                                                                                                              |
| ---------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `Preset voice`               | none                                 | The engine's default voice. Qwen uses a preset speaker for each language                                                 |
| `Clone from reference audio` | `Reference Audio` / `Reference Text` | Imitates the reference voice. `Reference Text` (a transcript of the audio) is used by **Qwen only**, and improves quality |
| `Design from a description`  | `Voice Design`                       | Specify the voice in words (qwen / irodori). Example: "A calm, low female voice. Polite and gentle way of speaking."     |

A wav such as `output\irodori-xxxxxxxxxxxx.wav` is written.

### Voice Design tab — create a voice from a description

**Creates a voice from a written description, without any reference audio.** You can make character voices without relying on a real person.

<img src="docs/readme/02_gui_voice_design.png" width="600">

| Item         | Default         | Description                                                                           |
| ------------ | --------------- | ------------------------------------------------------------------------------------- |
| Engine       | `qwen`          | Only engines that support Voice Design (qwen / irodori) are listed                    |
| Language     | `Auto`          | Language                                                                              |
| Voice Design | empty           | Description of the voice and manner of speaking. Example: "A bright, brisk voice of a woman in her 20s. Slightly fast." |
| Sample Text  | empty           | The sentence to read as a trial                                                       |
| Seed         | `random`        | Fixing it makes the same voice easier to reproduce                                    |
| Output Dir   | `input/voices/` | Where to write. The created voice can stay right in the reference audio folder        |
| Output File  | `master.wav`    | Output file name                                                                      |

A designed voice varies slightly every time. **The stable workflow is to keep one take you like and clone it from then on.**

1. Write the voice and manner of speaking in `Voice Design`, and a trial sentence in `Sample Text`
2. `Run` → `input/voices/master.wav` is created
3. If you don't like it, change `Seed` and repeat
4. Once decided, choose `Clone from reference audio` in the Synthesis tab and specify `master.wav`

For tips on crafting voices, see [docs/guide/original-voice.md](docs/guide/original-voice.md).

### Script tab — batch-synthesize from a character script

**Synthesizes lines in bulk from per-character voice definitions and a script.**  
A voice definition is written once and reused, so all you write each time is the lines.

<img src="docs/readme/03_gui_script.png" width="600">

#### Input / Output

| Item        | Default   | Description                                                                                       |
| ----------- | --------- | ------------------------------------------------------------------------------------------------- |
| Cast File   | not set   | Per-character voice definitions (`cast.toml`). Choose from `input/script/` with `...`             |
| Script File | not set   | Text listing "speaker: line". Choose from `input/script/` with `...`                              |
| Output Dir  | `output/` | Where to write. A wav per line and `manifest.json` are placed here                                |

#### Options

| Item       | Default | Description                                                                                                 |
| ---------- | ------- | ----------------------------------------------------------------------------------------------------------- |
| Gap        | `0.30`  | Pause between lines (seconds) used to compute `start_sec` in `manifest.json`. **No silence is added to the wav** |
| On Failure | OFF     | When ON, continues with the remaining lines even if one fails                                               |

Write the cast definition (`input/script/cast.toml`) and the script (`input/script/ep01.ja.txt`) like this:

```toml
[voices."霊夢"]
engine = "irodori"
voice_design = "落ち着いた少女の声。淡々としていて、少し呆れたような話し方。"
language = "ja"
seed = 42
```

```
霊夢: 今日はいい天気ね。
魔理沙: そうだな、絶好の弾幕日和だぜ！
霊夢[speed=0.9]: ……また変なこと言ってる。
[001-001-plasmo] ナレーター: Hello everyone!
```

This writes a wav per line such as `output\ep01\001-霊夢.wav`, plus `manifest.json`, which records each line's duration and offset from the start.  
Putting an output name such as `[001-001-plasmo]` at the start of a line writes that line as `001-001-plasmo.wav`. Lines without one are numbered sequentially as usual.  
Different speakers may use different engines (each model is loaded only once per engine).

For details on the format, see [docs/guide/script.md](docs/guide/script.md).

### While running

- Synthesis runs in a separate thread, so the window does not freeze (`Run` is disabled and `Cancel` is enabled)
- `Cancel` stops **before the next line starts**. A single-item synthesis runs to the end
- On first use, a dialog asks to confirm downloading the model weights (a few minutes, several GB; answering once suppresses it for the session)
- If "Engine Not Set Up" appears, that engine's virtual environment does not exist yet. Run `scripts\win\SetupEngines.ps1`
- Progress and errors go to the log below. The line labels (`[info]` / `[warn]` / `[error]`) are the same as in the CLI; clear with `File > Clear Log`
- On success, the output folder opens in Explorer
- Window position/size and input values are saved on exit and restored on the next launch
- `File > Clear Saved Settings...` clears the saved values and resets the window to defaults
- `Help > Open Document` opens the project's GitHub page

For details on each item, see **[docs/gui/usage.md](docs/gui/usage.md)**.

---

## 4. Folder structure

```
.
├─ python/
│   └─ ttstoolkit/       Package containing the GUI, CLI and processing
│       ├─ main.py           ← GUI entry point. Launched with -m ttstoolkit.main
│       ├─ tool_config.py    Title, size, resource paths
│       ├─ definitions.py    Choices shown in the UI (languages, voice sources)
│       ├─ gui/              Model / View / Controller and UI parts
│       ├─ cli/              Command-line entry (single entry + each command)
│       ├─ core/             Processing shared by CLI / GUI (parent-process side)
│       └─ engine/           Runners that run in separate virtual environments
│           ├─ _shared/          Contract (protocol) both sides obey, and runner base
│           └─ qwen/ chatterbox/ irodori/
├─ engine_env/         Definitions for building each engine's virtual environment
├─ .venvs/             The virtual environments themselves (common and engine-*)
├─ resources/          Icons and stylesheet (all colors and sizes live here)
├─ docs/               Detailed documentation
├─ input/              Input
│   ├─ voices/           Reference audio goes here (contents are git-ignored)
│   ├─ script/           Cast definitions and scripts go here
│   └─ batch/            JSON files for batch runs go here
├─ output/             Generated wav files (contents are git-ignored)
├─ scripts/
│   └─ win/SetupEngines.ps1 / LaunchApp.bat / Run{Synth,Batch,Script,Engines,Doctor}.bat
├─ tests/              Tests for the common layer (no models required)
├─ mise.toml           Python version to use (3.12) and uv settings
└─ pyproject.toml      Dependencies and Ruff settings
```

All Python code lives in `python/ttstoolkit/`.  
The common layer (`core`) neither prints to the screen nor terminates the process (progress goes through `logging`, failures through exceptions), so the CLI and GUI can call the same API as-is.  
The common layer never imports the models directly; it launches the runner in each engine's virtual environment as a subprocess and exchanges JSON over stdin/stdout. Batches and scripts keep the model loaded, so the load time is paid only once.

Default input/output paths are resolved **relative to the repository root, not the current directory**, so results are always written to the same place (`output/`) wherever you run from.

For why it is structured this way, see [docs/development/architecture.md](docs/development/architecture.md).

---

## 5. Using the CLI

The same processing as the GUI can be run from the command line.  
Run from the repository root, using the common layer's Python (`.venvs\common`).

```powershell
.\.venvs\common\Scripts\python.exe -m ttstoolkit.cli synth -e irodori -t "こんにちは。"
```

That is long to type every time, so defining a function helps. The rest of this section writes `tts`.

```powershell
function tts { & "$PWD\.venvs\common\Scripts\python.exe" -m ttstoolkit.cli @args }
```

If you'd rather not define a function, there is a `.bat` per subcommand in `scripts\win\`
that you can call directly (if the venv is missing, they print the setup instructions and stop).

```powershell
scripts\win\RunDoctor.bat
scripts\win\RunEngines.bat
scripts\win\RunSynth.bat -e qwen -t "こんにちは。" -l ja -O hello.wav
scripts\win\RunBatch.bat -e qwen sample.ja.json -o output\batch
scripts\win\RunScript.bat ep01.ja.txt -c cast.toml -o output\ep01
```

```powershell
# (1) Check the environment / list engines
tts doctor
tts engines

# (2) Synthesize one item
tts synth -e qwen -t "こんにちは。" -l ja -O hello.wav

# (3) Clone a voice from reference audio (Qwen gives higher quality with --reference-text)
tts synth -e qwen -t "おはようございます。" -l ja -r master.wav

# (4) Create a voice from a description → keep one you like and clone it from then on
tts synth -e irodori -l ja --seed 42 `
    -t "こんにちは。この声でナレーションを読み上げます。" `
    --voice-design "20 代女性のはきはきした明るい声。少し早口。" `
    -o input\voices -O master.wav
tts synth -e irodori -l ja -r master.wav -t "今日も一日がんばりましょう。"

# (5) Synthesize a JSON file in bulk (not available in the GUI)
tts batch -e qwen sample.ja.json -o output\batch

# (6) From a character script
tts script ep01.ja.txt -c cast.toml -o output\ep01
```

For reference audio, batch input and scripts, just give the file name and it is looked up in `input/voices/` / `input/batch/` / `input/script/`.

Things the GUI does not expose (`batch`, `-f` (read text from a file), `-v` (also show the engine's own output), etc.) are available in the CLI.  
Use `-h` to see all options.

- [docs/cli/common_options.md](docs/cli/common_options.md) — common options, path resolution, exit codes
- [docs/cli/synth.md](docs/cli/synth.md) — (2)(3)(4) single synthesis
- [docs/cli/batch.md](docs/cli/batch.md) — (5) bulk synthesis from JSON
- [docs/cli/script.md](docs/cli/script.md) — (6) character scripts
- [docs/cli/engines.md](docs/cli/engines.md) / [docs/cli/doctor.md](docs/cli/doctor.md) — (1) engine list / environment check

---

## 6. Build (distributable exe)

You can bundle just the GUI into a single exe with PyInstaller (**the CLI is not included**).
The engines (`.venvs/engine-*`) have mutually exclusive dependencies and rely on process isolation,
so only the common layer (GUI) is bundled; the heavy model dependencies are not.

```powershell
REM 1. Create the build environment (first time only)
build_env\scripts\win\Setup.bat

REM 2. Build
build_env\scripts\win\BuildApp.bat
```

`TTSToolkit.exe` and its supporting files are written to `build_env\scripts\win\dist\TTSToolkit\`.
To distribute, prepare `input/` / `output/` / `.venvs/` / `engine_env/` inside that folder
(next to `TTSToolkit.exe`), either by following `docs/setup/` or by copying from an existing environment.

```
TTSToolkit/
├─ TTSToolkit.exe
├─ _internal/          ← generated by the build
├─ input/
├─ output/
├─ .venvs/
│   ├─ engine-qwen/
│   ├─ engine-chatterbox/
│   └─ engine-irodori/
└─ engine_env/
```

For details (what `--add-data` bundles, how paths are resolved, etc.), see
[docs/development/build.md](docs/development/build.md).

---

## 7. Documentation

Detailed specifications, options and implementation notes are in [docs/](docs/README.md).

|                                                                      |                                              |
| -------------------------------------------------------------------- | -------------------------------------------- |
| [docs/setup/](docs/setup/README.md)                                  | Installation steps (**read this first**)     |
| [docs/gui/usage.md](docs/gui/usage.md)                               | All GUI options                              |
| [docs/cli/](docs/cli/common_options.md)                              | Usage for each CLI command                   |
| [docs/guide/script.md](docs/guide/script.md)                         | How to write character scripts               |
| [docs/guide/original-voice.md](docs/guide/original-voice.md)         | Designing and fixing an original voice       |
| [docs/development/architecture.md](docs/development/architecture.md) | Overall structure and design rationale       |
| [docs/development/build.md](docs/development/build.md)               | Bundling the GUI into an exe with PyInstaller |
| [docs/instructions/code_guide.md](docs/instructions/code_guide.md)   | Coding rules                                 |

---

## 8. License

Local generation is free and unlimited with all three models, and commercial use is allowed.

| Model       | Code       | Weights                                                |
| ----------- | ---------- | ------------------------------------------------------ |
| Qwen3-TTS   | Apache-2.0 | Apache-2.0                                             |
| Chatterbox  | MIT        | MIT (generated audio carries a PerTh watermark)        |
| Irodori-TTS | MIT        | MIT                                                    |

However, **rights to reference audio (voice material) are separate.** Cloning a real person's voice requires their consent and confirmation of the permitted scope of use.

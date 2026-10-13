# FAQ

### Is it really free? Is there an account?

Yes and no — no account, no subscription, MIT licence. Your only costs are the
electricity of the machine running the server and (optionally) an NVIDIA GPU.

### Do I need a GPU?

No. CPU-only runs roughly 5–10× slower: a six-second sentence takes a few seconds.
Switch to `whisper_model: small.en` and `cleanup_model: qwen2.5:3b-instruct`, or
turn cleanup off, and a modern CPU feels usable.

### How is this different from Wispr Flow / Superwhisper / OS dictation?

- **Nothing leaves your network.** Cloud dictation apps send your voice to their
  servers; Windows Voice Access and macOS Dictation run locally but have no AI
  formatting pass and no custom vocabulary.
- **No word limits, no subscription.** The server is yours.
- **It works offline** once installed.

The trade-off: you have to run a small server, and the setup is one step longer
than installing a cloud app.

### Does it work in other languages?

Yes — the default `small` model is multilingual with automatic detection
(90+ languages). Spanish and English are covered by tests and benchmarks. For
English-only dictation `small.en` is faster and more accurate.

### Why did it type something I didn't say?

Two different causes, and the log tells them apart: open the log from the tray
(*Open settings folder → `vozlab.log`*).

- `raw=…` is wrong → Whisper mis-heard. Speak closer to the mic, check the input
  device, or move to a bigger model (`medium`).
- `raw=…` is right but the final text isn't → the AI pass rewrote it. The server's
  guard rejects anything that invents words; if you see it happening, please open
  an issue with that log line.

### Can friends use it with my server?

They can, but the intended model is *everyone runs their own server* — nothing
points at your machine by default. Pointing several people at one server works
(the API is stateless) but the single token is shared, and your GPU does all the
work. For a group, run one server per household.

### Does the client work on macOS or Linux?

Not officially yet. It's plain Python, so `python run_vozlab.py` runs on
Linux/macOS for development, but text insertion uses Windows-specific behaviour
(`Ctrl+V`, registry autostart). Linux/macOS support is on the roadmap.

### How do I uninstall it?

- **Client**: `Settings → Apps → VozLab → Uninstall` (installer builds), or delete
  `%LOCALAPPDATA%\Programs\VozLab` and `%APPDATA%\VozLab` (source installs), plus
  the Start-menu shortcut.
- **Server**: `docker compose down` in `server/`, then delete the folder. Add
  `--volumes` if you used the all-in-one stack and want the model cache gone too.

### Can I use a cloud API instead of local models?

You could — the server is a thin wrapper — but that defeats the purpose: your
audio and text would leave your machine. VozLab will stay local-only by design.

### Is there a phone app?

No. Dictation needs a real keyboard to paste into; phones have their own
keyboard dictation. The server could be driven by any client that can POST audio,
though.

### Why is the installer unsigned? Windows blocked it!

Code signing costs money (a certificate plus identity validation), so VozLab ships
a **Smart-App-Control-safe** installer instead: `deploy.ps1` runs the app with
your signed Python rather than an unsigned `.exe`. Use the one-liner from the
README; it works even with SAC enabled.

### Where does the name come from?

*voz* (voice) + *lab* — the little lab at home that does the listening.

### Something else?

[Open an issue](https://github.com/diegosanchezguijarro-creator/vozlab/issues) or
check [Troubleshooting](TROUBLESHOOTING.md) first — most questions are answered
there.

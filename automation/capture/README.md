# Making the site's product captures

> **Not on every change.** These are refreshed once, near the end, when the
> product is close to complete — tracked in **#144**, which also lists what is
> known to have drifted since the last capture. Re-recording after every
> behaviour change during development is wasted effort; this kit exists so the
> refresh is cheap when it is finally worth doing.

The screenshots and the recording in `Website/media/` are taken from the
shipped build running in the Hyper-V lab VM (`VM_TESTING.md`), so they can be
remade whenever the app's screens change — F27 says the site shows the real
product, which is only true if the captures keep up with it.

Everything here runs **inside the guest**, through the bench's `F15UI`
interactive task. None of it runs on a desk: it moves windows around, starts
sprints and, in the recording's case, closes a real application.

## Order

| Step | Script | Why |
| --- | --- | --- |
| 1 | `set_resolution.py` | The baseline VM is 1024x768, which clips the app window. Raises it to 1920x1080 and persists it. A `lab.ps1 revert` puts it back, so this runs after every revert. |
| 2 | `clean_desktop.py` | Plain dark wallpaper, desktop icons hidden. The stock Windows photo is noise behind the app. |
| 3 | `seed_sample_data.py` | Writes a fortnight of sample sprints and a three-app blocklist. |
| 4 | `capture_screens.py` | Today, Blocked Apps, Schedule, and the end of a sprint. |
| 5 | `record_shield_closing.py` | Records the shield closing a blocked app, as JPEG frames. |

Encode the frames on the host once they are fetched:

```bash
ffmpeg -framerate 10 -i f%04d.jpg -an -c:v libvpx-vp9 -crf 36 -b:v 0 -pix_fmt yuv420p out.webm
ffmpeg -framerate 10 -i f%04d.jpg -an -c:v libx264 -crf 26 -preset slow -movflags +faststart -pix_fmt yuv420p out.mp4
```

## What the sample data is, and is not

`seed_sample_data.py` invents the history — three well-known apps and thirteen
sprints with a student's journal lines — and writes it through the settings
file's own unprotected envelope (`Protected: false`), which `SettingsService.Load`
already supports. **Nothing in the resulting screenshots is drawn by anything
but the shipped app.** Momentum and the streak are computed with the app's own
rules rather than typed in, so the numbers on screen agree with each other and
with the trend chart.

It is never a real blocklist and never a real licence: the app is in its free
trial in every capture.

## The recording needs a real blocked app

`record_shield_closing.py` expects something on the blocklist that is actually
installed, so the close is real. Steam was used for the current clip — installed
in the VM, left sitting on its own sign-in window, **never signed into**.

Install it in the guest with:

```powershell
Invoke-WebRequest -Uri 'https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe' -OutFile "$env:TEMP\SteamSetup.exe" -UseBasicParsing
Start-Process "$env:TEMP\SteamSetup.exe" -ArgumentList '/S' -Wait
```

Let it finish its first-run update before recording — it takes a few minutes and
shows a small progress window until the sign-in window appears.

**Revert the VM afterwards.** An installed Steam changes what the app picker
suggests, which would quietly skew later bench runs. Never checkpoint the VM
while it is in this state.

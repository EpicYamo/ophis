# Ophis for Windows

The Windows build is a normal user-mode HID application. It installs no
driver, no service and no kernel component, and it does not need administrator
rights.

## Run the portable build

1. Download `Ophis-windows.zip` from the
   [releases page](https://github.com/EpicYamo/ophis/releases).
2. Extract it anywhere (for example `C:\Users\<you>\Ophis`).
3. Quit Razer Synapse. If you do not need it for firmware updates, remove it
   from startup as well.
4. Run `Ophis.exe`.

The first launch may show a SmartScreen warning because the executable is not
code-signed. Choose **More info → Run anyway**.

`Ophis.exe` opens the window and adds a tray icon. Closing the window hides it;
right-click the icon to open it again, restore defaults or quit.

## Check the interface

Run `Ophis-cli.exe --probe` in PowerShell:

```powershell
.\Ophis-cli.exe --probe
```

It prints:

- whether the controller could be opened,
- the HID usage page and feature-report size of the control interface,
- every Razer HID interface with its usage page, feature-report size and
  whether it is the 91-byte control interface,
- the current brightness, fan target, power mode and charge limit,
- any Razer/Synapse processes that are still running.

Windows opens the mouse collection that carries the control report for system
use, so no user program can take an exclusive lock on it. If Synapse is running,
close it and run the probe again.

## Why Synapse and Ophis should not write at the same time

The controller has one vendor HID collection, nested under a mouse top-level
collection. Windows rejects share mode 0 and `GENERIC_READ` on that collection,
so Ophis opens it with a **shared, write-only handle** and talks to it with HID
feature reports. That means:

- Ophis cannot lock out Razer's RGB path at the OS level;
- every command is still serialised through one transport, and the app never
  creates two writers even if `Ophis.exe` is launched twice (a named pipe
  forwards the second launch to the first instance);
- keep Synapse closed while Ophis runs, so both do not address the EC at the
  same time.

Razer's power/fan path may use a different channel and can keep working; Ophis
does not depend on it.

## Build from source

```powershell
git clone https://github.com/EpicYamo/ophis.git
cd ophis
py -3 -m pip install -e ".[windows]"

# development run
py -3 -m ophis.windows.app --preview
py -3 -m ophis.windows.app

# portable build
powershell -ExecutionPolicy Bypass -File windows/build.ps1
```

Output:

```
dist/Ophis/Ophis.exe        windowed app
dist/Ophis/Ophis-cli.exe    console build for --probe
dist/Ophis-windows.zip      portable archive
```

## License

MIT. Not affiliated with Razer Inc.

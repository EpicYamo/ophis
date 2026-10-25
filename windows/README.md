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

## Check the device lock

Run `Ophis-cli.exe --probe` in PowerShell:

```powershell
.\Ophis-cli.exe --probe
```

It prints:

- whether the controller could be opened,
- the exclusive lock status and the HID usage page,
- the current brightness, fan target, power mode and charge limit,
- any Razer/Synapse processes that are still running.

If it says the interface is in use, close Razer Synapse (or stop its services)
and run the probe again.

## Why Synapse and Ophis should not write at the same time

The controller has one vendor HID collection. Ophis opens it with **share mode
0** and never falls back to a shared handle. That means:

- if Ophis starts first, Razer's RGB path cannot open the collection;
- if Synapse starts first, Ophis refuses to write and shows a clear error;
- the app never creates two writers, even if `Ophis.exe` is launched twice
  (a named pipe forwards the second launch to the first instance).

Razer's power/fan path may use a different channel and can keep working; Ophis
does not depend on it. For a clean setup, keep Synapse closed.

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

# Security

Explorer Advance — PnPUtil is a **local Windows desktop helper**. It is not a
network service and it does not send files anywhere.

## What the app can change

- **List / inspect** (`pnputil /enum-drivers`, `/files`, `/ids`,
  `/enum-devices /problem`) only reads the driver store and device list.
- **Export** (`pnputil /export-driver`) copies selected OEM packages out of
  the store into a folder you pick. It does not install, delete, or disable
  anything.

`/delete-driver`, `/disable-device`, `/remove-device`, and `/force` are
documented on the Command map and are **not wired** in the UI.

## Localhost only

The UI listens on `127.0.0.1` so other machines on the LAN cannot open it.
Do not change the host to `0.0.0.0` unless you understand that anyone who
can reach that port can list drivers and export packages as the logged-in
Windows user.

## Local files to keep private

`user_config.json` is created on this PC and listed in `.gitignore`. After an
export it can contain a folder path from this machine. Do not commit it or
attach it to issues.

## Reporting a problem

Open a GitHub issue. Do not attach driver-store dumps that include private
hardware serials unless you mean to.

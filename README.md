# Horizon Service Monitor

A read-only Windows desktop monitor for VMware / Omnissa Horizon services and
related Windows Event Log records. Built with Python, Tkinter and Windows PowerShell;
no third-party Python packages are required.

## Features

- Automatic service discovery and a 30-second status refresh.
- Status, startup type and process ID for each service.
- Separate direct and indirect Event lists for the last 48 hours of System and
  Application logs, with full message, XML, record ID and match reason.
- Case-insensitive service-name/display-name matching. Indirect matching requires
  a service-specific executable or path; shared and generic host binaries are excluded.
- Scan counts, elapsed time and visible read/parse errors.
- Live Turkish / English language selector, including open Event and About windows.
- About window with GitHub, source, issue and MIT License links.
- Automatic local Horizon Admin Console HTTP check every 45 seconds, independent
  of service refresh, with HTTP status, connection failures and last-check time.

The application does not start, stop or restart services, or modify Event Logs.
Original service names, provider messages and XML remain unchanged when switching
the interface language. The language choice applies to the current session.

## Run

Requires Windows, Python 3.10+ with Tkinter, and Windows PowerShell 5.1.
The current Windows account must have permission to read services and the selected logs.

```powershell
python HorizonServiceMonitor.py
```

Choose **Türkçe** or **English** from the language selector. Select a service and
click **View Windows Events**. Event scans run in the background and have a
300-second timeout; the scan duration includes reading, message rendering and matching.

## Tests

Run on Windows with Tkinter available:

```powershell
python -m unittest -v
```

The tests execute the production PowerShell matcher against synthetic events and
exercise the real Tkinter widgets. Synthetic RestartManager event `10006` and an
unrelated dependency event `7001` verify classification; these fixtures do not
substitute for validation on a Horizon Connection Server.

## Local admin console availability

The fixed endpoint is **`https://127.0.0.1/admin/`**, checked at startup and every
45 seconds in a background worker. No URL configuration is needed. This follows
[Omnissa's Horizon Console documentation](https://docs.omnissa.com/Horizon8InstallUpgrade/LogIntoHorizonConsole),
which specifies `/admin` and recommends `127.0.0.1` for connections from the server
itself. Run the monitor on each Connection Server to check that server's console.
On a client PC without a local console, a connection failure is expected.

Only **HTTP 200** is shown as reachable. The probe sends a GET and closes the
response without downloading the body or logging in. Local redirects within
`/admin/` are followed; redirects to HTML Access, other hosts or a load balancer
are not treated as a successful local admin check. Proxy settings are bypassed.
Each network operation has a 10-second timeout. The UI stays responsive during
checks, and a **Check Now** button is also available.

This is an HTTP availability check, not a functional login or certificate test.
For this numeric-loopback-only probe, TLS certificate validation is disabled so
self-signed certificates or certificates issued for the server's FQDN do not
hide the HTTP status. No credentials are sent. A 200 response does not establish
that all Horizon backend services or authentication are healthy.

## Türkçe

VMware / Omnissa Horizon servislerini ve ilgili Windows Event Log kayıtlarını
izleyen salt okunur bir masaüstü aracıdır. Servisler 30 saniyede bir yenilenir.
Dil seçicisinden Türkçe veya İngilizce seçildiğinde açık pencerelerin etiketleri
anında değişir; yeniden başlatma veya yeniden sorgulama gerekmez.
Admin paneli `https://127.0.0.1/admin/` adresinden otomatik olarak 45 saniyede bir
kontrol edilir. HTTP 200, farklı HTTP kodları, bağlantı hatası ve zaman aşımı
ayrı mesajlarla gösterilir. Adres girmeniz gerekmez; sunucuyu kontrol etmek için
uygulamayı o Connection Server üzerinde çalıştırın.

## Author and license

[AydinFatoglu](https://github.com/AydinFatoglu) ·
[Report an issue](https://github.com/AydinFatoglu/HorizonServiceMonitor/issues)

Copyright © 2026 AydinFatoglu. Distributed under the [MIT License](LICENSE).

This is an independent community project, not endorsed by VMware or Omnissa.
Product names are trademarks of their respective owners.

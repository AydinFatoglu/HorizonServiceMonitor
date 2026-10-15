"""Small, dependency-free UI translations; event data is never translated."""
import weakref


TEXT = {
    'tr': {
        'title': 'Horizon | Servis İzleme',
        'heading': 'VMware / Omnissa Horizon Servis İzleme',
        'refresh': 'Yenile', 'events_button': 'Windows Eventlerini Gör',
        'language': 'Dil', 'about': 'Hakkında', 'close': 'Kapat',
        'name': 'Servis Adı', 'display': 'Görünen Ad', 'state': 'Durum',
        'start': 'Başlangıç', 'pid': 'PID',
        'loading_services': 'Servis durumları okunuyor...',
        'service_footer': 'Salt okunur • Servisler 30 saniyede bir yenilenir • Eventleri görmek için servis seçin',
        'service_status': 'Son kontrol: {time}  |  Toplam: {count}  |  {summary}',
        'read_error': 'Okuma hatası: {error}',
        'web_title': 'Horizon Admin Paneli • 45 saniyede bir kontrol',
        'web_check': 'Şimdi Kontrol Et', 'web_checking': 'Admin paneli kontrol ediliyor...',
        'web_up': 'Admin paneli erişilebilir — HTTP 200',
        'web_http_error': 'Admin paneli HTTP 200 döndürmüyor — HTTP {code}',
        'web_connection_error': 'Admin paneline bağlanılamadı',
        'web_timeout': 'Admin paneli yanıtı zaman aşımına uğradı (10 sn)',
        'web_result': '{state} • Son kontrol: {time} • Süre: {seconds:.2f} sn',
        'web_scope': 'Bu makinenin /admin/ erişimi kontrol edilir; oturum açma ve sertifika geçerliliği test edilmez.',
        'Running': 'Çalışıyor', 'Stopped': 'Durduruldu', 'Stop Pending': 'Durduruluyor',
        'Start Pending': 'Başlatılıyor', 'Pause Pending': 'Duraklatılıyor',
        'Continue Pending': 'Devam ettiriliyor', 'Paused': 'Duraklatıldı', 'Unknown': 'Bilinmiyor',
        'Auto': 'Otomatik', 'Manual': 'El ile', 'Disabled': 'Devre dışı',
        'event_title': 'Windows Eventleri | {name}', 'refresh_events': 'Eventleri Yenile',
        'scanning': 'Windows Event Viewer kayıtları taranıyor...',
        'event_footer': 'System + Application • Son {hours} saat • Salt okunur',
        'direct': 'Doğrudan', 'indirect': 'Dolaylı',
        'event_section': '{kind} Event Kayıtları ({count})', 'unavailable': 'alınamadı',
        'detail_title': 'Event Detayları', 'time': 'Tarih / Saat', 'level': 'Seviye',
        'event_id': 'Event ID', 'log': 'Log', 'source': 'Kaynak',
        'event_error': 'Event okuma hatası: {error}',
        'no_records': 'Kayıtlar okunamadı.', 'partial': 'Sonuçlar eksik olabilir.',
        'no_matches': 'Eşleşen olay bulunamadı.', 'select_row': 'Ayrıntı için satır seçin.',
        'log_partial': ' (okunamadı / eksik)',
        'event_status': '{state}\n{logs} • Taranan: {total} • Doğrudan: {direct} • Dolaylı: {indirect} • Süre: {seconds:.2f} sn • Hata: {errors}\nAralık: {start} — {end}',
        'diagnostic_errors': 'Okuma / ayrıştırma hataları (ilk 20):\n{errors}',
        'reason_direct': 'Servis adı / görünen ad eşleşmesi: {term}',
        'reason_indirect': 'Servise özgü çalıştırılabilir dosya / yol: {term}',
        'reason_default': 'Servis adı veya görünen adı olayda geçiyor',
        'no_message': 'Mesaj metni alınamadı; XML içeriğine bakın.',
        'event_details': 'Eşleşme: {kind}\nAçıklama: {reason}\nTarih: {time}\nKaynak: {source}\nEvent ID: {id}\nLog: {log}\nRecord ID: {record}\n\n{message}\n\nXML:\n{xml}',
        'level_1': 'Kritik', 'level_2': 'Hata', 'level_3': 'Uyarı', 'level_4': 'Bilgi', 'level_5': 'Ayrıntılı', 'level_0': 'Bilgi',
        'about_title': 'Horizon Service Monitor Hakkında',
        'about_description': 'VMware / Omnissa Horizon servisleri ve Windows Event Log kayıtları için salt okunur izleme aracı.',
        'about_author': 'Geliştirici: AydinFatoglu', 'version': 'Sürüm {version}',
        'about_license': 'MIT Lisansı • Copyright © 2026 AydinFatoglu\nKullanım, değiştirme ve dağıtım MIT Lisansı koşullarına tabidir. Yazılım hiçbir garanti verilmeden sunulur.',
        'about_independent': 'Bağımsız bir topluluk projesidir; VMware veya Omnissa tarafından desteklenmez. Ürün adları ilgili sahiplerinin ticari markalarıdır.',
        'profile_link': 'GitHub Profili', 'repository_link': 'Kaynak Kodu',
        'issues_link': 'Hata Bildir / Öneri', 'license_link': 'MIT Lisansının Tam Metni',
    },
    'en': {
        'title': 'Horizon | Service Monitor',
        'heading': 'VMware / Omnissa Horizon Service Monitor',
        'refresh': 'Refresh', 'events_button': 'View Windows Events',
        'language': 'Language', 'about': 'About', 'close': 'Close',
        'name': 'Service Name', 'display': 'Display Name', 'state': 'Status',
        'start': 'Startup Type', 'pid': 'PID',
        'loading_services': 'Reading service status...',
        'service_footer': 'Read-only • Services refresh every 30 seconds • Select a service to view events',
        'service_status': 'Last checked: {time}  |  Total: {count}  |  {summary}',
        'read_error': 'Read error: {error}',
        'web_title': 'Horizon Admin Console • Checked every 45 seconds',
        'web_check': 'Check Now', 'web_checking': 'Checking the admin console...',
        'web_up': 'Admin console reachable — HTTP 200',
        'web_http_error': 'Admin console did not return HTTP 200 — HTTP {code}',
        'web_connection_error': 'Could not connect to the admin console',
        'web_timeout': 'Admin console response timed out (10 s)',
        'web_result': '{state} • Last checked: {time} • Duration: {seconds:.2f} s',
        'web_scope': 'Checks this machine’s /admin/ availability; login and certificate validity are not tested.',
        'Running': 'Running', 'Stopped': 'Stopped', 'Stop Pending': 'Stopping',
        'Start Pending': 'Starting', 'Pause Pending': 'Pausing',
        'Continue Pending': 'Resuming', 'Paused': 'Paused', 'Unknown': 'Unknown',
        'Auto': 'Automatic', 'Manual': 'Manual', 'Disabled': 'Disabled',
        'event_title': 'Windows Events | {name}', 'refresh_events': 'Refresh Events',
        'scanning': 'Scanning Windows Event Viewer records...',
        'event_footer': 'System + Application • Last {hours} hours • Read-only',
        'direct': 'Direct', 'indirect': 'Indirect',
        'event_section': '{kind} Events ({count})', 'unavailable': 'unavailable',
        'detail_title': 'Event Details', 'time': 'Date / Time', 'level': 'Level',
        'event_id': 'Event ID', 'log': 'Log', 'source': 'Provider',
        'event_error': 'Event read error: {error}',
        'no_records': 'Records could not be read.', 'partial': 'Results may be incomplete.',
        'no_matches': 'No matching events found.', 'select_row': 'Select a row for details.',
        'log_partial': ' (unreadable / incomplete)',
        'event_status': '{state}\n{logs} • Scanned: {total} • Direct: {direct} • Indirect: {indirect} • Duration: {seconds:.2f} s • Errors: {errors}\nRange: {start} — {end}',
        'diagnostic_errors': 'Read / parsing errors (first 20):\n{errors}',
        'reason_direct': 'Service name / display name match: {term}',
        'reason_indirect': 'Service-specific executable / path: {term}',
        'reason_default': 'The service name or display name appears in the event',
        'no_message': 'Message text is unavailable; see the XML content.',
        'event_details': 'Match: {kind}\nReason: {reason}\nDate: {time}\nProvider: {source}\nEvent ID: {id}\nLog: {log}\nRecord ID: {record}\n\n{message}\n\nXML:\n{xml}',
        'level_1': 'Critical', 'level_2': 'Error', 'level_3': 'Warning', 'level_4': 'Information', 'level_5': 'Verbose', 'level_0': 'Information',
        'about_title': 'About Horizon Service Monitor',
        'about_description': 'A read-only monitor for VMware / Omnissa Horizon services and Windows Event Log records.',
        'about_author': 'Developer: AydinFatoglu', 'version': 'Version {version}',
        'about_license': 'MIT License • Copyright © 2026 AydinFatoglu\nUse, modification and distribution are subject to the MIT License. This software is provided without warranty.',
        'about_independent': 'An independent community project; not endorsed by VMware or Omnissa. Product names are trademarks of their respective owners.',
        'profile_link': 'GitHub Profile', 'repository_link': 'Source Code',
        'issues_link': 'Report an Issue / Suggestion', 'license_link': 'Full MIT License',
    },
}


class Language:
    def __init__(self, code='tr'):
        self.code = code
        self._listeners = []

    def t(self, key, **values):
        return TEXT[self.code].get(key, key).format(**values)

    def subscribe(self, callback):
        self._listeners.append(weakref.WeakMethod(callback))

    def set(self, code):
        if code not in TEXT:
            raise ValueError(f'Unsupported language: {code}')
        if code == self.code:
            return
        self.code = code
        self._listeners = [ref for ref in self._listeners if ref() is not None]
        for ref in self._listeners:
            callback = ref()
            if callback is not None:
                callback()


class Localized:
    def init_language(self, master):
        if not hasattr(master, '_hsm_language'):
            master._hsm_language = Language()
        self.language = master._hsm_language
        self._labels = []
        self._headings = []
        self.language.subscribe(self.apply_language)

    def t(self, key, **values):
        return self.language.t(key, **values)

    def label(self, widget, key, **values):
        self._labels.append((widget, key, values))
        widget.configure(text=self.t(key, **values))
        return widget

    def heading(self, tree, column, key):
        self._headings.append((tree, column, key))
        tree.heading(column, text=self.t(key))

    def apply_language(self):
        if self.closed:
            return
        for widget, key, values in self._labels:
            widget.configure(text=self.t(key, **values))
        for tree, column, key in self._headings:
            tree.heading(column, text=self.t(key))
        self.update_language()

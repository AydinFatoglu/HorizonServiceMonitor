import json
import base64
import logging
import os
import queue
import re
import xml.etree.ElementTree as ET
import subprocess
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk
from localization import Language, Localized
from web_health import ADMIN_URL, WEB_REFRESH_MS, check_admin_web

VERSION = '1.1.1'
GITHUB_PROFILE = 'https://github.com/AydinFatoglu'
REPOSITORY_URL = GITHUB_PROFILE + '/HorizonServiceMonitor'
REFRESH_MS = 30_000
EVENT_HOURS = 48
SERVICE_PS = r'''
$ErrorActionPreference='Stop'
$services = Get-CimInstance Win32_Service | Where-Object {
 $_.Name -match 'VMware|Omnissa|Horizon|^OmnissaHzeDS$|^ADAM_VMwareVDMDS$|^PCOIPSG$|^VGAuthService$|^VM3DService$|^VMBlastSG$|^VMTools$|^vmvss$|^wsbroker$|^wscrl$|^wsdct$|^wsmsgbus$|^wsnm$|^WSSH$|^wstomcat$|^wstunnel$' -or
 $_.DisplayName -match 'VMware|Omnissa|Horizon'
} | Select-Object Name,DisplayName,State,StartMode,ProcessId,PathName
ConvertTo-Json -InputObject @($services) -Compress -Depth 3
'''
EVENT_PS = r'''
$ErrorActionPreference='Stop'
$name=$env:HSM_SERVICE_NAME
$display=$env:HSM_SERVICE_DISPLAY
$path=[string]$env:HSM_SERVICE_PATH
$hours=[int]$env:HSM_EVENT_HOURS
if (-not $name -or $hours -le 0) {throw 'Servis adı veya saat aralığı geçersiz.'}
$timer=[Diagnostics.Stopwatch]::StartNew()
$end=Get-Date
$start=$end.AddHours(-$hours)
$issues=New-Object 'System.Collections.Generic.List[string]'
$issueCount=0
function Add-Issue([string]$text) {
 $script:issueCount++
 if ($issues.Count -lt 20) {[void]$issues.Add($text)}
}
function Get-Exe([string]$command) {
 if ($command -match '^\s*"([^"]+?\.exe)"') {return $Matches[1]}
 if ($command -match '^\s*(.+?\.exe)(?:\s|$)') {return $Matches[1]}
 return ''
}
function Term-Pattern([string]$term) {
 return '(?i)(?<![\p{L}\p{N}_.\\/-])' + [regex]::Escape($term) + '(?![\p{L}\p{N}_\\/-]|\.[\p{L}\p{N}_])'
}
$directTerms=@($name,$display) | Where-Object { $_ -and $_.Trim() } | Select-Object -Unique
$exe=Get-Exe $path
$exeName=if ($exe) {[IO.Path]::GetFileName($exe)} else {''}
$generic=@('svchost.exe','rundll32.exe','dllhost.exe','cmd.exe','powershell.exe','pwsh.exe','conhost.exe','java.exe','javaw.exe','python.exe','pythonw.exe','dotnet.exe')
$indirectTerms=@()
# Only allow an executable identity after comparing all installed services.
if ($exeName -and $exeName.ToLowerInvariant() -notin $generic) {
 try {
  $others=@(Get-CimInstance Win32_Service -ErrorAction Stop | Where-Object {$_.Name -ne $name})
  $otherPaths=@($others | ForEach-Object {Get-Exe ([string]$_.PathName)} | Where-Object {$_})
  if ($exe -notin $otherPaths) {$indirectTerms+= $exe}
  $otherNames=@($otherPaths | ForEach-Object {[IO.Path]::GetFileName($_)})
  if ($exeName -notin $otherNames) {$indirectTerms+= $exeName}
 } catch {Add-Issue "Servis dosyası sahipliği doğrulanamadı; dolaylı eşleştirme kapalı: $($_.Exception.Message)"}
}
$directRules=@($directTerms | ForEach-Object {@{Term=$_; Pattern=(Term-Pattern $_)}})
$indirectRules=@($indirectTerms | ForEach-Object {@{Term=$_; Pattern=(Term-Pattern $_)}})
$matched=New-Object 'System.Collections.Generic.List[object]'
$logs=@{}
foreach ($log in @('System','Application')) {
 $logTimer=[Diagnostics.Stopwatch]::StartNew()
 $stats=@{Count=0;Success=$false;Seconds=0}
 $logs[$log]=$stats
 try {
  # Stream records; do not materialize the entire 48-hour log in memory.
  Get-WinEvent -FilterHashtable @{LogName=$log;StartTime=$start;EndTime=$end} -ErrorAction Stop | ForEach-Object {
   $ev=$_; $stats.Count++
   $msg=''; $xmlText=''; $fields=@()
   # Calling FormatDescription explicitly exposes provider rendering failures
   # that PowerShell's adapted Message property can silently turn into null.
   try {$msg=[string]$ev.FormatDescription()} catch {Add-Issue "$log / $($ev.RecordId) mesaj: $($_.Exception.Message)"}
   try {
    $xmlText=[string]$ev.ToXml()
    $xml=[xml]$xmlText
    $fields=@($xml.SelectNodes("/*[local-name()='Event']/*[local-name()='EventData' or local-name()='UserData']//*[not(*)]") | ForEach-Object {$_.InnerText})
   } catch {Add-Issue "$log / $($ev.RecordId) XML: $($_.Exception.Message)"}
   $texts=@($msg)+$fields
   $kind=''; $reason=''
   foreach ($rule in $directRules) {
    if ($texts -match $rule.Pattern) {
     $kind='direct'; $reason="Servis adı / görünen ad eşleşmesi: $($rule.Term)"; break
    }
   }
   if (-not $kind) {
    foreach ($rule in $indirectRules) {
     if ($texts -match $rule.Pattern) {
      $kind='indirect'; $reason="Servise özgü çalıştırılabilir dosya / yol: $($rule.Term)"; break
     }
    }
   }
   if ($kind) {
    [void]$matched.Add([pscustomobject]@{Time=$ev.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss');Log=$ev.LogName;Id=$ev.Id;Level=$ev.LevelDisplayName;LevelCode=$ev.Level;Source=$ev.ProviderName;Message=$msg;Xml=$xmlText;RecordId=$ev.RecordId;MatchType=$kind;Reason=$reason})
   }
  }
  $stats.Success=$true
 } catch {
  if ($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*') {$stats.Success=$true}
  else {Add-Issue "$log okunamadı: $($_.Exception.Message)"}
 }
 $stats.Seconds=[math]::Round($logTimer.Elapsed.TotalSeconds,3)
}
$timer.Stop()
$result=@{Events=@($matched.ToArray() | Sort-Object Time -Descending); Diagnostics=@{
 Logs=$logs; Total=($logs.System.Count+$logs.Application.Count);
 Direct=@($matched.ToArray() | Where-Object MatchType -eq 'direct').Count;
 Indirect=@($matched.ToArray() | Where-Object MatchType -eq 'indirect').Count;
 Seconds=[math]::Round($timer.Elapsed.TotalSeconds,3);Errors=@($issues.ToArray());ErrorCount=$issueCount;
 StartTime=$start.ToString('o');EndTime=$end.ToString('o')
}}
ConvertTo-Json -InputObject $result -Compress -Depth 8
'''


def run_ps(script, timeout=35, env=None):
    e=os.environ.copy()
    if env: e.update(env)
    # PowerShell 5.1 otherwise writes redirected output using the OEM code page.
    prelude = "$ProgressPreference='SilentlyContinue'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding;\n"
    encoded=base64.b64encode((prelude+script).encode('utf-16le')).decode('ascii')
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,text=True,encoding='utf-8-sig',errors='strict',timeout=timeout,env=e,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'PowerShell sorgusu {timeout} saniyede tamamlanamadı; sonuçlar alınamadı. Daha dar bir zaman aralığıyla tanılama yapın.') from exc
    stderr = powershell_errors(result.stderr)
    if result.returncode:
        raise RuntimeError(stderr or f'PowerShell çıkış kodu: {result.returncode}')
    if stderr:
        raise RuntimeError('PowerShell hata çıktısı: '+stderr)
    raw=result.stdout.strip()
    if not raw:
        raise RuntimeError('PowerShell boş çıktı döndürdü; JSON sonucu alınamadı.')
    try:
        data=json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'PowerShell JSON ayrıştırma hatası: {exc}') from exc
    if not isinstance(data,(list,dict)):
        raise RuntimeError('PowerShell JSON sonucu bir liste veya nesne olmalı.')
    return data


def powershell_errors(stderr):
    """EncodedCommand can emit module progress as CLIXML on stderr."""
    raw = stderr.strip()
    if not raw.startswith('#< CLIXML'):
        return raw
    try:
        root = ET.fromstring(raw.partition('\n')[2])
        errors = [node.text or '' for node in root.iter() if node.get('S') == 'Error' or node.get('S') == 'error']
        return re.sub(r'_x([0-9A-Fa-f]{4})_', lambda m: chr(int(m[1], 16)), '\n'.join(errors)).strip()
    except ET.ParseError:
        return raw


def validate_event_result(result):
    """Reject broken transport instead of rendering it as zero matches."""
    try:
        if not isinstance(result, dict) or not isinstance(result['Events'], list):
            raise ValueError('Events listesi eksik')
        d = result['Diagnostics']
        for log in ('System', 'Application'):
            if not isinstance(d['Logs'][log]['Success'], bool):
                raise ValueError('Log durumu geçersiz')
            if not isinstance(d['Logs'][log]['Count'], int):
                raise ValueError('Log sayısı geçersiz')
        for key in ('Total', 'Direct', 'Indirect', 'ErrorCount'):
            if not isinstance(d[key], int) or d[key] < 0:
                raise ValueError('Tanılama sayısı geçersiz')
        if not isinstance(d['Seconds'], (int, float)) or not isinstance(d['Errors'], list):
            raise ValueError('Süre veya hatalar geçersiz')
        if any(not isinstance(e, dict) or e.get('MatchType') not in ('direct', 'indirect') for e in result['Events']):
            raise ValueError('Event sınıflandırması geçersiz')
        if d['Direct'] != sum(e['MatchType'] == 'direct' for e in result['Events']) or d['Indirect'] != sum(e['MatchType'] == 'indirect' for e in result['Events']):
            raise ValueError('Event sayıları uyuşmuyor')
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f'Event JSON yapısı geçersiz: {exc}') from exc


def event_status(result, language=None):
    t = (language or Language()).t
    d = result['Diagnostics']
    logs = d['Logs']
    counts = ' • '.join(f"{log}: {logs[log]['Count']}" + ('' if logs[log]['Success'] else t('log_partial')) for log in ('System', 'Application'))
    state = ('no_records' if not any(logs[k]['Success'] for k in logs)
             else 'partial' if d['ErrorCount'] or not all(logs[k]['Success'] for k in logs)
             else 'no_matches' if not result['Events'] else 'select_row')
    return t('event_status', state=t(state), logs=counts, total=d['Total'], direct=d['Direct'],
             indirect=d['Indirect'], seconds=d['Seconds'], errors=d['ErrorCount'],
             start=d.get('StartTime', ''), end=d.get('EndTime', ''))


class UiDispatch:
    """Workers only enqueue callbacks; all Tcl calls run on the GUI thread."""
    def init_dispatch(self, widget):
        self.closed=False
        self._ui_widget=widget
        self._callbacks=queue.Queue()
        self._poll_id=widget.after(50,self._poll_callbacks)

    def safe_after(self, callback):
        if not self.closed:
            self._callbacks.put(callback)

    def _poll_callbacks(self):
        if self.closed:
            return
        try:
            while not self.closed:
                self._callbacks.get_nowait()()
        except queue.Empty:
            pass
        finally:
            if not self.closed:
                self._poll_id=self._ui_widget.after(50,self._poll_callbacks)

    def stop_dispatch(self):
        self.closed=True
        self._ui_widget.after_cancel(self._poll_id)

class GridTreeview(ttk.Treeview):
    """Keep native selection and scrolling, with thin cell separators."""
    def __init__(self, master, **options):
        super().__init__(master, **options)
        self._grid_after = None
        self._grid_lines = []
        for event in ('<Configure>', '<Expose>', '<MouseWheel>', '<KeyRelease>', '<ButtonRelease-1>'):
            self.bind(event, self._schedule_grid, add='+')
        self.bind('<Destroy>', self._destroy_grid, add='+')

    def _schedule_grid(self, event=None):
        if self._grid_after is None:
            self._grid_after = self.after_idle(self._draw_grid)

    def _destroy_grid(self, event):
        if event.widget is self and self._grid_after is not None:
            self.after_cancel(self._grid_after)
            self._grid_after = None

    def _draw_grid(self):
        self._grid_after = None
        height, width = self.winfo_height(), self.winfo_width()
        # Inspect only visible rows, regardless of the number of Event records.
        rows = list(dict.fromkeys(self.identify_row(y) for y in range(0, height, 4)))
        boxes = [(iid, self.bbox(iid)) for iid in rows if iid]
        boxes = [(iid, box) for iid, box in boxes if box]
        positions = []
        if boxes:
            top = max(1, boxes[0][1][1])
            bottom = min(height - 1, boxes[-1][1][1] + boxes[-1][1][3])
            for _, (x, y, row_width, row_height) in boxes:
                edge = y + row_height - 1
                if top <= edge < height:
                    positions.append((max(1, x), edge, min(row_width, width - 2), 1))
            columns = self['displaycolumns']
            if columns == ('#all',):
                columns = self['columns']
            for column in columns:
                box = self.bbox(boxes[0][0], column)
                if box:
                    edge = box[0] + box[2] - 1
                    if 0 < edge < width:
                        positions.append((edge, top, 1, bottom - top))
        while len(self._grid_lines) < len(positions):
            line = tk.Frame(self, bg='#d6dde5', borderwidth=0, highlightthickness=0, takefocus=False)
            # Border pixels should behave like the underlying table on click
            # and wheel input rather than interrupting selection or scrolling.
            for sequence in ('<Button-1>', '<ButtonRelease-1>', '<MouseWheel>'):
                line.bind(sequence, lambda event, seq=sequence: self.event_generate(
                    seq, x=event.x_root-self.winfo_rootx(), y=event.y_root-self.winfo_rooty(),
                    time=event.time, state=event.state,
                    **({'delta': event.delta} if seq == '<MouseWheel>' else {})))
            self._grid_lines.append(line)
        for line, (x, y, line_width, line_height) in zip(self._grid_lines, positions):
            line.place(x=x, y=y, width=line_width, height=line_height)
        for line in self._grid_lines[len(positions):]:
            line.place_forget()

    def insert(self, *args, **kwargs):
        iid = super().insert(*args, **kwargs)
        self._schedule_grid()
        return iid

    def delete(self, *items):
        super().delete(*items)
        self._schedule_grid()

    def yview(self, *args):
        result = super().yview(*args)
        if args:
            self._schedule_grid()
        return result

    def xview(self, *args):
        result = super().xview(*args)
        if args:
            self._schedule_grid()
        return result


class EventWindow(UiDispatch, Localized):
    def __init__(self, master, name, display, path):
        self.win = tk.Toplevel(master)
        self.win.geometry('1150x760')
        self.win.minsize(850, 550)
        self.name, self.display, self.path = name, display, path
        self.events = {}
        self.result = None
        self.error_message = None
        self.busy = False
        self.init_dispatch(self.win)
        self.init_language(master)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(self.win, padding=12)
        frame.pack(fill='both', expand=True)
        top = ttk.Frame(frame)
        top.pack(fill='x', pady=(0, 8))
        ttk.Label(top, text=f'{display} ({name})', font=('Segoe UI', 14, 'bold')).pack(side='left')
        self.btn = self.label(ttk.Button(top, command=self.refresh), 'refresh_events')
        self.btn.pack(side='right')
        self.info = tk.StringVar()
        ttk.Label(frame, textvariable=self.info, wraplength=1050).pack(anchor='w', pady=(0, 8))
        panes = ttk.Panedwindow(frame, orient='vertical')
        panes.pack(fill='both', expand=True)
        self.trees = {}
        for kind in ('Doğrudan', 'Dolaylı'):
            section = ttk.LabelFrame(panes, text=f'{kind} Event Kayıtları (0)', padding=6)
            panes.add(section, weight=2)
            self.trees[kind] = self.make_tree(section, kind)
            section._kind = kind
            if not hasattr(self, 'sections'):
                self.sections = {}
            self.sections[kind] = section
        detail = self.label(ttk.LabelFrame(panes, padding=7), 'detail_title')
        panes.add(detail, weight=2)
        self.message = tk.Text(detail, wrap='word', font=('Consolas', 10), state='disabled')
        scroll = ttk.Scrollbar(detail, orient='vertical', command=self.message.yview)
        self.message.configure(yscrollcommand=scroll.set)
        self.message.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.label(ttk.Label(frame, foreground='#64748b'), 'event_footer', hours=EVENT_HOURS).pack(anchor='w', pady=(8, 0))
        self.update_language()
        self.refresh()

    def make_tree(self, parent, kind):
        table = ttk.Frame(parent)
        table.pack(fill='both', expand=True)
        cols = ('time', 'level', 'id', 'log', 'source')
        tree = GridTreeview(table, columns=cols, show='headings', selectmode='browse', height=6)
        for col, title, width in [('time','time',165),('level','level',100),('id','event_id',90),('log','log',110),('source','source',420)]:
            self.heading(tree, col, title)
            tree.column(col, width=width, anchor='w', stretch=(col=='source'))
        sy = ttk.Scrollbar(table, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=sy.set)
        tree.pack(side='left', fill='both', expand=True)
        sy.pack(side='right', fill='y')
        tree.tag_configure('error', foreground='#b91c1c')
        tree.tag_configure('warning', foreground='#b45309')
        tree.bind('<<TreeviewSelect>>', lambda event, k=kind: self.show_message(k))
        return tree

    def refresh(self):
        if self.closed or self.busy:
            return
        self.busy = True
        self.error_message = None
        self.btn.configure(state='disabled')
        self.info.set(self.t('scanning'))
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            events = run_ps(EVENT_PS, timeout=300, env={
                'HSM_SERVICE_NAME': self.name,
                'HSM_SERVICE_DISPLAY': self.display,
                'HSM_SERVICE_PATH': self.path,
                'HSM_EVENT_HOURS': str(EVENT_HOURS)
            })
            validate_event_result(events)
            self.safe_after(lambda: self.render(events))
        except Exception as exc:
            msg = str(exc)
            logging.getLogger(__name__).exception('Event sorgusu başarısız: %s', self.name)
            self.safe_after(lambda: self.error(msg))

    def close(self):
        self.stop_dispatch()
        self.win.destroy()

    def render(self, result):
        if self.closed:
            return
        events = result['Events']
        self.result = result
        self.error_message = None
        self.events = {}
        self.set_message('')
        for kind, tree in self.trees.items():
            tree.delete(*tree.get_children())
            subset = [e for e in events if e.get('MatchType') == {'Doğrudan':'direct','Dolaylı':'indirect'}[kind]]
            for i, event in enumerate(subset):
                level = str(event.get('Level') or '')
                tag = 'error' if event.get('LevelCode') in (1,2) else 'warning' if event.get('LevelCode') == 3 else ''
                iid = str(i)
                self.events[(kind, iid)] = event
                tree.insert('', 'end', iid=iid, values=(event.get('Time'), level, event.get('Id'), event.get('Log'), event.get('Source')), tags=(tag,))
        if result['Diagnostics']['ErrorCount']:
            details='\n'.join(result['Diagnostics']['Errors'])
            logging.getLogger(__name__).warning('Event tanılama (%s): %s', self.name, details)
        self.busy = False
        self.btn.configure(state='normal')
        self.update_language()

    def error(self, msg):
        if self.closed:
            return
        self.error_message = msg
        self.result = None
        for kind, tree in self.trees.items():
            tree.delete(*tree.get_children())
        self.events = {}
        self.set_message(msg)
        self.busy = False
        self.btn.configure(state='normal')
        self.update_language()

    def update_language(self):
        self.win.title(self.t('event_title', name=self.name))
        for kind, tree in self.trees.items():
            key = 'direct' if kind == 'Doğrudan' else 'indirect'
            count = self.t('unavailable') if self.error_message else len(tree.get_children())
            self.sections[kind].configure(text=self.t('event_section', kind=self.t(key), count=count))
            for iid in tree.get_children():
                event = self.events[(kind, iid)]
                level = self.t('level_' + str(event.get('LevelCode'))) if event.get('LevelCode') in range(6) else event.get('Level', '')
                tree.set(iid, 'level', level)
        if self.busy:
            self.info.set(self.t('scanning'))
        elif self.error_message:
            self.info.set(self.t('event_error', error=self.error_message[:350]))
            self.set_message(self.error_message)
        elif self.result is not None:
            self.info.set(event_status(self.result, self.language))
        for kind, tree in self.trees.items():
            if tree.selection():
                self.show_message(kind)
                break
        else:
            if self.result and self.result['Diagnostics']['ErrorCount']:
                self.set_message(self.t('diagnostic_errors', errors='\n'.join(self.result['Diagnostics']['Errors'])))

    def set_message(self, value):
        self.message.configure(state='normal')
        self.message.delete('1.0', 'end')
        self.message.insert('1.0', value)
        self.message.configure(state='disabled')

    def show_message(self, kind):
        tree = self.trees[kind]
        selected = tree.selection()
        if not selected:
            return
        other = 'Dolaylı' if kind == 'Doğrudan' else 'Doğrudan'
        self.trees[other].selection_remove(*self.trees[other].selection())
        e = self.events.get((kind, selected[0]), {})
        key = 'direct' if kind == 'Doğrudan' else 'indirect'
        original_reason = e.get('Reason') or ''
        term = original_reason.partition(': ')[2]
        reason = self.t('reason_' + key, term=term) if term else self.t('reason_default')
        self.set_message(self.t('event_details', kind=self.t(key), reason=reason,
            time=e.get('Time',''), source=e.get('Source',''), id=e.get('Id',''),
            log=e.get('Log',''), record=e.get('RecordId',''),
            message=e.get('Message','') or self.t('no_message'), xml=e.get('Xml','')))

class WebHealthPanel(UiDispatch, Localized):
    def __init__(self, parent, master):
        self.frame = ttk.LabelFrame(parent, padding=8)
        self.frame.pack(fill='x', pady=(0, 10))
        self.busy = False
        self.after_id = None
        self.result = None
        self.checked_at = None
        self.init_dispatch(self.frame)
        self.init_language(master)
        self.label(self.frame, 'web_title')
        row = ttk.Frame(self.frame)
        row.pack(fill='x')
        ttk.Label(row, text=ADMIN_URL).pack(side='left')
        self.button = self.label(ttk.Button(row, command=self.refresh), 'web_check')
        self.button.pack(side='right')
        self.info = tk.StringVar()
        self.status_label = ttk.Label(self.frame, textvariable=self.info, wraplength=1000)
        self.status_label.pack(anchor='w', pady=(4, 0))
        self.label(ttk.Label(self.frame, foreground='#64748b', wraplength=1000), 'web_scope').pack(anchor='w', pady=(3, 0))
        self.frame.bind('<Destroy>', lambda event: self.close() if event.widget is self.frame else None)
        self.refresh()

    def refresh(self):
        if self.closed or self.busy:
            return
        if self.after_id is not None:
            self.frame.after_cancel(self.after_id)
            self.after_id = None
        self.busy = True
        self.button.configure(state='disabled')
        self.update_language()
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            result = check_admin_web()
        except Exception as exc:
            result = {'kind': 'connection_error', 'code': None, 'seconds': 0, 'detail': str(exc)}
        self.safe_after(lambda: self.render(result))

    def render(self, result):
        if self.closed:
            return
        self.result = result
        self.checked_at = datetime.now()
        self.busy = False
        self.button.configure(state='normal')
        self.update_language()
        # Start-to-start cadence, unless a slow check itself exceeded 45 sec.
        delay = max(1, WEB_REFRESH_MS - round(result['seconds'] * 1000))
        self.after_id = self.frame.after(delay, self.refresh)

    def update_language(self):
        if self.busy or self.result is None:
            self.info.set(self.t('web_checking'))
            self.status_label.configure(foreground='#64748b')
            return
        result = self.result
        if result['kind'] == 'http':
            key = 'web_up' if result['code'] == 200 else 'web_http_error'
        else:
            key = 'web_timeout' if result['kind'] == 'timeout' else 'web_connection_error'
        state = self.t(key, code=result['code'])
        self.info.set(self.t('web_result', state=state, time=self.checked_at.strftime('%d.%m.%Y %H:%M:%S'), seconds=result['seconds']))
        self.status_label.configure(foreground='#16803d' if key == 'web_up' else '#b91c1c')

    def close(self):
        if self.closed:
            return
        if self.after_id is not None:
            self.frame.after_cancel(self.after_id)
        self.stop_dispatch()


class AboutWindow(Localized):
    def __init__(self, master):
        self.closed = False
        self.win = tk.Toplevel(master)
        self.win.geometry('590x550')
        self.win.minsize(550, 510)
        self.win.transient(master)
        self.init_language(master)
        frame = ttk.Frame(self.win, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Horizon Service Monitor', font=('Segoe UI', 18, 'bold')).pack(anchor='w')
        self.label(ttk.Label(frame), 'version', version=VERSION).pack(anchor='w', pady=(2, 14))
        for key in ('about_description', 'about_author', 'about_license', 'about_independent'):
            self.label(ttk.Label(frame, wraplength=520, justify='left'), key).pack(anchor='w', pady=(0, 12))
        links = ttk.Frame(frame)
        links.pack(fill='x', pady=(0, 14))
        self.link_buttons = {}
        for index, (key, url) in enumerate((
            ('profile_link', GITHUB_PROFILE), ('repository_link', REPOSITORY_URL),
            ('issues_link', REPOSITORY_URL + '/issues'),
            ('license_link', REPOSITORY_URL + '/blob/main/LICENSE'),
        )):
            button = self.label(ttk.Button(links, command=lambda target=url: webbrowser.open(target)), key)
            button.grid(row=index // 2, column=index % 2, sticky='ew', padx=3, pady=3)
            self.link_buttons[key] = button
        links.columnconfigure((0, 1), weight=1)
        self.label(ttk.Button(frame, command=self.close), 'close').pack(side='bottom', anchor='e')
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.update_language()

    def update_language(self):
        self.win.title(self.t('about_title'))

    def close(self):
        self.closed = True
        self.win.destroy()


class Monitor(UiDispatch, Localized):
    def __init__(self,root):
        self.root=root;root.title('Horizon | Service Monitor');root.geometry('1100x590');root.minsize(820,430)
        self.busy=False;self.closed=False;self.after_id=None;self.service_paths={}
        self._data = None
        self._error = None
        self.checked_at = None
        self.init_dispatch(root)
        self.init_language(root)
        frame=ttk.Frame(root,padding=16);frame.pack(fill='both',expand=True)
        top=ttk.Frame(frame);top.pack(fill='x',pady=(0,12))
        self.label(ttk.Label(top,font=('Segoe UI',17,'bold')), 'heading').pack(side='left')
        controls = ttk.Frame(frame)
        controls.pack(fill='x', pady=(0, 10))
        self.label(ttk.Label(controls), 'language').pack(side='left', padx=(0, 8))
        self.language_choice = tk.StringVar(value='Türkçe')
        self.language_dropdown = ttk.Combobox(controls, textvariable=self.language_choice, values=('Türkçe', 'English'), state='readonly', width=12)
        self.language_dropdown.pack(side='left')
        self.language_dropdown.bind('<<ComboboxSelected>>', self.change_language)
        self.label(ttk.Button(controls, command=self.open_about), 'about').pack(side='right')
        self.refresh_button=self.label(ttk.Button(top,command=self.refresh),'refresh');self.refresh_button.pack(side='right')
        self.event_button=self.label(ttk.Button(top,command=self.open_events,state='disabled'),'events_button')
        self.event_button.pack(side='right',padx=(0,8))
        self.info=tk.StringVar()
        ttk.Label(frame,textvariable=self.info).pack(anchor='w',pady=(0,10))
        self.web_health = WebHealthPanel(frame, root)
        table=ttk.Frame(frame);table.pack(fill='both',expand=True)
        cols=('name','display','state','start','pid')
        self.tree=GridTreeview(table,columns=cols,show='headings',selectmode='browse')
        for col,title,width,anchor in [('name','name',175,'w'),('display','display',450,'w'),('state','state',130,'center'),('start','start',120,'center'),('pid','pid',80,'center')]:
            self.heading(self.tree,col,title);self.tree.column(col,width=width,minwidth=60,anchor=anchor,stretch=(col=='display'))
        scrollbar=ttk.Scrollbar(table,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        for tag,color in [('running','#16803d'),('stopped','#c0392b'),('pending','#c07700'),('other','#475569')]:self.tree.tag_configure(tag,foreground=color)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.event_button.configure(state='normal' if self.tree.selection() else 'disabled'))
        self.tree.bind('<Double-1>',lambda e:self.open_events())
        self.label(ttk.Label(frame,foreground='#64748b'), 'service_footer').pack(anchor='w',pady=(10,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()

    def change_language(self, event=None):
        self.language.set('en' if self.language_choice.get() == 'English' else 'tr')

    def open_about(self):
        AboutWindow(self.root)

    def update_language(self):
        self.root.title(self.t('title'))
        self.language_choice.set('English' if self.language.code == 'en' else 'Türkçe')
        if self._data is not None:
            services = {s['Name']: s for s in self._data}
            for iid in self.tree.get_children():
                name = self.tree.set(iid, 'name')
                self.tree.set(iid, 'state', self.t(str(services[name].get('State') or 'Unknown')))
                self.tree.set(iid, 'start', self.t(str(services[name].get('StartMode') or 'Unknown')))
        if self.busy or self._data is None and self._error is None:
            self.info.set(self.t('loading_services'))
        elif self._error is not None:
            self.info.set(self.t('read_error', error=self._error[:300]))
        else:
            counts = {}
            for service in self._data:
                state = str(service.get('State') or 'Unknown')
                counts[state] = counts.get(state, 0) + 1
            summary = '  |  '.join(f'{self.t(k)}: {v}' for k, v in sorted(counts.items()))
            self.info.set(self.t('service_status', time=self.checked_at.strftime('%d.%m.%Y %H:%M:%S'), count=len(self._data), summary=summary))

    def open_events(self):
        selection=self.tree.selection()
        if not selection:return
        values=self.tree.item(selection[0],'values')
        EventWindow(self.root,values[0],values[1],self.service_paths.get(values[0],''))

    def refresh(self):
        if self.closed or self.busy:return
        if self.after_id is not None:self.root.after_cancel(self.after_id);self.after_id=None
        self.busy=True;self._error=None;self.refresh_button.configure(state='disabled');self.update_language()
        threading.Thread(target=self.worker,daemon=True).start()

    def worker(self):
        try:
            data=run_ps(SERVICE_PS,timeout=35)
            if isinstance(data,dict):data=[data]
            self.safe_after(lambda:self.render(data))
        except Exception as exc:
            msg=str(exc);self.safe_after(lambda:self.error(msg))

    def render(self,data):
        if self.closed:return
        self._data = data
        self._error = None
        self.checked_at = datetime.now()
        selected=self.tree.selection()
        selected_name=self.tree.item(selected[0],'values')[0] if selected else None
        self.tree.delete(*self.tree.get_children())
        counts={}
        self.service_paths={str(s.get('Name','')):str(s.get('PathName') or '') for s in data}
        for s in sorted(data,key=lambda x:str(x.get('Name','')).lower()):
            state=str(s.get('State') or 'Unknown');counts[state]=counts.get(state,0)+1
            tag='running' if state=='Running' else 'stopped' if state=='Stopped' else 'pending' if 'Pending' in state else 'other'
            name=s.get('Name','')
            iid=self.tree.insert('','end',values=(name,s.get('DisplayName',''),state,s.get('StartMode',''),s.get('ProcessId') or '—'),tags=(tag,))
            if name==selected_name:self.tree.selection_set(iid)
        self.event_button.configure(state='normal' if self.tree.selection() else 'disabled')
        self.finish()
        self.update_language()

    def error(self,msg):
        if self.closed:return
        self._error=msg;self.finish();self.update_language()

    def finish(self):
        self.busy=False;self.refresh_button.configure(state='normal')
        if not self.closed:self.after_id=self.root.after(REFRESH_MS,self.refresh)

    def close(self):
        self.web_health.close()
        self.stop_dispatch()
        if self.after_id is not None:self.root.after_cancel(self.after_id)
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk()
    try:ttk.Style().theme_use('clam')
    except tk.TclError:pass
    Monitor(root)
    root.mainloop()

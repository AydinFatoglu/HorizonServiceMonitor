import json
import gc
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

import HorizonServiceMonitor as h
from localization import TEXT, Language


ENV = {
    'HSM_SERVICE_NAME': 'wsnm',
    'HSM_SERVICE_DISPLAY': 'VMware Horizon View Framework Component',
    'HSM_SERVICE_PATH': r'"C:\Program Files\VMware\FrameworkService.exe" -s',
    'HSM_EVENT_HOURS': '48',
}

# Run the actual production PowerShell classifier against deterministic records.
FIXTURES = r'''
function Get-CimInstance { param($ClassName) @(
 [pscustomobject]@{Name='wsnm';PathName=$env:HSM_SERVICE_PATH},
 [pscustomobject]@{Name='other';PathName='C:\Other\Other.exe'}
)}
function New-Event($id, $message, $data) {
 $ev=[pscustomobject]@{Id=$id;Message=$message;Data=$data;TimeCreated=(Get-Date);LogName='Application';Level=2;LevelDisplayName='Hata';ProviderName='Microsoft-Windows-RestartManager';RecordId=$id}
 $ev | Add-Member ScriptMethod FormatDescription {return $this.Message}
 $ev | Add-Member ScriptMethod ToXml {return '<Event><System><Provider Name="wsnm"/></System><EventData><Data>' + [Security.SecurityElement]::Escape($this.Data) + '</Data></EventData></Event>'}
 return $ev
}
function Get-WinEvent {
 param($FilterHashtable)
 $delta=$FilterHashtable.EndTime-$FilterHashtable.StartTime
 if ([math]::Abs($delta.TotalHours-48) -gt 0.001) {throw 'Incorrect time range'}
 if ($FilterHashtable.LogName -eq 'System') {return}
 New-Event 10006 "Application or service 'VMware Horizon View Framework Component' could not be shut down." ''
 New-Event 2 'Service WSNM.' ''
 New-Event 3 '' 'VMware Horizon View Framework Component'
 New-Event 4 'Faulting application FrameworkService.exe' ''
 New-Event 5 'C:\Program Files\VMware\FrameworkService.exe' ''
 New-Event 7001 'Network Location Awareness depends on Network List Service' ''
 New-Event 7 'prefixwsnmsuffix wsnm_other wsnm.exe' ''
 New-Event 8 'java.exe svchost.exe powershell.exe' ''
 New-Event 9 'unrelated provider metadata only' ''
 New-Event 10 'WSNM FrameworkService.exe' ''
 New-Event 11 '' 'wsnm'
 New-Event 12 'OtherFrameworkService.exe FrameworkService.exe.bak' ''
}
'''


class TransportTests(unittest.TestCase):
    def test_unicode_and_object_shape(self):
        result = h.run_ps("[pscustomobject]@{Value='Doğrudan / Dolaylı / İzleme'} | ConvertTo-Json -Compress")
        self.assertEqual(result, {'Value': 'Doğrudan / Dolaylı / İzleme'})

    def test_array_shapes(self):
        for payload in ('[]', '[{"Name":"wsnm"}]', '[{"Name":"a"},{"Name":"b"}]'):
            with self.subTest(payload=payload):
                self.assertEqual(h.run_ps("Write-Output '" + payload + "'"), json.loads(payload))

    def test_failures_are_visible(self):
        for script in ("throw 'test error'", "Write-Output 'broken json'", "return", "Write-Output 'null'"):
            with self.subTest(script=script), self.assertRaises(RuntimeError):
                h.run_ps(script)

    def test_timeout(self):
        with patch.object(h.subprocess, 'run', side_effect=subprocess.TimeoutExpired('powershell', 90)):
            with self.assertRaisesRegex(RuntimeError, '90 saniyede'):
                h.run_ps('', timeout=90)

    def test_clixml_progress_and_error(self):
        progress = '#< CLIXML\n<Objs><Obj S="progress"><S>Loading</S></Obj></Objs>'
        error = '#< CLIXML\n<Objs><S S="Error">Access denied_x000D__x000A_</S></Objs>'
        self.assertEqual(h.powershell_errors(progress), '')
        self.assertEqual(h.powershell_errors(error), 'Access denied')


class MatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = h.run_ps(FIXTURES + h.EVENT_PS, env=ENV)

    def test_classification_and_no_duplicates(self):
        h.validate_event_result(self.result)
        events = {e['Id']: e for e in self.result['Events']}
        self.assertEqual(set(events), {10006, 2, 3, 4, 5, 10, 11})
        for event_id in (10006, 2, 3, 10, 11):
            self.assertEqual(events[event_id]['MatchType'], 'direct')
        for event_id in (4, 5):
            self.assertEqual(events[event_id]['MatchType'], 'indirect')
        self.assertEqual(len(events), len(self.result['Events']))
        self.assertTrue(all(e['Reason'] for e in events.values()))

    def test_diagnostics(self):
        d = self.result['Diagnostics']
        self.assertEqual((d['Logs']['System']['Count'], d['Logs']['Application']['Count']), (0, 12))
        self.assertEqual((d['Total'], d['Direct'], d['Indirect'], d['ErrorCount']), (12, 5, 2, 0))
        self.assertGreaterEqual(d['Seconds'], 0)

    def test_shared_executable(self):
        prefix = FIXTURES.replace("PathName='C:\\Other\\Other.exe'", 'PathName=$env:HSM_SERVICE_PATH')
        result = h.run_ps(prefix + h.EVENT_PS, env=ENV)
        self.assertFalse(any(e['MatchType'] == 'indirect' for e in result['Events']))

    def test_same_filename_different_path_requires_full_path(self):
        prefix = FIXTURES.replace("PathName='C:\\Other\\Other.exe'", "PathName='C:\\Other\\FrameworkService.exe'")
        result = h.run_ps(prefix + h.EVENT_PS, env=ENV)
        indirect_ids = {e['Id'] for e in result['Events'] if e['MatchType'] == 'indirect'}
        self.assertEqual(indirect_ids, {5})

    def test_partial_read_failure_and_bad_xml(self):
        prefix = FIXTURES + r'''
function Get-WinEvent {
 param($FilterHashtable)
 if ($FilterHashtable.LogName -eq 'System') {throw 'Access denied'}
 $e=New-Event 15 'wsnm' ''
 $e | Add-Member -Force ScriptMethod ToXml {return 'broken XML'}
 $e
}
'''
        result = h.run_ps(prefix + h.EVENT_PS, env=ENV)
        h.validate_event_result(result)
        self.assertEqual(result['Events'][0]['MatchType'], 'direct')
        self.assertEqual(result['Diagnostics']['ErrorCount'], 2)
        self.assertIn('eksik olabilir', h.event_status(result))

    def test_real_no_matching_error_id_is_not_a_failure(self):
        prefix = FIXTURES + r'''
function Get-WinEvent {
 param($FilterHashtable)
 $exception=[Exception]::new('No events')
 $record=[System.Management.Automation.ErrorRecord]::new($exception,'NoMatchingEventsFound',[System.Management.Automation.ErrorCategory]::ObjectNotFound,$null)
 throw $record
}
'''
        result = h.run_ps(prefix + h.EVENT_PS, env=ENV)
        self.assertEqual(result['Diagnostics']['ErrorCount'], 0)
        self.assertIn('Eşleşen olay bulunamadı', h.event_status(result))

    def test_generic_host_even_full_path(self):
        env = dict(ENV, HSM_SERVICE_PATH=r'C:\Windows\System32\svchost.exe -k netsvcs')
        result = h.run_ps(FIXTURES + h.EVENT_PS, env=env)
        self.assertEqual(result['Diagnostics']['Indirect'], 0)

    def test_empty_vs_read_error(self):
        for implementation, success in (("return", True), ("throw 'Access denied'", False)):
            prefix = FIXTURES + '\nfunction Get-WinEvent {param($FilterHashtable) ' + implementation + '}\n'
            result = h.run_ps(prefix + h.EVENT_PS, env=ENV)
            h.validate_event_result(result)
            self.assertEqual(result['Events'], [])
            self.assertEqual(result['Diagnostics']['Logs']['System']['Success'], success)
            self.assertIn('Eşleşen olay bulunamadı' if success else 'Kayıtlar okunamadı', h.event_status(result))

    def test_xml_entities_userdata_and_missing_message(self):
        prefix = FIXTURES + r'''
function Get-WinEvent {
 param($FilterHashtable)
 if ($FilterHashtable.LogName -eq 'System') {return}
 $e=New-Event 14 '' ''
 $e | Add-Member -Force ScriptMethod FormatDescription {throw 'No provider resource'}
 $e | Add-Member -Force ScriptMethod ToXml {return '<Event><UserData><Item><Value>A &amp; B Service</Value></Item></UserData></Event>'}
 $e
}
'''
        result = h.run_ps(prefix + h.EVENT_PS, env=dict(ENV, HSM_SERVICE_DISPLAY='A & B Service'))
        self.assertEqual(result['Events'][0]['MatchType'], 'direct')
        self.assertEqual(result['Diagnostics']['ErrorCount'], 1)
        self.assertIn('eksik olabilir', h.event_status(result))

    def test_invalid_envelope_rejected(self):
        for result in ([], {}, {'Events': [], 'Diagnostics': {}}, {'Events': [{'MatchType': 'Doğrudan'}], 'Diagnostics': self.result['Diagnostics']}):
            with self.subTest(result=result), self.assertRaises(RuntimeError):
                h.validate_event_result(result)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root = h.tk.Tk()
        self.root.withdraw()
        self.web_probe = patch.object(h, 'check_admin_web', return_value={'kind': 'http', 'code': 200, 'seconds': .01, 'detail': ''})
        self.web_probe.start()

    def tearDown(self):
        self.root.destroy()
        self.web_probe.stop()
        # Release destroyed Tcl interpreters on their owning thread before the
        # next test starts another worker (which can otherwise trigger GC).
        gc.collect()

    def pump(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_worker_dispatch_render_and_close(self):
        result = h.run_ps(FIXTURES + h.EVENT_PS, env=ENV)
        gate = threading.Event()
        def slow_query(*args, **kwargs):
            gate.wait(3)
            return result
        with patch.object(h, 'run_ps', side_effect=slow_query):
            window = h.EventWindow(self.root, 'wsnm', 'Framework', ENV['HSM_SERVICE_PATH'])
            tick = []
            self.root.after(1, lambda: tick.append(True))
            self.pump(lambda: bool(tick))
            self.assertTrue(window.busy)
            gate.set()
            self.pump(lambda: not window.busy)
            self.assertEqual(len(window.trees['Doğrudan'].get_children()), 5)
            self.assertEqual(len(window.trees['Dolaylı'].get_children()), 2)
            window.trees['Doğrudan'].selection_set('0')
            window.show_message('Doğrudan')
            self.assertIn('Record ID:', window.message.get('1.0', 'end'))
            window.error('Deneme hatası')
            self.assertIn('Deneme hatası', window.message.get('1.0', 'end'))
            self.assertFalse(window.trees['Doğrudan'].get_children())
            window.close()
            thread = threading.Thread(target=lambda: window.safe_after(lambda: self.fail('closed')))
            thread.start()
            thread.join()

    def test_service_refresh_still_scheduled(self):
        services = [{'Name': 'wsnm', 'DisplayName': 'Framework', 'State': 'Running', 'PathName': 'framework.exe'}]
        with patch.object(h, 'run_ps', return_value=services):
            monitor = h.Monitor(self.root)
            self.pump(lambda: not monitor.busy)
            self.assertEqual(len(monitor.tree.get_children()), 1)
            self.assertEqual(h.REFRESH_MS, 30_000)
            self.assertIsNotNone(monitor.after_id)
            # close owns the root; tearDown performs the actual destroy here.
            monitor.stop_dispatch()
            self.root.after_cancel(monitor.after_id)

    def test_query_error_reaches_gui(self):
        with patch.object(h, 'run_ps', side_effect=RuntimeError('Erişim reddedildi')), patch.object(h.logging.Logger, 'exception'):
            window = h.EventWindow(self.root, 'wsnm', 'Framework', '')
            self.pump(lambda: not window.busy)
            self.assertIn('Erişim reddedildi', window.info.get())
            self.assertEqual(str(window.btn['state']), 'normal')
            self.assertIn('alınamadı', window.sections['Doğrudan']['text'])
            window.close()

    def test_live_language_updates_all_windows_without_queries(self):
        result = h.run_ps(FIXTURES + h.EVENT_PS, env=ENV)
        services = [{'Name': 'wsnm', 'DisplayName': 'Framework', 'State': 'Running', 'StartMode': 'Auto', 'PathName': 'framework.exe'}]
        with patch.object(h, 'run_ps', return_value=services) as query:
            monitor = h.Monitor(self.root)
            self.pump(lambda: not monitor.busy)
            query.return_value = result
            window = h.EventWindow(self.root, 'wsnm', 'Framework', ENV['HSM_SERVICE_PATH'])
            self.pump(lambda: not window.busy)
            about = h.AboutWindow(self.root)
            service_iid = monitor.tree.get_children()[0]
            monitor.tree.selection_set(service_iid)
            window.trees['Doğrudan'].selection_set('0')
            window.show_message('Doğrudan')
            original_event = window.events[('Doğrudan', '0')].copy()
            self.assertIn('Eşleşme:', window.message.get('1.0', 'end'))
            scheduled_refresh = monitor.after_id
            query_count = query.call_count
            monitor.language_choice.set('English')
            monitor.language_dropdown.event_generate('<<ComboboxSelected>>')
            self.root.update()
            self.assertEqual(monitor.refresh_button['text'], 'Refresh')
            self.assertEqual(monitor.tree.heading('display')['text'], 'Display Name')
            self.assertEqual(monitor.tree.set(service_iid, 'state'), 'Running')
            self.assertEqual(monitor.tree.set(service_iid, 'start'), 'Automatic')
            self.assertIn('Last checked:', monitor.info.get())
            self.assertEqual(window.sections['Doğrudan']['text'], 'Direct Events (5)')
            self.assertIn('Scanned: 12', window.info.get())
            self.assertIn('Match: Direct', window.message.get('1.0', 'end'))
            self.assertIn('Service name / display name match:', window.message.get('1.0', 'end'))
            self.assertEqual(about.win.title(), 'About Horizon Service Monitor')
            self.assertEqual(about.link_buttons['profile_link']['text'], 'GitHub Profile')
            self.assertEqual(query.call_count, query_count)
            self.assertEqual(monitor.after_id, scheduled_refresh)
            self.assertEqual(monitor.tree.selection(), (service_iid,))
            self.assertEqual(window.trees['Doğrudan'].selection(), ('0',))
            self.assertEqual(window.events[('Doğrudan', '0')], original_event)
            monitor.language.set('tr')
            self.assertEqual(monitor.tree.set(service_iid, 'state'), 'Çalışıyor')
            self.assertEqual(window.sections['Doğrudan']['text'], 'Doğrudan Event Kayıtları (5)')
            self.assertIn('Eşleşme: Doğrudan', window.message.get('1.0', 'end'))
            self.assertEqual(about.link_buttons['profile_link']['text'], 'GitHub Profili')
            about.close()
            window.close()
            # Closed windows must not receive Tcl calls on later changes.
            monitor.language.set('en')
            monitor.stop_dispatch()
            self.root.after_cancel(monitor.after_id)

    def test_language_change_while_query_is_running_and_on_error(self):
        gate = threading.Event()
        def fail_query(*args, **kwargs):
            gate.wait(3)
            raise RuntimeError('Access denied')
        with patch.object(h, 'run_ps', side_effect=fail_query), patch.object(h.logging.Logger, 'exception'):
            window = h.EventWindow(self.root, 'wsnm', 'Framework', '')
            window.language.set('en')
            self.assertTrue(window.busy)
            self.assertEqual(window.info.get(), 'Scanning Windows Event Viewer records...')
            gate.set()
            self.pump(lambda: not window.busy)
            self.assertIn('Event read error:', window.info.get())
            window.language.set('tr')
            self.assertIn('Event okuma hatası:', window.info.get())
            window.close()

    def test_about_links_open_correct_targets_only_on_click(self):
        with patch.object(h.webbrowser, 'open') as browser:
            about = h.AboutWindow(self.root)
            browser.assert_not_called()
            for key, url in (
                ('profile_link', h.GITHUB_PROFILE), ('repository_link', h.REPOSITORY_URL),
                ('issues_link', h.REPOSITORY_URL + '/issues'),
                ('license_link', h.REPOSITORY_URL + '/blob/main/LICENSE'),
            ):
                about.link_buttons[key].invoke()
                browser.assert_called_with(url)
            about.close()


class LocalizationTests(unittest.TestCase):
    def test_translation_keys_and_placeholders_match(self):
        from string import Formatter
        self.assertEqual(set(TEXT['en']), set(TEXT['tr']))
        for key in TEXT['en']:
            placeholders = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field}
            self.assertEqual(placeholders(TEXT['en'][key]), placeholders(TEXT['tr'][key]), key)

    def test_event_status_in_both_languages(self):
        result = {'Events': [], 'Diagnostics': {'Logs': {'System': {'Count': 0, 'Success': True}, 'Application': {'Count': 0, 'Success': True}}, 'Total': 0, 'Direct': 0, 'Indirect': 0, 'ErrorCount': 0, 'Seconds': 1.2}}
        self.assertIn('No matching events found.', h.event_status(result, Language('en')))
        self.assertIn('Eşleşen olay bulunamadı.', h.event_status(result, Language('tr')))


if __name__ == '__main__':
    unittest.main(verbosity=2)

import contextlib
import io
import json
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from remote_check.analyzer import analyze
from remote_check.cli import exit_code, main, sarif, scan
from remote_check.lexer import SourceError, structure, tokenize


def event(body='', parameters='player, value', connect='Connect'):
    return f'remote.OnServerEvent:{connect}(function({parameters})\n{body}\nend)'


def rules(source):
    return {(f['rule'],f['level']) for f in analyze(source)[1]}


class LexerTests(unittest.TestCase):
    def test_comments_and_strings_are_inactive(self):
        source = '''-- remote.OnServerEvent:Connect(function(p,x) require(x) end)
local a = "remote.OnServerInvoke = function(p,x) end"
--[==[ remote.OnServerEvent ]==]
local b = [=[ remote.OnServerEvent ]=]
local c = `remote.OnServerEvent`
'''
        self.assertEqual(analyze(source), ([], []))

    def test_escaped_quotes_and_z_whitespace(self):
        self.assertEqual(analyze('local s = "a\\\" remote.OnServerEvent \\z\n  b"')[0], [])

    def test_comments_preserve_crlf_positions(self):
        source = '-- first\r\n--[=[ comment\r\nmore ]=]\r\n' + event()
        handler = analyze(source)[0][0]
        self.assertEqual((handler['line'], handler['column']), (4,8))

    def test_delimiters_inside_strings_do_not_close_blocks(self):
        handlers, _ = analyze(event('local text = "end ) ] }"\nlocal x = [=[end]=]'))
        self.assertEqual(handlers[0]['endLine'],4)

    def test_unterminated_strings_and_comments(self):
        for source in ('"unfinished', '--[=[unfinished', '[==[unfinished', '`unfinished'):
            with self.subTest(source=source), self.assertRaises(SourceError):
                tokenize(source)

    def test_interpolation_reports_unsupported_code(self):
        with self.assertRaisesRegex(SourceError,'Interpolated'):
            tokenize('local s = `value {require(id)}`')

    def test_escaped_interpolation_brace_stays_literal(self):
        self.assertEqual(analyze(r'local s = `value \{literal}`'), ([],[]))

    def test_if_expression_is_not_silently_misparsed(self):
        with self.assertRaisesRegex(SourceError,'if-expression'):
            analyze(event('local x = if value then 1 else 2'))

    def test_classic_nested_blocks(self):
        source = event('for i = 1, 3 do\nwhile value do break end\nend\nrepeat value = nil until true\ndo local a=1 end\nif value then return elseif value == nil then return else return end')
        self.assertTrue(analyze(source)[0][0]['analyzed'])

    def test_unbalanced_source_is_an_error(self):
        for source in ('if x then', 'repeat x=1 end', 'end', 'local x = (]', event()[:-1]):
            with self.subTest(source=source), self.assertRaises(SourceError):
                analyze(source)

    def test_token_and_nesting_limits(self):
        with self.assertRaises(SourceError):
            tokenize('x '*11,max_tokens=10)
        with self.assertRaises(SourceError):
            structure(tokenize('('*257 + ')'*257))

    def test_numeric_tokens_do_not_swallow_property_names(self):
        self.assertEqual(len(analyze('local a=1..remote.OnServerEvent')[0]),1)

    def test_bounded_random_sources_fail_with_source_errors_only(self):
        randomizer=random.Random(1942)
        fragments=['if ', 'then ', 'else ', 'end ', 'function ', 'do ', 'repeat ', 'until ', '(', ')', '[', ']', '{', '}', '"', "'", '`', '--', '\n', 'x ', '1 ', '.OnServerEvent ', ':Connect ', '= ']
        for _ in range(500):
            source=''.join(randomizer.choice(fragments) for _ in range(30))
            try:analyze(source)
            except SourceError:pass


class AnalyzerTests(unittest.TestCase):
    def test_unchecked_callback_reports_review_hints(self):
        hints=rules(event('print(value)'))
        self.assertIn(('RMC001','warning'),hints)
        self.assertIn(('RMC002','warning'),hints)

    def test_type_annotations_are_not_runtime_validation(self):
        self.assertIn(('RMC001','warning'),rules(event('', 'player: Player, value: number')))

    def test_typeof_annotation_and_assignment_are_not_guard_evidence(self):
        for body in ('local copy: typeof(value) = value', 'local kind = typeof(value)', 'type Kind = typeof(value)'):
            with self.subTest(body=body):
                self.assertIn(('RMC001','warning'),rules(event(body)))

    def test_elseif_type_guard_is_observed(self):
        self.assertIn(('RMC001','note'),rules(event('if false then return elseif type(value) ~= "number" then return end')))

    def test_observed_calls_still_have_review_notes(self):
        hints=rules(event('if not limiter:allow(player.UserId) then return end\nif typeof(value) ~= "number" then return end'))
        self.assertEqual(hints,{('RMC001','note'),('RMC002','note')})

    def test_checks_after_side_effect_are_not_certified(self):
        handlers, findings=analyze(event('require(value)\nassert(type(value)=="number")'))
        self.assertTrue(handlers[0]['typeCalls'])
        self.assertIn('RMC004',{f['rule'] for f in findings})
        self.assertIn('do not prove',next(f['message'] for f in findings if f['rule']=='RMC001'))

    def test_no_payload_still_reviews_permissions(self):
        self.assertIn(('RMC001','note'),rules(event('', 'player')))

    def test_once_parallel_and_multiline(self):
        for connect in ('Connect','Once','ConnectParallel'):
            self.assertTrue(analyze(event('',connect=connect))[0][0]['analyzed'])
        self.assertTrue(analyze('remote\n.OnServerEvent\n:Connect(\nfunction(player, value)\nend\n)')[0][0]['analyzed'])

    def test_invoke_and_bracket_properties(self):
        source = 'r["OnServerInvoke"] = function(player, value) return value end\nr[\'OnServerEvent\']:Connect(function(player) end)'
        handlers,_=analyze(source)
        self.assertEqual([h['api'] for h in handlers],['OnServerInvoke','OnServerEvent'])
        self.assertTrue(all(h['analyzed'] for h in handlers))

    def test_named_wrapped_and_aliased_references_are_visible(self):
        for source in ('r.OnServerInvoke = handler','r.OnServerEvent:Connect(handler)','local e=r.OnServerEvent','r.OnServerEvent:Connect(wrap(function(p,x) end))'):
            handlers, findings=analyze(source)
            self.assertEqual(len(handlers),1)
            self.assertFalse(handlers[0]['analyzed'])
            self.assertEqual(findings[0]['rule'],'RMC005')

    def test_generic_callback_is_manual_review(self):
        handlers,findings=analyze('r.OnServerInvoke = function<T>(p, x: T) return x end')
        self.assertFalse(handlers[0]['analyzed'])
        self.assertEqual(findings[0]['rule'],'RMC005')

    def test_nested_helper_checks_do_not_count(self):
        source=event('local function helper(value)\nassert(typeof(value)=="number")\nlimiter:allow(1)\nend\nprint(value)')
        self.assertIn(('RMC001','warning'),rules(source))
        self.assertIn(('RMC002','warning'),rules(source))

    def test_adjacent_handlers_do_not_share_checks(self):
        source=event('assert(value)\nlimiter:allow(player.UserId)')+'\n'+event('print(value)')
        handlers,_=analyze(source)
        self.assertTrue(handlers[0]['typeCalls'])
        self.assertFalse(handlers[1]['typeCalls'])

    def test_nested_remote_handlers_are_separate(self):
        source=event(event('assert(value)\nlimiter:allow(player.UserId)'))
        handlers,_=analyze(source)
        self.assertEqual(len(handlers),2)
        self.assertFalse(handlers[0]['typeCalls'])
        self.assertTrue(handlers[1]['typeCalls'])

    def test_parameter_types_with_commas(self):
        handlers,_=analyze(event('print(value)', 'player: Player, value: { x: number, y: number }, callback: (number, string) -> ()'))
        self.assertEqual(handlers[0]['parameters'],['player','value','callback'])

    def test_broadcast_require_and_varargs(self):
        hints=rules(event('remote:FireAllClients(value)\nrequire(value)'))
        self.assertIn(('RMC003','warning'),hints)
        self.assertIn(('RMC004','warning'),hints)
        self.assertIn(('RMC003','warning'),rules(event('remote:FireAllClients(...)','player, ...')))
        self.assertIn(('RMC003','warning'),rules(event('remote:FireAllClients(...)','...')))

    def test_comments_cannot_supply_validation_evidence(self):
        self.assertIn(('RMC001','warning'),rules(event('-- assert(value)\nlocal s="typeof(value)"')))

    def test_exact_configured_helpers(self):
        source=event('Gate:take(player.UserId)')
        self.assertFalse(analyze(source)[0][0]['rateCalls'])
        self.assertTrue(analyze(source,rate_helpers=('Gate.take',))[0][0]['rateCalls'])
        self.assertFalse(analyze(event('other.limiter:allow(player.UserId)'))[0][0]['rateCalls'])

    def test_aliases_are_not_claimed_as_tracked(self):
        self.assertNotIn(('RMC004','warning'),rules(event('local alias=value\nrequire(alias)')))

    def test_receiver_class_is_not_inferred(self):
        self.assertEqual(len(analyze('r.OnServerEvent:Connect(function(p) end)')[0]),1)

    def test_unrelated_events_are_ignored(self):
        self.assertEqual(analyze('r.OnClientEvent:Connect(function(value) end)'),([],[]))


class FilesAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def write(self,name,source):
        path=self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(source,encoding='utf-8')
        return path

    def test_text_json_and_sarif_exit_codes(self):
        file=self.write('review.luau',event())
        for format in ('text','json','sarif'):
            with self.subTest(format=format),contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main([str(file),'--format',format]),1)
                if format!='text':json.loads(output.getvalue())

    def test_analysis_errors_outrank_hints(self):
        self.write('a.luau',event())
        self.write('b.luau','local s=`x {value}`')
        report=scan(self.root)
        self.assertEqual(exit_code(report),2)
        self.assertEqual(report['filesScanned'],1)

    def test_no_source_and_missing_path_are_errors(self):
        self.assertEqual(exit_code(scan(self.root)),2)
        self.assertEqual(exit_code(scan(self.root/'missing')),2)

    def test_no_remote_is_not_a_safety_verdict(self):
        report=scan(self.write('a.luau','print("hello")'))
        self.assertEqual(exit_code(report),0)
        self.assertIn('does not establish safety',report['notice'])

    def test_utf8_bom_and_invalid_bytes(self):
        self.write('a.LUA','\ufeff'+event())
        (self.root/'b.luau').write_bytes(b'\xff')
        report=scan(self.root)
        self.assertEqual(report['filesScanned'],1)
        self.assertFalse(report['scanComplete'])

    def test_size_limit(self):
        file=self.write('huge.luau','x'*1048577)
        self.assertEqual(exit_code(scan(file)),2)

    def test_file_count_total_bytes_and_traversal_limits(self):
        self.write('a.luau',event())
        self.write('b.luau',event())
        for setting,value in [('MAX_FILES',1),('MAX_TOTAL_BYTES',2),('MAX_ENTRIES',1)]:
            with self.subTest(setting=setting),patch('remote_check.cli.'+setting,value):
                self.assertEqual(exit_code(scan(self.root)),2)

    def test_excluded_directories_are_reported(self):
        self.write('a.luau','print(1)')
        self.write('node_modules/b.luau',event())
        report=scan(self.root)
        self.assertEqual(report['filesScanned'],1)
        self.assertEqual(report['skipped'][0]['reason'],'excluded directory')

    def test_symlink_is_not_followed(self):
        target=self.write('a.luau','print(1)')
        link=self.root/'linked.luau'
        try:link.symlink_to(target)
        except OSError as error:self.skipTest('Symlink creation unavailable: '+str(error))
        self.assertEqual(exit_code(scan(link)),2)
        self.assertEqual(len(scan(self.root)['skipped']),1)

    def test_io_error_is_reported(self):
        file=self.write('a.luau',event())
        with patch.object(Path,'open',side_effect=PermissionError(13,'permission denied')):
            self.assertEqual(exit_code(scan(file)),2)

    def test_inputs_are_unchanged_and_report_is_deterministic(self):
        file=self.write('a.luau',event())
        before=file.read_bytes()
        self.assertEqual(scan(self.root),scan(self.root))
        self.assertEqual(file.read_bytes(),before)

    def test_sarif_paths_and_coordinates(self):
        file=self.write('folder space/caf\u00e9.luau','-- heading\n'+event())
        report=sarif(scan(self.root))
        location=report['runs'][0]['results'][0]['locations'][0]['physicalLocation']
        self.assertEqual(location['artifactLocation']['uri'],'folder%20space/caf%C3%A9.luau')
        self.assertEqual(location['region'],{'startLine':2,'startColumn':8})

    def test_helper_option_is_validated(self):
        file=self.write('a.luau',event())
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
            main([str(file),'--rate-helper','bad(name)'])
        self.assertEqual(caught.exception.code,2)

    def test_real_cli_and_module_entrypoints(self):
        project=Path(__file__).resolve().parents[1]
        file=self.write('a.luau','print(1)')
        for command in ([sys.executable,'flash_remote_check.py'],[sys.executable,'-m','remote_check']):
            result=subprocess.run([*command,str(file),'--format','json'],cwd=project,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['filesScanned'],1)

    def test_input_is_never_executed(self):
        marker=self.root/'executed'
        file=self.write('data.luau',f'os.execute("echo dangerous > {marker}")\n'+event())
        scan(file)
        self.assertFalse(marker.exists())


if __name__=='__main__':
    unittest.main()

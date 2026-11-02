"""Read local source files and print text, JSON or SARIF review hints."""
import argparse
import json
from pathlib import Path
import re
import stat
import sys
from urllib.parse import quote

from .analyzer import DEFAULT_RATE_HELPERS, RULES, analyze
from .lexer import SourceError

MAX_FILE_BYTES = 1048576
MAX_TOTAL_BYTES = 32 * MAX_FILE_BYTES
MAX_FILES = 1000
MAX_ENTRIES = 20000
EXCLUDED = {'.git', '.venv', 'venv', 'node_modules', 'build', 'dist', '__pycache__'}
HELPER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z', re.ASCII)


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def scan(root, rate_helpers=DEFAULT_RATE_HELPERS):
    root = Path(root).absolute()
    base = root if root.is_dir() else root.parent
    report = {'schemaVersion':1,'scanComplete':True,'filesScanned':0,'bytesRead':0,'handlers':[],'findings':[],'skipped':[],
              'notice':'Review hints only. No findings does not establish safety; no source is executed or uploaded.'}

    def label(path):
        return path.relative_to(base).as_posix() if path != base else '.'

    def failure(path, message, line=1, column=1):
        report['scanComplete'] = False
        report['findings'].append({'path':label(path),'line':line,'column':column,'rule':'RMC000','level':'error','message':message})

    try:
        if linked(root):
            failure(root, 'Explicit input is a link or reparse point; choose its original path.')
            return finish(report)
    except OSError as error:
        failure(root, 'Cannot access input: ' + error.strerror if error.strerror else 'Cannot access input.')
        return finish(report)
    if not root.is_dir() and (not root.is_file() or root.suffix.lower() not in ('.lua','.luau')):
        failure(root, 'Choose a .lua/.luau file or a directory.')
        return finish(report)
    stack = [root]
    entries, candidates = 0, 0
    while stack:
        path = stack.pop()
        entries += 1
        if entries > MAX_ENTRIES:
            failure(root, 'Traversal exceeds 20000 entries. Choose a smaller directory.')
            break
        try:
            if linked(path):
                report['skipped'].append({'path':label(path),'reason':'link or reparse point'})
                continue
            if path.is_dir():
                if path != root and path.name in EXCLUDED:
                    report['skipped'].append({'path':label(path),'reason':'excluded directory'})
                    continue
                children = []
                for child in path.iterdir():
                    children.append(child)
                    if len(children) + entries + len(stack) > MAX_ENTRIES:
                        raise SourceError('Traversal exceeds 20000 entries. Choose a smaller directory.')
                stack.extend(sorted(children, key=lambda p:p.name, reverse=True))
                continue
            if path.suffix.lower() not in ('.lua','.luau'):
                continue
            if not stat.S_ISREG(path.stat().st_mode):
                failure(path, 'Source is not a regular file.')
                continue
            candidates += 1
            if candidates > MAX_FILES:
                failure(root, 'Scan exceeds 1000 source files. Choose a smaller directory.')
                break
            with path.open('rb') as stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
            report['bytesRead'] += len(raw)
            if report['bytesRead'] > MAX_TOTAL_BYTES:
                failure(root, 'Scan exceeds 32 MiB. Choose a smaller directory.')
                break
            if len(raw) > MAX_FILE_BYTES:
                failure(path, 'Source exceeds 1 MiB.')
                continue
            source = raw.decode('utf-8-sig')
            handlers, findings = analyze(source, label(path), rate_helpers)
            report['filesScanned'] += 1
            report['handlers'].extend(handlers)
            report['findings'].extend(findings)
            if len(report['findings']) > 10000:
                report['findings'] = report['findings'][:10000]
                failure(root, 'Report exceeds 10000 hints. Choose a smaller directory; remaining results were not retained.')
                break
        except SourceError as error:
            failure(path, str(error), error.line, error.column)
        except UnicodeError:
            failure(path, 'Source is not valid UTF-8.')
        except OSError as error:
            failure(path, 'Cannot read source: ' + (error.strerror or 'I/O error'))
    if not candidates and report['scanComplete']:
        failure(root, 'No .lua/.luau source files were found in this scope.')
    return finish(report)


def finish(report):
    report['findings'].sort(key=lambda f:(f['path'],f['line'],f['column'],f['rule']))
    report['handlers'].sort(key=lambda h:(h['path'],h['line'],h['column']))
    report['handlersAnalyzed'] = sum(h['analyzed'] for h in report['handlers'])
    report['referencesFound'] = len(report['handlers'])
    report['reviewCount'] = sum(f['level']=='warning' for f in report['findings'])
    report['errorCount'] = sum(f['level']=='error' for f in report['findings'])
    return report


def exit_code(report):
    return 2 if not report['scanComplete'] else 1 if report['reviewCount'] else 0


def sarif(report):
    return {
        '$schema':'https://json.schemastore.org/sarif-2.1.0.json', 'version':'2.1.0',
        'runs':[{
            'tool':{'driver':{'name':'Flash Remote Check','version':'0.1.0','informationUri':'https://github.com/flshmodels/flash-remote-check',
                            'rules':[{'id':key,'shortDescription':{'text':value}} for key,value in RULES.items()]}},
            'columnKind':'unicodeCodePoints',
            'invocations':[{'executionSuccessful':report['scanComplete']}],
            'properties':{'notice':report['notice'],'referencesFound':report['referencesFound'],'handlersAnalyzed':report['handlersAnalyzed'],'skipped':report['skipped']},
            'results':[{'ruleId':f['rule'],'level':f['level'],'message':{'text':f['message']},
                        'locations':[{'physicalLocation':{'artifactLocation':{'uri':quote(f['path'],safe='/.-_~')},
                                                        'region':{'startLine':f['line'],'startColumn':f['column']}}}]} for f in report['findings']],
        }],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',type=Path,help='source directory or .lua/.luau file')
    parser.add_argument('--format',choices=('text','json','sarif'),default='text')
    parser.add_argument('--rate-helper',action='append',default=[],metavar='NAME',help='additional exact dotted helper name; colon calls use dots here')
    args = parser.parse_args(argv)
    if len(args.rate_helper)>32 or any(len(s)>100 or not HELPER.fullmatch(s) for s in args.rate_helper):
        parser.error('Use at most 32 dotted helper names, up to 100 ASCII characters each.')
    report = scan(args.path, (*DEFAULT_RATE_HELPERS,*args.rate_helper))
    if args.format in ('json','sarif'):
        print(json.dumps(sarif(report) if args.format=='sarif' else report,ensure_ascii=True,indent=2))
    else:
        print(f"{report['filesScanned']} files scanned / {report['referencesFound']} inbound references / {report['handlersAnalyzed']} inline callbacks analyzed")
        for f in report['findings']:
            # Escape control characters in paths/messages so input cannot inject terminal lines.
            location = json.dumps(f['path'],ensure_ascii=True)[1:-1]
            message = json.dumps(f['message'],ensure_ascii=True)[1:-1]
            print(f"{location}:{f['line']}:{f['column']}: {f['level']} {f['rule']}: {message}")
        print(f"{report['reviewCount']} review hints / {report['errorCount']} analysis errors / {len(report['skipped'])} paths skipped")
        print(report['notice'])
    return exit_code(report)

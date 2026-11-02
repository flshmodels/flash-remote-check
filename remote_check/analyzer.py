"""Token-based review hints, without type inference or control-flow claims."""
from .lexer import SourceError, structure, tokenize

DEFAULT_RATE_HELPERS = ('limiter.allow', 'limiter.tryAcquire', 'rateLimiter.allow', 'rateLimiter.tryAcquire')
RULES = {
    'RMC000': 'File could not be analyzed',
    'RMC001': 'Review payload validation',
    'RMC002': 'Review per-player throttling',
    'RMC003': 'Payload name appears in a broadcast',
    'RMC004': 'Payload name appears in require',
    'RMC005': 'Inbound reference needs manual inspection',
}


def diagnostic(path, token, rule, level, message):
    return {'path': path, 'line': token.line, 'column': token.column, 'rule': rule, 'level': level, 'message': message}


def parameters(tokens, opening, pairs):
    closing = pairs[opening]
    names = []
    cursor = opening + 1
    while cursor < closing:
        token = tokens[cursor]
        if token.kind != 'word' and token.value != '...':
            raise SourceError('Unsupported callback parameter list.', token.line, token.column)
        names.append(token.value)
        cursor += 1
        while cursor < closing and tokens[cursor].value != ',':
            if tokens[cursor].value in ('(', '[', '{'):
                cursor = pairs[cursor] + 1
            else:
                cursor += 1
        cursor += 1
    return names


def own_body(tokens, start, end, pairs):
    # A nested helper's checks must not count as evidence in its enclosing handler.
    result = []
    cursor = start
    while cursor < end:
        if tokens[cursor].kind == 'word' and tokens[cursor].value == 'function':
            cursor = pairs[cursor] + 1
        else:
            result.append(cursor)
            cursor += 1
    return result


def calls(tokens, indices, pairs):
    allowed = set(indices)
    for i in indices:
        if tokens[i].kind != 'word' or i + 1 not in allowed or tokens[i + 1].value != '(':
            continue
        opening = i + 1
        if opening not in pairs or pairs[opening] not in allowed:
            continue
        parts = [tokens[i].value]
        cursor = i - 1
        while cursor - 1 in allowed and tokens[cursor].value in ('.', ':') and tokens[cursor - 1].kind == 'word':
            parts.insert(0, tokens[cursor - 1].value)
            cursor -= 2
        arguments = [tokens[j] for j in range(opening + 1, pairs[opening]) if j in allowed]
        yield i, '.'.join(parts), arguments


def analyze(source, path='<memory>', rate_helpers=DEFAULT_RATE_HELPERS):
    tokens = tokenize(source)
    pairs = structure(tokens)
    handlers, findings = [], []
    for index, token in enumerate(tokens):
        if token.value not in ('OnServerEvent', 'OnServerInvoke'):
            continue
        property_end = index
        direct = token.kind == 'word' and index > 0 and tokens[index - 1].value == '.'
        bracket = token.kind == 'string' and index > 0 and tokens[index - 1].value == '[' and index + 1 < len(tokens) and tokens[index + 1].value == ']'
        if bracket:
            property_end += 1
        if not direct and not bracket:
            continue
        tail = [t.value for t in tokens[property_end + 1:property_end + 6]]
        event = token.value == 'OnServerEvent'
        function_index = None
        if event and len(tail) >= 4 and tail[0] == ':' and tail[1] in ('Connect', 'Once', 'ConnectParallel') and tail[2] == '(' and tail[3] == 'function':
            function_index = property_end + 4
        elif not event and len(tail) >= 2 and tail[:2] == ['=', 'function']:
            function_index = property_end + 2
        entry = {'path':path,'line':token.line,'column':token.column,'api':token.value,'analyzed':False,'parameters':[], 'typeCalls':[], 'rateCalls':[]}
        handlers.append(entry)
        if len(handlers) > 2000:
            raise SourceError('File exceeds 2000 inbound API references.', token.line, token.column)
        if function_index is None:
            findings.append(diagnostic(path, token, 'RMC005', 'warning', 'Inbound API reference was not resolved to an inline callback. Inspect named callbacks, aliases and wrappers manually.'))
            continue
        opening = function_index + 1
        if opening >= len(tokens) or tokens[opening].value != '(' or function_index not in pairs:
            findings.append(diagnostic(path, token, 'RMC005', 'warning', 'Callback syntax is outside the supported inline form. Inspect it manually.'))
            continue
        names = parameters(tokens, opening, pairs)
        ending = pairs[function_index]
        if event and (ending + 1 >= len(tokens) or tokens[ending + 1].value != ')'):
            findings.append(diagnostic(path, token, 'RMC005', 'warning', 'The callback is wrapped or has trailing syntax this scanner does not resolve. Inspect it manually.'))
            continue
        # The first argument is supplied by Roblox; the remaining names are payload candidates.
        payload = set(names[1:]) | ({'...'} if '...' in names else set())
        entry.update(analyzed=True, parameters=names, endLine=tokens[ending].line)
        body = own_body(tokens, pairs[opening] + 1, ending, pairs)
        found_calls = list(calls(tokens, body, pairs))
        for call_index, name, arguments in found_calls:
            mentioned = sorted({a.value for a in arguments if a.kind == 'word' and a.value in payload} | ({'...'} if '...' in payload and any(a.value == '...' for a in arguments) else set()))
            if name in ('type', 'typeof', 'assert') and mentioned:
                entry['typeCalls'].append({'name':name,'line':tokens[call_index].line,'parameters':mentioned})
            if name in rate_helpers:
                entry['rateCalls'].append({'name':name,'line':tokens[call_index].line})
            if mentioned and name.split('.')[-1] == 'FireAllClients':
                findings.append(diagnostic(path, tokens[call_index], 'RMC003', 'warning', 'Payload name(s) ' + ', '.join(mentioned) + ' appear in broadcast arguments. Review validation, authorization and amplification.'))
            if mentioned and name == 'require':
                findings.append(diagnostic(path, tokens[call_index], 'RMC004', 'warning', 'A payload name appears in require arguments. Use a server-owned module allowlist; review this call manually.'))
        if payload and not entry['typeCalls']:
            findings.append(diagnostic(path, token, 'RMC001', 'warning', 'No direct type/typeof/assert call involving a payload name was observed. Review type, size, finite bounds and game permissions; helper checks may exist elsewhere.'))
        else:
            findings.append(diagnostic(path, token, 'RMC001', 'note', 'Review this inbound boundary for game permissions, bounds and check ordering. Observed calls and type annotations do not prove validation.'))
        if not entry['rateCalls']:
            findings.append(diagnostic(path, token, 'RMC002', 'warning', 'No configured rate-helper call was observed in this callback. Review per-player throttling; custom or wrapped limiters may exist.'))
        else:
            findings.append(diagnostic(path, token, 'RMC002', 'note', 'A configured rate-helper name was observed. Verify its implementation, player key and rejection path; the name alone proves nothing.'))
    return handlers, findings

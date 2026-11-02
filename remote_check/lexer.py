"""Small source lexer. It never evaluates the input."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


class SourceError(ValueError):
    def __init__(self, message, line=1, column=1):
        super().__init__(message)
        self.line, self.column = line, column


NUMBER = re.compile(r'(?:0[xX][0-9a-fA-F_]+(?:\.(?!\.)[0-9a-fA-F_]*)?(?:[pP][+-]?[0-9_]+)?|0[bB][01_]+|(?:\d[\d_]*(?:\.(?!\.)[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?[\d_]+)?)', re.ASCII)
OPERATORS = ('...', '..=', '::', '->', '==', '~=', '<=', '>=', '+=', '-=', '*=', '/=', '//=', '//', '%=', '^=', '..')
LONG_OPEN = re.compile(r'\[(=*)\[')


def tokenize(source, max_tokens=100000):
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    tokens = []
    index, line, column = 0, 1, 1

    def advance(end):
        nonlocal index, line, column
        piece = source[index:end]
        if '\n' in piece:
            line += piece.count('\n')
            column = len(piece.rsplit('\n', 1)[1]) + 1
        else:
            column += len(piece)
        index = end

    def long_end(start):
        match = LONG_OPEN.match(source, start)
        if not match:
            return None
        closing = ']' + match[1] + ']'
        end = source.find(closing, start + len(match[0]))
        if end < 0:
            raise SourceError('Unterminated long string or comment.', line, column)
        return end + len(closing)

    while index < len(source):
        character = source[index]
        if character.isspace():
            advance(index + 1)
            continue
        if source.startswith('--', index):
            end = long_end(index + 2)
            if end is None:
                end = source.find('\n', index)
                if end < 0:
                    end = len(source)
            advance(end)
            continue
        start_line, start_column = line, column
        if character in ('"', "'", '`'):
            quote, start = character, index
            cursor = index + 1
            interpolated = False
            while cursor < len(source) and source[cursor] != quote:
                if source[cursor] == '\\':
                    if cursor + 1 < len(source) and source[cursor + 1] == 'z':
                        cursor += 2
                        while cursor < len(source) and source[cursor].isspace():
                            cursor += 1
                    else:
                        cursor += 2
                else:
                    if quote == '`' and source[cursor] == '{':
                        interpolated = True
                    if source[cursor] == '\n' and quote != '`':
                        raise SourceError('Unescaped newline in a quoted string.', start_line, start_column)
                    cursor += 1
            if cursor >= len(source):
                raise SourceError('Unterminated quoted string.', start_line, start_column)
            if interpolated:
                raise SourceError('Interpolated backtick strings are outside this scanner\'s subset. Review this file manually.', start_line, start_column)
            tokens.append(Token('string', source[start + 1:cursor], start_line, start_column))
            advance(cursor + 1)
        elif character == '[' and (end := long_end(index)) is not None:
            tokens.append(Token('long-string', '', start_line, start_column))
            advance(end)
        elif character.isascii() and (character.isalpha() or character == '_'):
            end = index + 1
            while end < len(source) and source[end].isascii() and (source[end].isalnum() or source[end] == '_'):
                end += 1
            tokens.append(Token('word', source[index:end], start_line, start_column))
            advance(end)
        elif (match := NUMBER.match(source, index)) is not None:
            tokens.append(Token('number', match[0], start_line, start_column))
            advance(match.end())
        else:
            value = next((op for op in OPERATORS if source.startswith(op, index)), character)
            tokens.append(Token('symbol', value, start_line, start_column))
            advance(index + len(value))
        if len(tokens) > max_tokens:
            raise SourceError('Source exceeds 100000 tokens.', start_line, start_column)
    return tokens


def structure(tokens):
    """Pair delimiters and classic statement blocks; decline ambiguous syntax."""
    brackets, blocks, pairs = [], [], {}
    closers = {')': '(', ']': '[', '}': '{'}
    expression_prefixes = {'=', 'return', '(', ',', '[', 'and', 'or', '+', '-', '*', '/', '..', '::', '->'}
    for index, token in enumerate(tokens):
        value = token.value
        if token.kind in ('string', 'long-string', 'number'):
            continue
        if value in ('(', '[', '{'):
            brackets.append((value, index))
        elif value in closers:
            if not brackets or brackets[-1][0] != closers[value]:
                raise SourceError('Unbalanced delimiter.', token.line, token.column)
            _, start = brackets.pop()
            pairs[start] = index
        elif token.kind == 'word':
            if value == 'if':
                previous = tokens[index - 1] if index else None
                if previous and (previous.value in expression_prefixes or previous.value in ('then', 'else') and previous.line == token.line):
                    raise SourceError('An if-expression or ambiguous inline if is outside this scanner\'s subset. Review this file manually.', token.line, token.column)
                blocks.append(('if', index))
            elif value in ('function', 'repeat', 'for', 'while'):
                blocks.append((value, index))
            elif value == 'do':
                if blocks and blocks[-1][0] in ('for', 'while'):
                    kind, start = blocks.pop()
                    blocks.append((kind + '-body', start))
                else:
                    blocks.append(('do', index))
            elif value == 'until':
                if not blocks or blocks[-1][0] != 'repeat':
                    raise SourceError('Unbalanced repeat/until block.', token.line, token.column)
                _, start = blocks.pop()
                pairs[start] = index
            elif value == 'end':
                if not blocks or blocks[-1][0] in ('repeat', 'for', 'while'):
                    raise SourceError('Unbalanced or unsupported block.', token.line, token.column)
                _, start = blocks.pop()
                pairs[start] = index
        if len(blocks) + len(brackets) > 256:
            raise SourceError('Source nesting exceeds 256.', token.line, token.column)
    if brackets or blocks:
        _, index = (brackets or blocks)[-1]
        token = tokens[index]
        raise SourceError('Unclosed delimiter or block.', token.line, token.column)
    return pairs

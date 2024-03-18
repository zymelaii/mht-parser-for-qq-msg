from bs4.builder._htmlparser import BeautifulSoupHTMLParser, HTMLParserTreeBuilder
from bs4.dammit import EntitySubstitution
from bs4 import BeautifulSoup
from datetime import datetime
from io import TextIOWrapper
from enum import Enum
from typing import Callable
import html
import os
import re
import sys

try:
    from html.parser import HTMLParseError
except ImportError as e:
    class HTMLParseError(Exception):
        pass

class CustomHTMLParser(BeautifulSoupHTMLParser):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.ENTITIY_TO_CHARACTER = EntitySubstitution.HTML_ENTITY_TO_CHARACTER
        self.ENTITIY_TO_CHARACTER['nbsp'] = ' '
        self.ENTITIY_TO_CHARACTER['get'] = '>'

    def handle_entityref(self, name):
        if ch := self.ENTITIY_TO_CHARACTER.get(name):
            data = ch
        else:
            data = "&%s;" % name
        self.handle_data(data)

    def handle_data(self, data):
        self.soup.handle_data(data.replace('\xa0', ' '))

class CustomHTMLParseTreeBuilder(HTMLParserTreeBuilder):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def feed(self, markup):
        args, kwargs = self.parser_args
        parser = CustomHTMLParser(*args, **kwargs)
        parser.soup = self.soup
        try:
            parser.feed(markup)
            parser.close()
        except HTMLParseError as e:
            raise e
        parser.already_closed_empty_element = []

class MsgType(Enum):
    Unknown = 0
    Title = 1
    Group = 2
    Target = 3
    Date = 4
    User = 6
    System = 5

def next_msg_item(file: TextIOWrapper) -> str | None:
    body = ''
    while True:
        while (ch := file.read(1)) != '<':
            if ch == '':
                return
        tag = ''
        while (ch := file.read(1)) != '>':
            if ch == '':
                return
            tag += ch
        if tag.split(' ')[0] != 'tr':
            continue
        while True:
            for expect in '</tr>':
                ch = file.read(1)
                if ch == '':
                    return
                body += ch
                if ch != expect:
                    break
            else:
                return f'<tr>{body}'

def parse_msg_item(item: str) -> tuple[MsgType, str | dict[str, str | list[str]] | None]:
    root = BeautifulSoup(item, builder=CustomHTMLParseTreeBuilder)
    div_set = root.select('td > div')
    root.get_text()

    if len(div_set) == 0:
        type = MsgType.Date
        data = root.text.split('日期:')[1].lstrip()

    if len(div_set) == 1:
        text = div_set[0].text
        if text == '消息记录':
            type = MsgType.Title
            data = text
        elif text.startswith('消息分组:'):
            type = MsgType.Group
            data = text.split('消息分组:')[1].replace('\xa0', ' ')
        elif text.startswith('消息对象:'):
            type = MsgType.Target
            data = text.split('消息对象:')[1].replace('\xa0', ' ')
        else:
            type = MsgType.Unknown
            data = None

    if len(div_set) == 2:
        msg = []
        for tag in div_set[1]:
            if tag.name == 'b':
                tag = tag.select_one('font')
            if not tag:
                continue
            if tag.name == 'font':
                for e in tag.contents:
                    msg.append(e if isinstance(e, str) else '\n')
            elif tag.name == 'img':
                msg.append(f'[image={tag["src"]}]')

        sender = div_set[0].div.text

        if sender == '系统消息(10000)':
            # [personal]
            # 1. withdraw message
            msg = [''.join(msg)]
            type = MsgType.System
        elif sender == '系统消息(1000000)':
            # [group]
            # 1. invite person to group
            # 2. rename group
            # 3. essence message notice
            msg = [''.join(msg)]
            type = MsgType.System
        elif len(msg) == 2 and sender == '\xa0': #<! FIXME
            # window vibration
            type = MsgType.System
        elif len(msg) == 2 and sender == '':
            # receive file
            type = MsgType.System
        else:
            if sender.startswith('系统消息'):
                print(item)
                exit()
            type = MsgType.User

        data = {
            'sender': sender,
            'time': div_set[0].contents[1],
            'msg': msg,
        }

    return (type, data)

def format_timestamp(tm: str) -> str:
    time = datetime.strptime(tm, '%H:%M:%S')

    if time.hour < 6:
        time_frame = '凌晨'
    elif time.hour < 12:
        time_frame = '上午'
    elif time.hour < 18:
        time_frame = '下午'
    else:
        time_frame = '晚上'

    return f'{time_frame} {time.strftime("%I:%M")}'

def get_tm_diff_secs(tm_beg: str, tm_end: str) -> int:
    beg = datetime.strptime(tm_beg, '%H:%M:%S')
    end = datetime.strptime(tm_end, '%H:%M:%S')
    return (end - beg).seconds

def find_first_not_of(s: str, sub: str):
    for i, ch in enumerate(s):
        if ch != sub:
            return i
    return -1

"""
For private chats, the content of the message sender is the nickname of the message
sender, in which case there is no need to process its value twice; When in a group
chat, the content will follow the message sender's mailbox or account, in which case
the value of the mailbox or account is extracted and re-appended to the sender's
nickname.
"""
def format_sender(sender: str) -> str:
    sender = data['sender']
    uid = None
    if result := re.match(r'^(.+)(?:<(.*@.*)>)$', sender):
        sender = result.group(1)
        uid = result.group(2)
    elif result := re.match(r'^(.+)(?:\((\d+)\))$', sender):
        sender = result.group(1)
        uid = result.group(2)
    if uid:
        sender = f'{sender} ({uid})'
    return sender

"""
A message with four leading Spaces is treated by obsidian as an internal block
of code reference, in which case the message block may be split or other parsing
errors may occur. To prevent this, message blocks with messages that have four
leading Spaces are treated directly as code blocks.
"""
def try_into_code_block(messages: list[str]) -> str | None:
    max_indent = 0
    for msg in messages:
        pos = find_first_not_of(msg, ' ')
        if pos == -1:
            continue
        max_indent = max(max_indent, pos)
    if max_indent < 4:
        return
    should_break = True
    content = ''
    prefix = '>> ' + ' ' * 4
    for msg in messages:
        if msg.startswith('![[') and msg.endswith(']]'):
            if not content.endswith('\n'):
                content += '\n'
            content += '>> ' + msg
            should_break = True
        elif msg != '\n':
            if should_break:
                content += '>> \n'
                should_break = False
            content += prefix + msg
            continue
        should_break = False
        if len(content) > 0 and content[-1] == '\n':
            content += prefix + '\n'
        else:
            content += '\n'
    return content

def get_ulist_line_flag(s: str) -> int:
    if s.startswith('* ') or s.startswith('- '):
        return 0
    elif s == '\n':
        return 1
    else:
        return 2

def get_olist_line_flag(s: str) -> int:
    if re.match('^\d+\. ', s):
        return 0
    elif s == '\n':
        return 1
    else:
        return 2

def thrink_markdown_list_by_flags(messages: list[str], get_flag: Callable[[str], int]) -> list[str]:
    flags = list(map(get_flag, messages))
    if flags.count(0) <= 1:
        return messages
    result = []
    i = 0
    while True:
        while i < len(flags):
            i += 1
            result.append(messages[i - 1])
            if flags[i - 1] == 0:
                break
        if i == len(flags):
            break
        if i + 1 >= len(flags):
            break
        while i + 1 < len(flags) and flags[i] == 1 and flags[i + 1] == 0:
            result[-1] += '\n>> ' + messages[i + 1]
            i += 2
    while i < len(flags):
        result.append(messages[i])
        i += 1
    return result

def thrink_markdown_list(messages: list[str]) -> list[str]:
    messages = thrink_markdown_list_by_flags(messages, get_ulist_line_flag)
    messages = thrink_markdown_list_by_flags(messages, get_olist_line_flag)
    return messages

def escape_markdown_characters(text: str) -> str:
    # escape sep line '---' to raw text
    text = text.replace('---', '\\-\\-\\-')
    # escape sep line '===' to raw text
    text = text.replace('===', '\\=\\=\\=')
    ## escape '[' to raw text
    text = text.replace('[', '\\[')
    # escape '<' to raw text
    text = text.replace('<', '\\<')
    # escape '#' to raw text
    text = text.replace('#', '\\#')
    # escape '~~' to raw text
    text = text.replace('~~', '\\~\\~')
    # escape '*' to raw text
    text = text.replace('*', '\\*')
    return text

def try_parse_image_item(msg: str) -> str | None:
    # map image item to md wiki link
    if msg.startswith('[image=') and msg.endswith(']'):
        guid, _ = os.path.splitext(msg[7:-1])
        if file := guid_image_table.get(guid.upper()):
            msg = f'![[{file}]]'
        else:
            msg = f'[[{guid.upper()}|图片已失效]]'
        return msg

if __name__ != '__main__':
    exit()

if len(sys.argv) < 4:
    print(f'USAGE: python {sys.argv[0]} <path-to-html> <image-dir> <md-dir>')
    exit()

html_path, image_dir, md_dir = sys.argv[1:4]

if not os.path.isdir(image_dir):
    print(f'error: image dir is not valid')
    exit(-1)

if os.path.exists(md_dir):
    if not os.path.isdir(md_dir):
        print(f'error: {md_dir} is not a directory')
        exit(-1)
else:
    try:
        os.mkdir(md_dir)
    except:
        print(f'error: failed to create {md_dir}')
        exit(-1)

try:
    html_file: TextIOWrapper | None = open(html_path, 'r', encoding='utf-8')
except:
    print(f'error: cannot open {html_path}')
    exit(-1)

# setup mappings from guid to image file
guid_image_table = {}
for path in os.listdir(image_dir):
    file = os.path.basename(path)
    guid, _ = os.path.splitext(file)
    guid_image_table[guid.upper()] = file

date: str | None = None
md: TextIOWrapper | None = None
last_time = None

while item := next_msg_item(html_file):
    type, data = parse_msg_item(item)

    if type == MsgType.Date:
        if date:
            print(f'{date} 已导出')
        date = data
        md = open(f'{md_dir}/{date}.md', 'w', encoding='utf-8')
        last_time = None
        continue

    if not md:
        continue

    if type != MsgType.User and type != MsgType.System:
        continue

    msg_time = data['time']

    need_new_part = False
    need_new_line = False
    if not last_time:
        need_new_line = False
        need_new_part = True
    elif get_tm_diff_secs(last_time, msg_time) / 60 >= 5:
        need_new_line = True
        need_new_part = True

    last_time = msg_time

    if need_new_line:
        md.write('\n')

    if need_new_part:
        md.write(f'> [!abstract] {format_timestamp(msg_time)}\n')

    md.write('> \n')

    msgs = data['msg']

    if type == MsgType.System:
        if len(msgs) > 0:
            text = html.escape(msgs[-1])
            md.write(f'> <center><font color="gray">{text}</font></center>\n')

    if type == MsgType.User:
        sender = format_sender(data['sender'])
        md.write(f'>> [!note] {sender}\n')

        # messages is likely to be a code block
        msgs_in = list(map(lambda e: try_parse_image_item(e) or e, msgs))
        if content := try_into_code_block(msgs_in):
            md.write(content + '\n')
            continue

        content = ''
        for msg in thrink_markdown_list(msgs):
            if link := try_parse_image_item(msg):
                msg = link
            elif msg.count('\n') <= 1:
                # text message should be escaped to raw text, while multiline
                # message can be made from thrink_markdown_list, check it here
                msg = escape_markdown_characters(msg)
            if msg == '\n':
                content += '\n>> ' * 2
            else:
                content += msg
        md.write('>> ' + content + '\n')

if date:
    print(f'{date} 已导出')

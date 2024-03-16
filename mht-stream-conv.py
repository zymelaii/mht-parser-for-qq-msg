from bs4 import BeautifulSoup
from datetime import datetime
from io import TextIOWrapper
from enum import Enum
import os
import re
import sys

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
    root = BeautifulSoup(item, 'html.parser')
    div_set = root.select('td > div')

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
        if sender.startswith('系统消息(10000)'):
            type = MsgType.System
        elif len(msg) == 2 and msg[-1].endswith('发送了一个窗口抖动。'):
            type = MsgType.System
        else:
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

if __name__ != '__main__':
    exit()

if len(sys.argv) < 4:
    print(f'USAGE: python {sys.argv[0]} <path-to-html> <image-dir> <md-dir>')
    exit()

html_file, image_dir, md_dir = sys.argv[1:4]

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
    html: TextIOWrapper | None = open(html_file, 'r', encoding='utf-8')
except:
    print(f'error: cannot open {html_file}')
    exit(-1)

# setup mappings from guid to image file
guid_image_table = {}
for path in os.listdir(image_dir):
    file = os.path.basename(path)
    guid, _ = os.path.splitext(file)
    guid_image_table[guid] = file

date: str | None = None
md: TextIOWrapper | None = None
last_time = None

while item := next_msg_item(html):
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
    for i in range(len(msgs)):
        # escape list numbering to raw text
        # unscape '\xa0' to ' '
        msg = re.sub(r'(\d+)\. ', r"\1\\. ", msgs[i].replace('\xa0', ' '))
        # map image item to md wiki link
        if msg.startswith('[image=') and msg.endswith(']'):
            guid, _ = os.path.splitext(msg[7:-1])
            if file := guid_image_table.get(guid):
                msg = f'![[{file}]]'
            else:
                msg = f'[[{guid}|图片已失效]]'
        msgs[i] = msg

    if type == MsgType.User:
        md.write(f'>> [!note] {data["sender"]}\n')
        contents = []
        for msg in msgs:
            if msg == '\n':
                contents.append('\n>> \n>> ')
            else:
                contents.append(msg)
        md.write('>> ' + ''.join(contents) + '\n')

    if type == MsgType.System:
        if len(msgs) == 1:
            # withdraw message
            md.write(f'> <center><font color="gray">{msgs[0]}</font></center>\n')
        elif len(msgs) == 2:
            # window vibration
            md.write(f'> <center><font color="gray">{msgs[1]}</font></center>\n')
        else:
            # unknown system message
            continue

if date:
    print(f'{date} 已导出')

# mht-parser-for-qq-msg

PC QQ 消息记录转换，用于从 QQ 导出的 .mht 文档提取消息记录并转换为自定义格式。

repo 主要提供了 mht-extract 和 mht-stream-conv 两个工具。

[mht-extract](mht-extract.cpp) 用于从导出的 .mhr 文档提取消息记录的 html 文档及图片附件。

[mht-stream-conv.py](mht-stream-conv.py) 用于将导出数据转换为 obsidian 的 markdown 格式；若需转换为其它格式，请查看源码相关部分并自行修改。

## 构建说明

**Makefile**

```sh
make build
```

**CMake**

```sh
cmake -B build -DCMAKE_INSTALL_PREFIX=.
cmake --build build --target install
```

## 使用说明

### PC QQ 导出消息记录为 mht 文档

QQ > 主菜单 > 消息管理 > 导出消息记录 > 以 `网页格式（*.mht，不支持导入）` 格式保存。

### mht 导出 html 文档与图片附件

```sh
mht-extract <path-to-mht> -H <html-dir> -A <attachment-dir>
```

### 消息记录转换格式

```sh
python mht-stream-conv.py <path-to-html> <image-dir> <md-dir>
```

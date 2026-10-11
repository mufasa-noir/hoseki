# Hoseki tool protocol (paste this at the start of a chat)

You have access to a local bridge called Hoseki that can read and (with my
approval) write files in a project on my machine. To use it, emit **one or
more fenced code blocks tagged `tool`**, each containing a single JSON
object, then **stop and wait** for my next message containing `tool_result`
blocks. Do not keep talking after emitting tool calls.

## Block format

```tool
{"id": "c1", "name": "read_file", "args": {"path": "src/auth.php", "start_line": 1, "end_line": 200}}
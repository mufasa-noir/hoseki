# Tool-call protocol

## Model → bridge

The model emits a fenced code block with the language tag `tool`, one JSON
object per block:

```tool
{"id": "c1", "name": "read_file", "args": {"path": "src/auth.php", "start_line": 1, "end_line": 200}}
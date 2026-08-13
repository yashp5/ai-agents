"""Module 02 — The Agent Loop.

An agent from scratch in ~120 lines: an LLM, four tools, and a while-loop.
It gets ONE task and figures out the steps itself.

Run from the repo root:  uv run modules/02-the-agent-loop/example.py
"""

import ast
import json
import operator
from pathlib import Path

from anthropic import Anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
MAX_ITERATIONS = 15  # guardrail #1: never let the loop run unbounded
WORKSPACE = Path(__file__).parent / "workspace"
client = Anthropic()

# --------------------------- tool implementations ---------------------------


def _safe_path(rel_path: str) -> Path:
    """Guardrail #2: confine all file access to the workspace directory.

    Tool arguments are model-generated, i.e. untrusted input — never pass
    them straight to the filesystem.
    """
    p = (WORKSPACE / rel_path).resolve()
    if not p.is_relative_to(WORKSPACE.resolve()):
        raise ValueError(f"Path escapes the workspace: {rel_path}")
    return p


def list_files() -> str:
    files = [str(p.relative_to(WORKSPACE)) for p in sorted(WORKSPACE.rglob("*")) if p.is_file()]
    return "\n".join(files) or "(workspace is empty)"


def read_file(path: str) -> str:
    return _safe_path(path).read_text()


def write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Wrote {len(content)} characters to {path}"


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def calculate(expression: str) -> str:
    """Arithmetic only, evaluated via the AST — never eval() model output."""

    def ev(node):
        match node:
            case ast.Expression():
                return ev(node.body)
            case ast.Constant() if isinstance(node.value, (int, float)):
                return node.value
            case ast.BinOp() if type(node.op) in _OPS:
                return _OPS[type(node.op)](ev(node.left), ev(node.right))
            case ast.UnaryOp() if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            case _:
                raise ValueError("Only +, -, *, / arithmetic is allowed")

    return str(ev(ast.parse(expression, mode="eval")))


TOOL_FUNCTIONS = {"list_files": list_files, "read_file": read_file, "write_file": write_file, "calculate": calculate}

# ----------------------------- tool definitions -----------------------------

TOOLS: list[ToolParam] = [
    {
        "name": "list_files",
        "description": "List all files in the workspace. Use this first to see what exists.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_file",
        "description": "Read a file from the workspace by relative path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the workspace (relative path). Creates parent dirs.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate an arithmetic expression, e.g. '412.5 + 398.75'. Use this instead of doing math in your head.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
]

SYSTEM = (
    "You are a careful finance assistant operating on a file workspace. "
    "Work step by step with your tools, verify numbers with the calculate tool, "
    "and when the task is complete, stop and summarize what you did."
)

TASK = (
    "Analyze the expense files in the workspace. For each month, compute total spend "
    "and spend by category, check them against the rules in notes.txt, and write a "
    "short markdown report to output/report.md. Then tell me the single biggest "
    "cost-saving opportunity."
)

# -------------------------------- THE LOOP ----------------------------------


def run_agent(task: str) -> None:
    messages: list[MessageParam] = [{"role": "user", "content": task}]
    print(f"TASK: {task}\n")

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM, tools=TOOLS, messages=messages
        )

        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"\n[{iteration}] agent: {block.text}")

        if response.stop_reason != "tool_use":
            print(f"\n--- done after {iteration} iterations ---")
            return

        messages.append({"role": "assistant", "content": response.content})

        tool_results: list[ToolResultBlockParam] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            args = json.dumps(block.input)
            print(f"[{iteration}] tool : {block.name}({args[:80]}{'...' if len(args) > 80 else ''})")
            result: ToolResultBlockParam
            try:
                output = TOOL_FUNCTIONS[block.name](**block.input)
                result = {"type": "tool_result", "tool_use_id": block.id, "content": output}
            except Exception as e:
                # Errors go back to the model as results — it sees the failure
                # and corrects course. This is how agents "self-heal".
                print(f"[{iteration}]        ERROR: {e}")
                result = {"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True}
            tool_results.append(result)

        messages.append({"role": "user", "content": tool_results})

    print(f"\n--- stopped: hit MAX_ITERATIONS ({MAX_ITERATIONS}) ---")


if __name__ == "__main__":
    run_agent(TASK)
    report = WORKSPACE / "output" / "report.md"
    if report.exists():
        print(f"\n===== {report.relative_to(WORKSPACE.parent)} =====\n{report.read_text()}")

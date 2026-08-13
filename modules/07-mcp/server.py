"""Module 07 — a real MCP server, from scratch, in one file.

Speaks the actual Model Context Protocol: JSON-RPC 2.0 messages, one per line,
over stdin/stdout. No SDK — so you can see that the "protocol" is a handful of
method names.

  initialize        handshake: versions + capabilities
  tools/list        "here are the tools I offer" (this is DISCOVERY)
  tools/call        "run this one with these arguments"
  resources/list    "here is context you can read" (not a tool — data)
  resources/read    "give me that document"

Normally you never run this yourself — an MCP CLIENT (Claude Desktop, Claude
Code, an IDE, or example.py next door) launches it as a subprocess.
"""

import json
import sys

PROTOCOL_VERSION = "2025-06-18"

# --------------------------------------------------------------------------
# The "company systems" this server exposes. In reality: the claims DB, the
# policy admin system, the payments API — whatever this team owns.
# --------------------------------------------------------------------------

POLICIES = {
    "HP-40122-B": {"holder": "Raj Mehta", "status": "active", "deductible_usd": 500,
                   "coverage": "homeowners standard", "since": "2019-04-01"},
    "HP-88913-C": {"holder": "Ana Duarte", "status": "lapsed", "deductible_usd": 1000,
                   "coverage": "homeowners standard", "since": "2021-09-15"},
}

CLAIMS: dict[str, dict] = {
    "CLM-2214": {"policy_number": "HP-40122-B", "peril": "water_damage",
                 "amount_usd": 2700, "status": "open"},
}

HANDBOOK = """\
HomeShield Claims Handbook (excerpt)
- Report losses within 60 days of discovery; later reports may be denied.
- Claims under $3,000 may be settled by any licensed adjuster.
- A $500 deductible applies once per claim, not per damaged item.
- Lapsed policies cannot have new claims opened against them.
"""

# --------------------------------------------------------------------------
# Tool definitions. Note "inputSchema" (camelCase) — MCP's spelling of the
# same JSON Schema you wrote by hand in module 01.
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "look_up_policy",
        "description": "Look up a HomeShield policy by number. Returns holder, "
                       "status, deductible, and coverage type.",
        "inputSchema": {
            "type": "object",
            "properties": {"policy_number": {"type": "string",
                                             "description": "e.g. 'HP-40122-B'"}},
            "required": ["policy_number"],
        },
    },
    {
        "name": "open_claim",
        "description": "Open a new claim against an ACTIVE policy. Always look "
                       "the policy up first — claims on lapsed policies are rejected.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "policy_number": {"type": "string"},
                "peril": {"type": "string",
                          "enum": ["water_damage", "fire", "theft", "other"]},
                "amount_usd": {"type": "number"},
            },
            "required": ["policy_number", "peril", "amount_usd"],
        },
    },
    {
        "name": "list_claims",
        "description": "List all claims on file, with status and amount.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

RESOURCES = [
    {
        "uri": "homeshield://handbook",
        "name": "Claims handbook",
        "description": "Internal process rules for adjusters.",
        "mimeType": "text/plain",
    },
]


def call_tool(name: str, args: dict) -> str:
    """The actual work. Same plain Python as module 01 — the protocol is
    only the delivery mechanism."""
    if name == "look_up_policy":
        policy = POLICIES.get(args["policy_number"].upper())
        return json.dumps(policy) if policy else f"No policy {args['policy_number']}"

    if name == "open_claim":
        policy = POLICIES.get(args["policy_number"].upper())
        if not policy:
            raise ValueError(f"Unknown policy {args['policy_number']}")
        if policy["status"] != "active":
            # Guardrail lives in the SERVER: the model cannot talk its way past it.
            raise ValueError(f"Policy {args['policy_number']} is {policy['status']} "
                             "— cannot open a claim")
        claim_id = f"CLM-{2215 + len(CLAIMS) - 1}"
        CLAIMS[claim_id] = {"policy_number": args["policy_number"].upper(),
                            "peril": args["peril"], "amount_usd": args["amount_usd"],
                            "status": "open"}
        return json.dumps({"claim_id": claim_id, **CLAIMS[claim_id]})

    if name == "list_claims":
        return json.dumps(CLAIMS)

    raise ValueError(f"Unknown tool: {name}")


# --------------------------------------------------------------------------
# The JSON-RPC loop: read a line, answer it, repeat.
# --------------------------------------------------------------------------


def handle(request: dict) -> dict | None:
    method, params = request.get("method"), request.get("params", {})

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "homeshield-claims", "version": "0.1.0"},
        }
    elif method == "notifications/initialized":
        return None  # notifications have no id and get no reply
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            output = call_tool(params["name"], params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": output}]}
        except Exception as e:
            # Tool errors are RESULTS, not protocol errors: the model sees them
            # and can correct course (module 02's self-healing, over the wire).
            result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
    elif method == "resources/list":
        result = {"resources": RESOURCES}
    elif method == "resources/read":
        result = {"contents": [{"uri": params["uri"], "mimeType": "text/plain",
                                "text": HANDBOOK}]}
    else:
        return {"jsonrpc": "2.0", "id": request.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {method}"}}

    return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle(json.loads(line))
        if response is not None:
            print(json.dumps(response), flush=True)  # flush: the client is waiting


if __name__ == "__main__":
    main()

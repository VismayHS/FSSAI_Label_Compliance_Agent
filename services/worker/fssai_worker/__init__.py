"""Worker (owner: Vismay): executes label-check runs off the queue (A4, A7).

jobs      execute_run(): one run, from payload to saved RunStatus
dispatch  how the API hands a run over: an RQ queue on Redis, or inline for local development
__main__  `python -m fssai_worker`: the RQ worker process with its /metrics port
"""

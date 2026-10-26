"""Dev-only: DevLLMClient plus a User-Agent header.

Groq sits behind Cloudflare, which answers urllib's default User-Agent with 403 (error 1010).
Temporary until Vismay's gateway (or dev_llm.py) sends its own User-Agent.
"""
import urllib.request

from fssai_contracts.dev_llm import DevLLMClient


class UADevLLMClient(DevLLMClient):
    def __init__(self) -> None:
        super().__init__()
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "fssai-agent/0.1")]
        urllib.request.install_opener(opener)
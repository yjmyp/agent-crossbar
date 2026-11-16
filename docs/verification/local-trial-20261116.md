# Trial report (20261116-011028)

- Verdict: **PASS**
- Total time: 149 seconds
- Tester: (fill in your name or handle)
- Machine: (fill in CPU / RAM / Windows edition)

## environment
- OS: Microsoft Windows 11 家庭版 中文版 10.0.26200
- PowerShell: 5.1.26100.7705
- Python on PATH: C:\Users\29947\AppData\Local\Programs\Python\Python310\python.exe
- Working copy: C:\Users\29947\AppData\Local\Temp\crossbar-trial-20261116-011028
## install into a fresh virtual environment
- OK   python -m venv (26004 ms)
- OK   pip install wheel (108200 ms)
```text
Processing .\build\wheels\agent_crossbar-0.1.0-py3-none-any.whl
Collecting aiosqlite>=0.20.0 (from agent-crossbar==0.1.0)
  Using cached aiosqlite-0.22.1-py3-none-any.whl.metadata (4.3 kB)
Collecting fastapi>=0.115.0 (from agent-crossbar==0.1.0)
  Using cached fastapi-0.162.5-py3-none-any.whl.metadata (27 kB)
Collecting httpx>=0.28.0 (from agent-crossbar==0.1.0)
  Using cached httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
Collecting jsonschema>=4.23.0 (from agent-crossbar==0.1.0)
  Using cached jsonschema-4.26.0-py3-none-any.whl.metadata (7.6 kB)
Collecting langgraph<2,>=1.0 (from agent-crossbar==0.1.0)
  Using cached langgraph-1.2.22-py3-none-any.whl.metadata (4.9 kB)
Collecting mcp<3,>=2.3.0 (from agent-crossbar==0.1.0)
  Using cached mcp-2.3.0-py3-none-any.whl.metadata (6.6 kB)
Collecting pydantic>=2.10.0 (from agent-crossbar==0.1.0)
  Using cached pydantic-2.14.3-py3-none-any.whl.metadata (141 kB)
Collecting uvicorn>=0.32.0 (from uvicorn[standard]>=0.32.0->agent-crossbar==0.1.0)
  Using cached uvicorn-0.54.0-py3-none-any.whl.metadata (6.6 kB)
Collecting langchain-core<2,>=1.4.7 (from langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached langchain_core-1.7.7-py3-none-any.whl.metadata (4.8 kB)
Collecting langgraph-checkpoint<5.0.0,>=4.3.0 (from langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached langgraph_checkpoint-4.3.2-py3-none-any.whl.metadata (6.7 kB)
Collecting langgraph-prebuilt<1.2.0,>=1.1.0 (from langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached langgraph_prebuilt-1.1.2-py3-none-any.whl.metadata (6.9 kB)
Collecting langgraph-sdk<0.5.0,>=0.4.6 (from langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached langgraph_sdk-0.4.14-py3-none-any.whl.metadata (5.1 kB)
Collecting xxhash>=3.5.0 (from langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached xxhash-4.1.0-cp310-cp310-win_amd64.whl.metadata (19 kB)
Collecting certifi>=2026.10.19 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached certifi-2026.10.23-py3-none-any.whl.metadata (2.5 kB)
Collecting jsonpatch>=1.33.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached jsonpatch-1.46-py3-none-any.whl.metadata (4.7 kB)
Collecting langchain-protocol>=0.0.20 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached langchain_protocol-0.0.21-py3-none-any.whl.metadata (2.4 kB)
Collecting langsmith<1.0.0,>=0.14.9 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached langsmith-0.14.17-py3-none-any.whl.metadata (39 kB)
Collecting packaging>=23.2.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached packaging-26.3-py3-none-any.whl.metadata (3.5 kB)
Collecting pyyaml>=5.3.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached pyyaml-6.0.3-cp310-cp310-win_amd64.whl.metadata (2.4 kB)
Collecting tenacity!=8.4.0,>=8.1.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached tenacity-9.2.1-py3-none-any.whl.metadata (1.4 kB)
Collecting typing-extensions>=4.7.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Collecting uuid-utils>=0.12.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached uuid_utils-1.2.0-cp310-abi3-win_amd64.whl.metadata (6.5 kB)
Collecting ormsgpack>=1.12.0 (from langgraph-checkpoint<5.0.0,>=4.3.0->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached ormsgpack-1.12.2-cp310-cp310-win_amd64.whl.metadata (3.3 kB)
Collecting orjson>=3.11.5 (from langgraph-sdk<0.5.0,>=0.4.6->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached orjson-3.13.0-cp310-cp310-win_amd64.whl.metadata (43 kB)
Collecting websockets>=14 (from langgraph-sdk<0.5.0,>=0.4.6->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached websockets-16.1.1-cp310-cp310-win_amd64.whl.metadata (7.0 kB)
Collecting anyio<5,>=3.5.0 (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached anyio-4.16.0-py3-none-any.whl.metadata (4.7 kB)
Collecting distro<2,>=1.7.0 (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
Collecting httpx2<3,>=2 (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached httpx2-2.14.0-py3-none-any.whl.metadata (10 kB)
Collecting requests-toolbelt>=1.0.0 (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached requests_toolbelt-1.0.0-py2.py3-none-any.whl.metadata (14 kB)
Collecting requests>=2.0.0 (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached requests-2.34.2-py3-none-any.whl.metadata (4.8 kB)
Collecting sniffio (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
Collecting uuid-utils>=0.12.0 (from langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached uuid_utils-0.19.0-cp310-abi3-win_amd64.whl.metadata (6.5 kB)
Collecting zstandard>=0.23.0 (from langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached zstandard-0.25.0-cp310-cp310-win_amd64.whl.metadata (3.3 kB)
Collecting exceptiongroup>=1.0.2 (from anyio<5,>=3.5.0->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached exceptiongroup-1.3.1-py3-none-any.whl.metadata (6.7 kB)
Collecting idna>=2.8 (from anyio<5,>=3.5.0->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached idna-3.20-py3-none-any.whl.metadata (7.2 kB)
Collecting httpcore2==2.14.0 (from httpx2<3,>=2->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached httpcore2-2.14.0-py3-none-any.whl.metadata (27 kB)
Collecting truststore>=0.10 (from httpx2<3,>=2->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached truststore-0.10.5-py3-none-any.whl.metadata (4.5 kB)
Collecting h11>=0.16 (from httpcore2==2.14.0->httpx2<3,>=2->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
Collecting mcp-types==2.3.0 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached mcp_types-2.3.0-py3-none-any.whl.metadata (1.9 kB)
Collecting opentelemetry-api>=1.28.0 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached opentelemetry_api-1.45.2-py3-none-any.whl.metadata (1.4 kB)
Collecting pyjwt>=2.10.1 (from pyjwt[crypto]>=2.10.1->mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached pyjwt-2.15.1-py3-none-any.whl.metadata (3.5 kB)
Collecting python-multipart>=0.0.9 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached python_multipart-0.0.32-py3-none-any.whl.metadata (2.1 kB)
Collecting pywin32>=311 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached pywin32-312-cp310-cp310-win_amd64.whl.metadata (11 kB)
Collecting sse-starlette>=3.0.0 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached sse_starlette-3.5.1-py3-none-any.whl.metadata (15 kB)
Collecting starlette>=0.27 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached starlette-1.7.0-py3-none-any.whl.metadata (6.6 kB)
Collecting typing-inspection>=0.4.1 (from mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached typing_inspection-0.4.5-py3-none-any.whl.metadata (2.6 kB)
Collecting annotated-types>=0.6.0 (from pydantic>=2.10.0->agent-crossbar==0.1.0)
  Using cached annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
Collecting pydantic-core==2.50.4 (from pydantic>=2.10.0->agent-crossbar==0.1.0)
  Using cached pydantic_core-2.50.4-cp310-cp310-win_amd64.whl.metadata (6.7 kB)
Collecting annotated-doc>=0.0.2 (from fastapi>=0.115.0->agent-crossbar==0.1.0)
  Using cached annotated_doc-0.0.6-py3-none-any.whl.metadata (6.5 kB)
Collecting httpcore==1.* (from httpx>=0.28.0->agent-crossbar==0.1.0)
  Using cached httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
Collecting jsonpointer>=3.8 (from jsonpatch>=1.33.0->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached jsonpointer-3.12-py3-none-any.whl.metadata (2.7 kB)
Collecting attrs>=22.2.0 (from jsonschema>=4.23.0->agent-crossbar==0.1.0)
  Using cached attrs-26.1.0-py3-none-any.whl.metadata (8.8 kB)
Collecting jsonschema-specifications>=2023.03.6 (from jsonschema>=4.23.0->agent-crossbar==0.1.0)
  Using cached jsonschema_specifications-2025.9.1-py3-none-any.whl.metadata (2.9 kB)
Collecting referencing>=0.28.4 (from jsonschema>=4.23.0->agent-crossbar==0.1.0)
  Using cached referencing-0.37.0-py3-none-any.whl.metadata (2.8 kB)
Collecting rpds-py>=0.25.0 (from jsonschema>=4.23.0->agent-crossbar==0.1.0)
  Using cached rpds_py-0.30.0-cp310-cp310-win_amd64.whl.metadata (4.2 kB)
Collecting cryptography>=3.4.0 (from pyjwt[crypto]>=2.10.1->mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached cryptography-50.0.2-cp39-abi3-win_amd64.whl.metadata (4.4 kB)
Collecting cffi>=2.0.0 (from cryptography>=3.4.0->pyjwt[crypto]>=2.10.1->mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached cffi-2.1.1-cp310-cp310-win_amd64.whl.metadata (2.6 kB)
Collecting pycparser (from cffi>=2.0.0->cryptography>=3.4.0->pyjwt[crypto]>=2.10.1->mcp<3,>=2.3.0->agent-crossbar==0.1.0)
  Using cached pycparser-3.11-py3-none-any.whl.metadata (8.2 kB)
Collecting charset_normalizer<4,>=2 (from requests>=2.0.0->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached charset_normalizer-3.5.2-cp310-cp310-win_amd64.whl.metadata (47 kB)
Collecting urllib3<3,>=1.26 (from requests>=2.0.0->langsmith<1.0.0,>=0.14.9->langchain-core<2,>=1.4.7->langgraph<2,>=1.0->agent-crossbar==0.1.0)
  Using cached urllib3-2.8.0-py3-none-any.whl.metadata (7.4 kB)
Collecting click>=7.0 (from uvicorn>=0.32.0->uvicorn[standard]>=0.32.0->agent-crossbar==0.1.0)
  Using cached click-8.5.1-py3-none-any.whl.metadata (2.6 kB)
Collecting httptools>=0.8.0 (from uvicorn[standard]>=0.32.0->agent-crossbar==0.1.0)
  Using cached httptools-0.9.0-cp310-cp310-win_amd64.whl.metadata (3.7 kB)
Collecting python-dotenv>=0.13 (from uvicorn[standard]>=0.32.0->agent-crossbar==0.1.0)
  Using cached python_dotenv-1.2.4-py3-none-any.whl.metadata (29 kB)
Collecting watchfiles>=0.20 (from uvicorn[standard]>=0.32.0->agent-crossbar==0.1.0)
  Using cached watchfiles-1.3.0-cp310-abi3-win_amd64.whl.metadata (5.0 kB)
Using cached langgraph-1.2.22-py3-none-any.whl (264 kB)
Using cached langchain_core-1.7.7-py3-none-any.whl (580 kB)
Using cached langgraph_checkpoint-4.3.2-py3-none-any.whl (58 kB)
Using cached langgraph_prebuilt-1.1.2-py3-none-any.whl (42 kB)
Using cached langgraph_sdk-0.4.14-py3-none-any.whl (171 kB)
Using cached langsmith-0.14.17-py3-none-any.whl (940 kB)
Using cached anyio-4.16.0-py3-none-any.whl (134 kB)
Using cached distro-1.9.0-py3-none-any.whl (20 kB)
Using cached httpx2-2.14.0-py3-none-any.whl (96 kB)
Using cached httpcore2-2.14.0-py3-none-any.whl (84 kB)
Using cached mcp-2.3.0-py3-none-any.whl (368 kB)
Using cached mcp_types-2.3.0-py3-none-any.whl (69 kB)
Using cached pydantic-2.14.3-py3-none-any.whl (494 kB)
Using cached pydantic_core-2.50.4-cp310-cp310-win_amd64.whl (2.3 MB)
Using cached typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Using cached uuid_utils-0.19.0-cp310-abi3-win_amd64.whl (182 kB)
Using cached aiosqlite-0.22.1-py3-none-any.whl (17 kB)
Using cached annotated_types-0.8.0-py3-none-any.whl (13 kB)
Using cached certifi-2026.10.23-py3-none-any.whl (135 kB)
Using cached exceptiongroup-1.3.1-py3-none-any.whl (16 kB)
Using cached fastapi-0.162.5-py3-none-any.whl (151 kB)
Using cached annotated_doc-0.0.6-py3-none-any.whl (5.3 kB)
Using cached h11-0.16.0-py3-none-any.whl (37 kB)
Using cached httpx-0.28.1-py3-none-any.whl (73 kB)
Using cached httpcore-1.0.9-py3-none-any.whl (78 kB)
Using cached idna-3.20-py3-none-any.whl (69 kB)
Using cached jsonpatch-1.46-py3-none-any.whl (25 kB)
Using cached jsonpointer-3.12-py3-none-any.whl (10 kB)
Using cached jsonschema-4.26.0-py3-none-any.whl (90 kB)
Using cached attrs-26.1.0-py3-none-any.whl (67 kB)
Using cached jsonschema_specifications-2025.9.1-py3-none-any.whl (18 kB)
Using cached langchain_protocol-0.0.21-py3-none-any.whl (7.4 kB)
Using cached opentelemetry_api-1.45.2-py3-none-any.whl (60 kB)
Using cached orjson-3.13.0-cp310-cp310-win_amd64.whl (121 kB)
Using cached ormsgpack-1.12.2-cp310-cp310-win_amd64.whl (117 kB)
Using cached packaging-26.3-py3-none-any.whl (129 kB)
Using cached pyjwt-2.15.1-py3-none-any.whl (33 kB)
Using cached cryptography-50.0.2-cp39-abi3-win_amd64.whl (3.9 MB)
Using cached cffi-2.1.1-cp310-cp310-win_amd64.whl (185 kB)
Using cached python_multipart-0.0.32-py3-none-any.whl (30 kB)
Using cached pywin32-312-cp310-cp310-win_amd64.whl (6.9 MB)
Using cached pyyaml-6.0.3-cp310-cp310-win_amd64.whl (158 kB)
Using cached referencing-0.37.0-py3-none-any.whl (26 kB)
Using cached requests-2.34.2-py3-none-any.whl (73 kB)
Using cached charset_normalizer-3.5.2-cp310-cp310-win_amd64.whl (215 kB)
Using cached urllib3-2.8.0-py3-none-any.whl (135 kB)
Using cached requests_toolbelt-1.0.0-py2.py3-none-any.whl (54 kB)
Using cached rpds_py-0.30.0-cp310-cp310-win_amd64.whl (235 kB)
Using cached sse_starlette-3.5.1-py3-none-any.whl (17 kB)
Using cached starlette-1.7.0-py3-none-any.whl (78 kB)
Using cached tenacity-9.2.1-py3-none-any.whl (32 kB)
Using cached truststore-0.10.5-py3-none-any.whl (19 kB)
Using cached typing_inspection-0.4.5-py3-none-any.whl (14 kB)
Using cached uvicorn-0.54.0-py3-none-any.whl (87 kB)
Using cached click-8.5.1-py3-none-any.whl (126 kB)
Using cached httptools-0.9.0-cp310-cp310-win_amd64.whl (92 kB)
Using cached python_dotenv-1.2.4-py3-none-any.whl (23 kB)
Using cached watchfiles-1.3.0-cp310-abi3-win_amd64.whl (290 kB)
Using cached websockets-16.1.1-cp310-cp310-win_amd64.whl (180 kB)
Using cached xxhash-4.1.0-cp310-cp310-win_amd64.whl (48 kB)
Using cached zstandard-0.25.0-cp310-cp310-win_amd64.whl (506 kB)
Using cached pycparser-3.11-py3-none-any.whl (51 kB)
Using cached sniffio-1.3.1-py3-none-any.whl (10 kB)
Installing collected packages: zstandard, xxhash, websockets, uuid-utils, urllib3, typing-extensions, truststore, tenacity, sniffio, rpds-py, pyyaml, pywin32, python-multipart, python-dotenv, pycparser, packaging, ormsgpack, orjson, jsonpointer, idna, httptools, h11, distro, click, charset_normalizer, certifi, attrs, annotated-types, annotated-doc, aiosqlite, uvicorn, typing-inspection, requests, referencing, pyjwt, pydantic-core, opentelemetry-api, langchain-protocol, jsonpatch, httpcore2, httpcore, exceptiongroup, cffi, requests-toolbelt, pydantic, jsonschema-specifications, cryptography, anyio, watchfiles, starlette, mcp-types, jsonschema, httpx2, httpx, sse-starlette, langsmith, fastapi, mcp, langchain-core, langgraph-sdk, langgraph-checkpoint, langgraph-prebuilt, langgraph, agent-crossbar

Successfully installed agent-crossbar-0.1.0 aiosqlite-0.22.1 annotated-doc-0.0.6 annotated-types-0.8.0 anyio-4.16.0 attrs-26.1.0 certifi-2026.10.23 cffi-2.1.1 charset_normalizer-3.5.2 click-8.5.1 cryptography-50.0.2 distro-1.9.0 exceptiongroup-1.3.1 fastapi-0.162.5 h11-0.16.0 httpcore-1.0.9 httpcore2-2.14.0 httptools-0.9.0 httpx-0.28.1 httpx2-2.14.0 idna-3.20 jsonpatch-1.46 jsonpointer-3.12 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 langchain-core-1.7.7 langchain-protocol-0.0.21 langgraph-1.2.22 langgraph-checkpoint-4.3.2 langgraph-prebuilt-1.1.2 langgraph-sdk-0.4.14 langsmith-0.14.17 mcp-2.3.0 mcp-types-2.3.0 opentelemetry-api-1.45.2 orjson-3.13.0 ormsgpack-1.12.2 packaging-26.3 pycparser-3.11 pydantic-2.14.3 pydantic-core-2.50.4 pyjwt-2.15.1 python-dotenv-1.2.4 python-multipart-0.0.32 pywin32-312 pyyaml-6.0.3 referencing-0.37.0 requests-2.34.2 requests-toolbelt-1.0.0 rpds-py-0.30.0 sniffio-1.3.1 sse-starlette-3.5.1 starlette-1.7.0 tenacity-9.2.1 truststore-0.10.5 typing-extensions-4.16.0 typing-inspection-0.4.5 urllib3-2.8.0 uuid-utils-0.19.0 uvicorn-0.54.0 watchfiles-1.3.0 websockets-16.1.1 xxhash-4.1.0 zstandard-0.25.0
```
- OK   crossbar-security --help (2471 ms)
```text
usage: crossbar-security [-h] [--root ROOT] [--base BASE] [--staged]
                         [--format {terminal,json,markdown,md,sarif}]
                         [--output OUTPUT] [--policy POLICY] [--lang {zh,en}]
                         [--fail-on {never,blocked}] [--include-ignored]
                         [--secrets-only] [--include-generated]
                         [--external-sarif EXTERNAL_SARIF]

Local deterministic security gate for agent-generated code.

options:
  -h, --help            show this help message and exit
  --root ROOT           repository or directory to scan
  --base BASE           scan only lines changed against this git ref (default:
                        full scan)
  --staged              diff the git index
  --format {terminal,json,markdown,md,sarif}
  --output OUTPUT, -o OUTPUT
  --policy POLICY
  --lang {zh,en}        localise finding titles and remediation in
                        terminal/markdown output
  --fail-on {never,blocked}
                        exit non-zero when the gate is blocked
  --include-ignored     also scan paths excluded by default ignore rules; VCS
                        and dependency dirs stay skipped
  --secrets-only        run only secret-detection rules (intended for whole-
                        repository secret sweeps)
  --include-generated   with --include-ignored, also traverse build/cache
                        directories (can be very slow)
  --external-sarif EXTERNAL_SARIF
                        merge findings from an external SARIF 2.1.0 file
                        (repeatable)
```
## run the gate against a deliberately unsafe sample
- OK   crossbar-security on unsafe sample (expected exit 1) (1517 ms)
## run the 10 minute demo
- OK   demo (9961 ms)
```text
[demo] run created: run_2df4f3cf85a14be2bf5de500d48db82b
[demo] run status: completed
[demo] verdict: block - 阻断交付：存在未豁免的高风险问题或行为预算超限。
[demo] findings: 1 total, 1 blocking
  - critical CS-PY-003 deploy.py:6 以 shell=True 调用子进程
[demo] behaviour: 运行正常结束=pass, Token 预算=pass, 时长预算=pass, 工具调用预算=pass, 安全扫描不外发源码=pass
[demo] wrote C:\Users\29947\Documents\Codex\agent-crossbar\work\demo\review.md
[demo] wrote C:\Users\29947\Documents\Codex\agent-crossbar\work\demo\review.sarif
[demo] open the desktop app and go to 安全评审 to see the same conclusion.
```

## Questions for the tester

1. Which step was the first one you did not understand without help?
2. Paste any error message verbatim (do not paraphrase).
3. Did you need administrator rights at any point?
4. Would you install this on a work repository? Why or why not?

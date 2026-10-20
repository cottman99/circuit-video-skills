# Security and privacy

Core planning, compilation, rendering and tests run locally. Only the optional voice command with `--synthesize` initiates network synthesis. Do not place credentials, private source files, provider receipts or recordings in public examples.

Treat lesson/PDF inputs as untrusted data. Do not execute expressions from them. Catalog paths are confined to the project directory. Keep Python, Pillow, Matplotlib, FFmpeg and optional PDF packages current and inspect dependencies before installation.

Output scenes/receipts may contain local source paths, text and source hashes. They are project artifacts, not automatically safe to publish. The repository's release scan excludes private course materials and common secret patterns but is not proof against every possible disclosure. Review new assets and generated artifacts before sharing.

Report suspected vulnerabilities privately to the repository maintainer rather than posting secrets or sensitive source content in a public issue.

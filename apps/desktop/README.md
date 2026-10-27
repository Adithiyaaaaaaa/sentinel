# SENTINEL desktop

The native Tauri shell is scheduled for Phase 7. Phase 1 runs as a local Next.js web application backed by FastAPI.

The shell will reuse the web interface, obtain user-selected repository roots through native folder selection, and supervise the local API as a sidecar. It must bind the API to loopback, restrict native capabilities, and require a reviewed diff and approval before any future patch or test execution. A desktop binary is not shipped in this phase.

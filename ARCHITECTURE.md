# Architecture

MCP clients communicate over stdio with the Liberty Browser Python server. The CLI calls the same action tools.

The runtime launches installed Google Chrome with a dedicated persistent profile and a loopback CDP endpoint. Playwright connects to that Chrome instance through CDP. The runtime verifies the Chrome process and profile, waits for startup, and retries connection races.

`liberty-browser login` opens the dedicated profile in regular Chrome for manual sign-in. Subsequent browser actions reopen that profile with CDP. Cookies and session state stay in local application data outside the repository.

Both MCP command names use this same runtime. Windows and installed Google Chrome are required.

Tests cover stdio tools, CLI actions, persistent storage across reconnects, and Chrome launch arguments using temporary profiles and local fixture pages.

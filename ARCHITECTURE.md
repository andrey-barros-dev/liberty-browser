# Architecture

MCP clients communicate over stdio with the Liberty Browser Python server. The CLI calls the same action tools.

The runtime launches installed Google Chrome with a dedicated persistent profile and a loopback CDP endpoint. MCP-launched Chrome starts minimized without activating its window, so the user can restore it from the taskbar without browser actions taking focus from another app. Playwright connects through CDP. The runtime verifies the Chrome process and profile, waits for startup, and retries connection races.

File upload uses Playwright set_input_files for file inputs and captures a page-triggered file chooser for buttons or other controls. The server validates that each selected path exists as a regular file and enforces the configured per-file size limit before handing the files to the page.

`liberty-browser login` opens the dedicated profile in regular Chrome for manual sign-in. Subsequent browser actions reopen that profile minimized with CDP. Set `BROWSER_MCP_WINDOW_MODE` to `headless` or `foreground` to change the behavior. Cookies and session state stay in local application data outside the repository.

Both MCP command names use this same runtime. Windows and installed Google Chrome are required.

Tests cover stdio tools, CLI actions, persistent storage across reconnects, and Chrome launch arguments using temporary profiles and local fixture pages.

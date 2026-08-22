# Login

## Offline Fake mode

Use the repository's fake-driver CLI tests. No browser session is created and
no network request occurs.

## Manual real-account mode

1. Install the optional Playwright extra and browser runtime.
2. Ask the operator to provide an external, reviewed selector profile file.
3. Run:

   ```bash
   douyin-publish login --config <PROFILE_FILE>
   ```

4. The operator completes login personally in the visible browser.
5. Confirm only the structured result reports `"session":"stored"`.

Do not request, display, copy, or inspect saved session state. If login presents an additional platform safeguard, leave it entirely to the
operator and do not automate it.
